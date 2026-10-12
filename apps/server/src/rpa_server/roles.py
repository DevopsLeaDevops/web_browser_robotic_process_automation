"""登入角色與 Secrets（M4）：登記角色、人工登入、檢查是否已登入、提供執行用的登入設定。

- 角色只描述「怎麼登入、怎麼判斷已登入」；登入狀態（storageState）每個角色一份，存在資料目錄，
  只有本人能讀寫，不經由網頁或 API 提供。
- **人工登入**：在這台電腦開瀏覽器視窗到登入網址，使用者自己登入（SSO、驗證碼、二次驗證都可以），
  按「完成登入」或關掉視窗後，先用無頭瀏覽器確認真的登入了，才取代原本的登入狀態。
- **自動登入**（選用）：角色附一段 DSL 步驟，帳密用 ``{{ secrets.名稱 }}``；
  執行前發現沒登入時先自動登入。
- 執行的結果也會更新角色的狀態：需要登入的執行把角色標成需要登入，通過登入檢查的標成已登入。
"""

import contextlib
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Issue, format_field, format_issue, validate_data
from rpa_core.dsl.yaml_loader import YamlLoadError, load_yaml
from rpa_core.i18n import Locale, use_locale
from rpa_runner.files import LOGIN, read_json_or
from rpa_runner.login import ENV_LOGIN, EXIT_NEEDS_LOGIN, LoginSettings
from rpa_server.domain import DOMAIN_ID, RoleRecord, RoleStatus, now
from rpa_server.errors import ServiceError
from rpa_server.i18n import t
from rpa_server.models import Role
from rpa_server.processes import Lines, child_env, launch, send, stop
from rpa_server.secret_store import SECRET_NAME, SecretInfo, SecretStore
from rpa_server.storage import Storage

__all__ = ["CHECK_SECONDS", "LOGIN_SECONDS", "RoleService", "parse_locator"]

CHECK_SECONDS: Final = 60.0
"""檢查是否已登入（含自動登入）最多花多久。"""
LOGIN_SECONDS: Final = 15 * 60.0
"""人工登入最多等多久；超過就關掉瀏覽器。"""
ENGINES: Final = ("chromium", "firefox")
_SECRET_REFERENCE: Final = re.compile(
    r"secrets\s*(?:\.\s*([A-Z][A-Z0-9_]*)|\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\])"
)
_ACTIVE: Final = frozenset({"starting", "waiting", "checking"})


def _error(status: int, code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(status, code, message, **details)


def _check_url(value: str | None, *, required: bool) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise _error(422, "role_url_invalid", t("error.role_url_invalid", value=value))
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise _error(422, "role_url_invalid", t("error.role_url_invalid", value=value))
    return value


def parse_locator(text: object) -> dict[str, object]:
    """「已登入時看得到的元素」：DSL 定位器，寫成 YAML（``{ testId: current-user }``）或物件。"""
    data: object = text
    if isinstance(text, str):
        try:
            data, _ = load_yaml(text)
        except YamlLoadError as error:
            raise _error(
                422, "role_check_invalid", t("error.role_check_invalid", detail=error)
            ) from error
    if not isinstance(data, dict) or not data:
        raise _error(422, "role_check_invalid", t("error.role_check_invalid", detail=text))
    locator = cast("dict[str, object]", data)
    probe: dict[str, object] = {
        "schemaVersion": 1,
        "id": "check",
        "name": "check",
        "steps": [{"id": "check", "action": "waitFor", "target": locator}],
    }
    result = validate_data(probe)
    if not result.ok:
        details = "; ".join(_locator_issue(issue) for issue in result.issues)
        raise _error(422, "role_check_invalid", t("error.role_check_invalid", detail=details))
    return locator


def _locator_issue(issue: Issue) -> str:
    """定位器的問題：只留定位器裡的欄位名稱。"""
    path = list(issue.path)
    inner = path[3:] if path[:3] == ["steps", 0, "target"] else path
    name = format_field(inner)
    return f"{name}: {issue.message}" if name else issue.message


def parse_steps(text: str | None) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """自動登入步驟（DSL 步驟清單的 YAML）→ (步驟, 用到的 Secrets 名稱)；沒有內容時是空的。"""
    if text is None or not text.strip():
        return [], ()
    try:
        data, _ = load_yaml(text)
    except YamlLoadError as error:
        raise _error(
            422,
            "role_steps_invalid",
            t("error.role_steps_invalid", count=1),
            issues=[{"text": str(error)}],
        ) from error
    if isinstance(data, dict) and "steps" in data:
        data = cast("dict[str, object]", data)["steps"]
    if not isinstance(data, list) or not data:
        raise _error(
            422,
            "role_steps_invalid",
            t("error.role_steps_invalid", count=1),
            issues=[{"text": t("error.role_steps_not_list")}],
        )
    steps = cast("list[dict[str, object]]", data)
    names = sorted({match.group(1) or match.group(2) for match in _SECRET_REFERENCE.finditer(text)})
    probe: dict[str, object] = {
        "schemaVersion": 1,
        "id": "login",
        "name": "login",
        "secrets": names,
        "steps": steps,
    }
    result = validate_data(probe)
    if not result.ok:
        raise _error(
            422,
            "role_steps_invalid",
            t("error.role_steps_invalid", count=len(result.issues)),
            issues=[{"text": format_issue(issue)} for issue in result.issues],
        )
    return steps, tuple(names)


@dataclass(slots=True)
class _LoginSession:
    """一次人工登入：瀏覽器視窗開在這台電腦上，等使用者登入。"""

    role_id: str
    process: subprocess.Popen[str]
    candidate: Path
    status: str = "starting"
    """starting → waiting（視窗已開）→ checking（確認登入狀態）→ done／failed／cancelled。"""
    message: str | None = None
    started_at: datetime = field(default_factory=now)
    finished_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.status in _ACTIVE

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "startedAt": self.started_at.isoformat(timespec="seconds"),
            "finishedAt": self.finished_at.isoformat(timespec="seconds")
            if self.finished_at
            else None,
        }


class RoleService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: Storage,
        secrets: SecretStore,
        *,
        display: bool,
        locale: Locale,
        scene_roles: Callable[[], Mapping[str, str]] = dict,
        launcher: Callable[..., subprocess.Popen[str]] | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.secrets = secrets
        self.display = display
        self.locale: Locale = locale
        self.scene_roles = scene_roles
        """場景 → 用到的角色（最新版本）；由 Services 提供。"""
        self.launcher: Callable[..., subprocess.Popen[str]] = launcher or launch
        """啟動人工登入子程序的方式；測試換成不開瀏覽器視窗的假程式。"""
        self._lock = threading.Lock()
        self._logins: dict[str, _LoginSession] = {}
        self._checking: set[str] = set()

    # ------------------------------------------------------------ 查詢

    @staticmethod
    def _get(session: Session, role_id: str) -> Role:
        role = session.get(Role, role_id)
        if role is None:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        return role

    def _state_time(self, role_id: str) -> datetime | None:
        path = self.storage.role_state(role_id)
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            return None

    def _record(self, role: Role, used: Mapping[str, str]) -> RoleRecord:
        saved = self._state_time(role.id)
        with self._lock:
            login = self._logins.get(role.id)
            checking = role.id in self._checking
        activity = (
            "login" if login is not None and login.active else ("checking" if checking else None)
        )
        # 登入狀態檔不見了就不算已登入；檢查失敗（需要登入、無法確認）照資料庫的紀錄顯示
        status = cast(
            "RoleStatus", "none" if saved is None and role.status == "logged_in" else role.status
        )
        return RoleRecord(
            id=role.id,
            name=role.name,
            description=role.description,
            login_url=role.login_url,
            check_url=role.check_url,
            check_locator=dict(role.check_locator),
            engine=role.engine,
            auto_login=role.auto_login,
            status=status,
            message=role.message,
            checked_at=role.checked_at,
            state_saved_at=saved,
            used_by=tuple(sorted(scene for scene, role_id in used.items() if role_id == role.id)),
            activity=activity,
            session=login.to_json() if login is not None else None,
            created_at=role.created_at,
        )

    def list_roles(self) -> list[RoleRecord]:
        used = self.scene_roles()
        with self.sessions() as session:
            roles = session.scalars(select(Role).order_by(Role.id))
            return [self._record(role, used) for role in roles]

    def get_role(self, role_id: str) -> RoleRecord:
        used = self.scene_roles()
        with self.sessions() as session:
            return self._record(self._get(session, role_id), used)

    def exists(self, role_id: str) -> bool:
        with self.sessions() as session:
            return session.get(Role, role_id) is not None

    def login_settings(self, role_id: str) -> LoginSettings | None:
        """執行與調試用的登入設定；角色沒有登記時回傳 None。"""
        with self.sessions() as session:
            role = session.get(Role, role_id)
            if role is None:
                return None
            steps, names = parse_steps(role.auto_login)
            return LoginSettings(
                role=role.id,
                state=self.storage.role_state(role.id),
                check_url=role.check_url or role.login_url,
                check=dict(role.check_locator),
                login_url=role.login_url,
                steps=tuple(steps),
                secrets=names,
                name=role.name,
            )

    # ------------------------------------------------------------ 登記

    def create_role(self, role_id: str, values: Mapping[str, object]) -> RoleRecord:
        role_id = role_id.strip()
        if not DOMAIN_ID.fullmatch(role_id):
            raise _error(422, "role_id_invalid", t("error.role_id_invalid", id=role_id))
        fields = self._fields(values, creating=True)
        with self.sessions() as session:
            if session.get(Role, role_id) is not None:
                raise _error(409, "role_exists", t("error.role_exists", id=role_id))
            moment = now()
            role = Role(id=role_id, status="none", created_at=moment, updated_at=moment, **fields)
            session.add(role)
            session.commit()
        return self.get_role(role_id)

    def update_role(self, role_id: str, values: Mapping[str, object]) -> RoleRecord:
        fields = self._fields(values, creating=False)
        with self.sessions() as session:
            role = self._get(session, role_id)
            for name, value in fields.items():
                setattr(role, name, value)
            role.updated_at = now()
            session.commit()
        return self.get_role(role_id)

    def _fields(self, values: Mapping[str, object], *, creating: bool) -> dict[str, object]:
        """API 的欄位 → 資料庫欄位；建立時名稱、登入網址、判斷方式都要有。"""
        fields: dict[str, object] = {}
        if creating or "name" in values:
            name = str(values.get("name") or "").strip()
            if not name:
                raise _error(422, "role_name_missing", t("error.role_name_missing"))
            fields["name"] = name[:100]
        if "description" in values:
            fields["description"] = str(values.get("description") or "").strip() or None
        if creating or "loginUrl" in values:
            fields["login_url"] = _check_url(
                cast("str | None", values.get("loginUrl")), required=True
            )
        if "checkUrl" in values:
            fields["check_url"] = _check_url(
                cast("str | None", values.get("checkUrl")), required=False
            )
        if creating or "check" in values:
            fields["check_locator"] = parse_locator(values.get("check"))
        if "engine" in values or creating:
            engine = str(values.get("engine") or "chromium")
            if engine not in ENGINES:
                raise _error(
                    422, "role_engine_invalid", t("error.role_engine_invalid", engine=engine)
                )
            fields["engine"] = engine
        if "autoLogin" in values:
            text = str(values.get("autoLogin") or "")
            parse_steps(text)
            fields["auto_login"] = text.strip() + "\n" if text.strip() else None
        return fields

    def delete_role(self, role_id: str) -> None:
        """刪除角色與它的登入狀態；還有場景用到時不能刪。"""
        used = sorted(scene for scene, role in self.scene_roles().items() if role == role_id)
        with self.sessions() as session:
            role = self._get(session, role_id)
            if used:
                raise _error(
                    409, "role_in_use", t("error.role_in_use", id=role_id, scenes=", ".join(used))
                )
            self.cancel_login(role_id, missing_ok=True)
            session.delete(role)
            session.commit()
        shutil.rmtree(self.storage.roles / role_id, ignore_errors=True)

    def clear_state(self, role_id: str) -> RoleRecord:
        """登出：刪除登入狀態檔。"""
        with self.sessions() as session:
            role = self._get(session, role_id)
            role.status = "none"
            role.message = None
            session.commit()
        self.storage.role_state(role_id).unlink(missing_ok=True)
        return self.get_role(role_id)

    def import_examples(self, path: Path, wanted: Sequence[str]) -> list[str]:
        """從範例的 roles.json 建立場景用到、還沒登記的角色。"""
        data = read_json_or(path, {})
        roles = cast("dict[str, object]", data).get("roles") if isinstance(data, dict) else None
        created: list[str] = []
        for item in cast("list[object]", roles) if isinstance(roles, list) else []:
            if not isinstance(item, dict):
                continue
            values = cast("dict[str, object]", item)
            role_id = str(values.get("id", ""))
            if role_id not in wanted or self.exists(role_id):
                continue
            try:
                self.create_role(role_id, values)
            except Exception:  # 範例檔有誤時略過，不影響匯入場景
                continue
            created.append(role_id)
        return created

    # ------------------------------------------------------------ 執行結果

    def record_result(self, role_id: str, status: str, message: str | None = None) -> None:
        """執行的登入檢查結果：passed → 已登入，needs_login → 需要登入。"""
        mapped = {"passed": "logged_in", "needs_login": "needs_login"}.get(status)
        if mapped is None:
            return
        with self.sessions() as session:
            role = session.get(Role, role_id)
            if role is None:
                return
            role.status = mapped
            role.message = message
            role.checked_at = now()
            session.commit()

    # ------------------------------------------------------------ 檢查

    def _check_process(
        self, settings: LoginSettings, engine: str, out: Path
    ) -> tuple[int, dict[str, object]]:
        """執行一次登入檢查子程序，回傳 (結束碼, login.json)。"""
        names = settings.secrets
        values = self.secrets.values()
        env = child_env(
            self.locale,
            {
                ENV_LOGIN: json.dumps(settings.to_json(), ensure_ascii=False),
                **{name: values[name] for name in names if name in values},
            },
        )
        out.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "rpa_runner.login",
            "check",
            "--out",
            str(out),
            "--deadline",
            str(CHECK_SECONDS),
            "--engine",
            engine,
        ]
        with (out / "login.log").open("wb") as log:
            try:
                completed = subprocess.run(
                    command,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=CHECK_SECONDS + 30,
                    check=False,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 3
        details = read_json_or(out / LOGIN, {})
        return code, cast("dict[str, object]", details) if isinstance(details, dict) else {}

    def _outcome(self, code: int, details: Mapping[str, object]) -> tuple[RoleStatus, str | None]:
        if code == 0:
            return "logged_in", t("role.auto_logged_in") if details.get("refreshed") else None
        if code == EXIT_NEEDS_LOGIN:
            return "needs_login", t("role.not_logged_in", url=details.get("url") or "")
        error = str(details.get("error") or t("role.check_crashed", code=code))
        return "unknown", error

    def check(self, role_id: str) -> RoleRecord:
        """在背景檢查是否已登入（必要時自動登入）；馬上回傳，進度看 activity。"""
        settings = self.login_settings(role_id)
        if settings is None:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        with self._lock:
            login = self._logins.get(role_id)
            if role_id in self._checking or (login is not None and login.active):
                raise _error(409, "role_busy", t("error.role_busy", id=role_id))
            self._checking.add(role_id)
        engine = self.get_role(role_id).engine
        values = self.secrets.values()
        missing = [n for n in settings.secrets if n not in values and n not in os.environ]
        if missing:
            # 缺少自動登入要用的 Secret：只檢查現在的登入狀態，不自動登入
            settings = dataclasses.replace(settings, steps=(), secrets=())

        def work() -> None:
            try:
                with use_locale(self.locale):
                    out = self.storage.roles / role_id / "check"
                    shutil.rmtree(out, ignore_errors=True)
                    code, details = self._check_process(settings, engine, out)
                    status, message = self._outcome(code, details)
                    if missing and status == "needs_login":
                        message = t("role.secret_missing", names=", ".join(missing))
                    self._save_status(role_id, status, message)
            finally:
                with self._lock:
                    self._checking.discard(role_id)

        threading.Thread(target=work, name=f"role-check-{role_id}", daemon=True).start()
        return self.get_role(role_id)

    def _save_status(self, role_id: str, status: RoleStatus, message: str | None) -> None:
        with self.sessions() as session:
            role = session.get(Role, role_id)
            if role is None:
                return
            role.status = status
            role.message = message
            role.checked_at = now()
            session.commit()

    def wait_idle(self, role_id: str, timeout: float = 120) -> None:
        """等背景的檢查或登入結束（測試用）。"""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                login = self._logins.get(role_id)
                busy = role_id in self._checking or (login is not None and login.active)
            if not busy:
                return
            time.sleep(0.1)
        raise TimeoutError(role_id)

    # ------------------------------------------------------------ 人工登入

    def start_login(self, role_id: str) -> RoleRecord:
        """在這台電腦開瀏覽器視窗到登入網址，等使用者登入。"""
        if not self.display:
            raise _error(422, "display_unavailable", t("error.login_display_unavailable"))
        settings = self.login_settings(role_id)
        if settings is None:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        engine = self.get_role(role_id).engine
        folder = self.storage.roles / role_id
        folder.mkdir(parents=True, exist_ok=True)
        candidate = folder / "candidate.json"
        candidate.unlink(missing_ok=True)
        with self._lock:
            current = self._logins.get(role_id)
            if (current is not None and current.active) or role_id in self._checking:
                raise _error(409, "role_busy", t("error.role_busy", id=role_id))
            process = self.launcher(
                [
                    sys.executable,
                    "-m",
                    "rpa_runner.login",
                    "capture",
                    "--state",
                    str(candidate),
                    "--engine",
                    engine,
                ],
                env=child_env(self.locale, {ENV_LOGIN: json.dumps(settings.to_json())}),
                log=folder / "capture.log",
            )
            login = _LoginSession(role_id=role_id, process=process, candidate=candidate)
            self._logins[role_id] = login
        threading.Thread(
            target=self._follow,
            args=(login, settings, engine),
            name=f"login-{role_id}",
            daemon=True,
        ).start()
        return self.get_role(role_id)

    def _follow(self, login: _LoginSession, settings: LoginSettings, engine: str) -> None:
        """讀人工登入子程序的進度；存好登入狀態後確認真的登入了，才取代原本的狀態。"""
        with use_locale(self.locale):
            lines = Lines(login.process)
            deadline = time.monotonic() + LOGIN_SECONDS
            saved = False
            while True:
                try:
                    line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
                except TimeoutError:
                    send(login.process, "cancel")
                    self._finish(login, "failed", t("role.login_timeout"))
                    stop(login.process)
                    return
                if line is None:
                    break
                with contextlib.suppress(ValueError):
                    event = cast("dict[str, object]", json.loads(line))
                    kind = event.get("event")
                    if kind == "ready":
                        self._set(login, "waiting")
                    elif kind == "saved":
                        saved = True
                    elif kind == "cancelled":
                        self._finish(login, "cancelled", None)
                    elif kind == "error":
                        self._finish(login, "failed", str(event.get("message") or ""))
            login.process.wait()
            if not saved:
                if login.active:
                    self._finish(
                        login, "failed", t("role.login_ended", code=login.process.returncode)
                    )
                login.candidate.unlink(missing_ok=True)
                return
            self._set(login, "checking")
            candidate = dataclasses.replace(settings, state=login.candidate)
            out = self.storage.roles / login.role_id / "check"
            shutil.rmtree(out, ignore_errors=True)
            code, details = self._check_process(candidate, engine, out)
            status, message = self._outcome(code, details)
            if status == "logged_in":
                state = self.storage.role_state(login.role_id)
                login.candidate.replace(state)
                self._save_status(login.role_id, "logged_in", None)
                self._finish(login, "done", t("role.login_done"))
            else:
                login.candidate.unlink(missing_ok=True)
                self._finish(login, "failed", message or t("role.login_not_confirmed"))

    def _set(self, login: _LoginSession, status: str) -> None:
        with self._lock:
            login.status = status

    def _finish(self, login: _LoginSession, status: str, message: str | None) -> None:
        with self._lock:
            if not login.active:
                return
            login.status = status
            login.message = message
            login.finished_at = now()

    def finish_login(self, role_id: str) -> RoleRecord:
        """使用者在 Portal 按「完成登入」。"""
        login = self._active_login(role_id)
        if login.status != "waiting" or not send(login.process, "finish"):
            raise _error(409, "login_not_waiting", t("error.login_not_waiting", id=role_id))
        return self.get_role(role_id)

    def cancel_login(self, role_id: str, *, missing_ok: bool = False) -> RoleRecord | None:
        with self._lock:
            login = self._logins.get(role_id)
        if login is None or not login.active:
            if missing_ok:
                return None
            raise _error(409, "login_not_active", t("error.login_not_active", id=role_id))
        send(login.process, "cancel")
        self._finish(login, "cancelled", None)
        threading.Thread(target=stop, args=(login.process,), daemon=True).start()
        return self.get_role(role_id) if not missing_ok else None

    def _active_login(self, role_id: str) -> _LoginSession:
        with self._lock:
            login = self._logins.get(role_id)
        if login is None or not login.active:
            raise _error(409, "login_not_active", t("error.login_not_active", id=role_id))
        return login

    def close(self) -> None:
        """伺服器關閉：結束所有進行中的人工登入。"""
        with self._lock:
            logins = [login for login in self._logins.values() if login.active]
        for login in logins:
            send(login.process, "cancel")
            stop(login.process, grace=2)

    # ------------------------------------------------------------ Secrets

    def list_secrets(self) -> list[SecretInfo]:
        return self.secrets.names()

    def set_secret(self, name: str, value: str) -> SecretInfo:
        if not SECRET_NAME.fullmatch(name):
            raise _error(422, "secret_name_invalid", t("error.secret_name_invalid", name=name))
        if not value:
            raise _error(422, "secret_value_missing", t("error.secret_value_missing"))
        return self.secrets.set(name, value)

    def delete_secret(self, name: str) -> None:
        if not self.secrets.delete(name):
            raise _error(404, "secret_not_found", t("error.secret_not_found", name=name))

    def secret_values(self, names: Sequence[str]) -> dict[str, str]:
        """執行用：指定名稱中有保存的值。"""
        values = self.secrets.values()
        return {name: values[name] for name in names if name in values}
