"""登入角色與 Secrets（M4）：登記角色、人工登入、檢查是否已登入、提供執行用的登入設定。

- 角色只描述「怎麼登入、怎麼判斷已登入」；登入狀態（storageState）每個角色一份，存在資料目錄，
  只有本人能讀寫，不經由網頁或 API 提供。
- **人工登入**：在操作的那台（這台或錄製端）開瀏覽器視窗到登入網址，使用者自己登入（SSO、驗證碼、
  二次驗證都可以），按「完成登入」或關掉視窗後，**開視窗的那台**先用無頭瀏覽器確認真的登入了，
  才把登入狀態傳回來取代原本的；所以這台不需要瀏覽器。還沒登入時視窗不關，可以繼續登入。
  不會自己確認的舊版錄製端，改由這台確認（這台要有瀏覽器）。
- **檢查**：這台有下載角色用的瀏覽器時在這台；沒有時，透過錄製端操作就交給錄製端（無頭）；
  都不行時說明，不改角色的狀態。檢查用登入狀態的複本，通過後才取代原本的。
- **自動登入**（選用）：角色附一段 DSL 步驟，帳密用 ``{{ secrets.名稱 }}``；
  執行前發現沒登入時先自動登入。
- 執行的結果也會更新角色的狀態：需要登入的執行把角色標成需要登入，通過登入檢查的標成已登入。
- 角色的定義放在領域資料夾的 ``roles/<角色>.yaml``（M11），跟著領域同步；資料庫是它的索引，
  登入檢查的結果只在資料庫。
"""

import contextlib
import dataclasses
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Issue, format_field, format_issue, validate_data
from rpa_core.dsl.features import data_features
from rpa_core.dsl.yaml_loader import YamlLoadError, load_yaml
from rpa_core.i18n import Locale, use_locale
from rpa_runner.commands import module_command
from rpa_runner.files import LOGIN, read_json_or
from rpa_runner.installed import DISPLAY_NAMES, missing_browsers
from rpa_runner.login import ENV_LOGIN, EXIT_NEEDS_LOGIN, LoginSettings
from rpa_server.domain import DOMAIN_ID, RoleRecord, RoleStatus, now
from rpa_server.errors import ServiceError
from rpa_server.i18n import t
from rpa_server.models import Domain, Role
from rpa_server.processes import ChildProcess, Launch, Lines, child_env, launch, send, stop
from rpa_server.secret_store import SECRET_NAME, SecretInfo, SecretStore
from rpa_server.storage import Storage

if TYPE_CHECKING:
    from rpa_server.devices import RecorderHub
    from rpa_server.packs import PackStore

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
BROWSERS_TTL: Final = 300.0
"""這台下載了哪些瀏覽器：判斷的結果快取這麼久（秒）。"""
STATE_COPY: Final = "state.json"
"""登入檢查用的登入狀態複本，放在檢查的資料夾裡；檢查通過後才取代角色的狀態。"""


class LocalBrowsers:
    """這台下載了哪些瀏覽器（依 Playwright 預期的執行檔位置判斷，不啟動瀏覽器）。

    要啟動 Playwright 的 driver（約一秒），所以結果快取 :data:`BROWSERS_TTL` 秒，整個程序共用一份。
    判斷不了時當作都有：照舊在這台試，失敗時錯誤會說要下載哪個瀏覽器。
    """

    def __init__(self, ttl: float = BROWSERS_TTL) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._checked = float("-inf")
        self._engines: frozenset[str] = frozenset(ENGINES)

    def __call__(self) -> frozenset[str]:
        with self._lock:
            if time.monotonic() - self._checked >= self.ttl:
                missing = set(missing_browsers(ENGINES))
                self._engines = frozenset(engine for engine in ENGINES if engine not in missing)
                self._checked = time.monotonic()
            return self._engines


_LOCAL_BROWSERS: Final = LocalBrowsers()


def _mtime(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _check_state_data(data: bytes) -> None:
    """登入狀態檔的內容要是 Playwright storageState 的 JSON 物件（cookies、origins 是清單）。"""
    state: object = json.loads(data.decode("utf-8"))
    if not isinstance(state, dict):
        raise ValueError("storage state must be an object")
    values = cast("dict[str, object]", state)
    if not all(isinstance(values.get(key, []), list) for key in ("cookies", "origins")):
        raise ValueError("cookies and origins must be lists")


def _outdated(log: Path) -> bool:
    """錄製端的程式比較舊、不認得 ``check --state``（argparse 的錯誤）。"""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "unrecognized arguments" in text and "--state" in text


def _login_problem(event: Mapping[str, object], *, final: bool) -> str:
    """人工登入確認沒通過（``not_logged_in``）的說明；final 是子程序因此結束時用的。"""
    detail = event.get("message")
    if detail:
        key = "role.login_unverified" if final else "role.login_check_failed"
        return t(key, detail=str(detail))
    key = "role.login_closed_not_logged_in" if final else "role.login_not_yet"
    return t(key, url=str(event.get("url") or ""))


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
    """一次人工登入：瀏覽器視窗開在操作的這台電腦上（伺服器或錄製端），等使用者登入。"""

    role_id: str
    process: ChildProcess
    candidate: Path
    device: str | None = None
    """在哪台錄製端登入（M10.2）；伺服器這台是 None。"""
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
            "deviceId": self.device,
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
        launcher: Launch | None = None,
        hosts: "RecorderHub | None" = None,
        packs: "PackStore | None" = None,
        default_domain: Callable[[], str] | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.secrets = secrets
        self.display = display
        self.locale: Locale = locale
        self.scene_roles = scene_roles
        """場景 → 用到的角色（最新版本）；由 Services 提供。"""
        self.launcher: Launch = launcher or launch
        """在這台啟動人工登入子程序的方式；測試換成不開瀏覽器視窗的假程式。"""
        self.hosts = hosts
        """錄製端（M10.2）：請求透過錄製端時，登入的瀏覽器視窗開在那台。"""
        self.packs = packs
        """角色定義寫進領域資料夾（M11）；None 時只用資料庫（單元測試）。"""
        self.default_domain = default_domain
        """沒指定領域時放在哪個領域（「未分類」，需要時建立）。"""
        self._lock = threading.Lock()
        self._logins: dict[str, _LoginSession] = {}
        self._checking: set[str] = set()
        self.local_engines: Callable[[], Collection[str]] = _LOCAL_BROWSERS
        """這台下載了哪些瀏覽器（決定登入檢查在哪台跑）；測試換成固定的清單。"""

    # ------------------------------------------------------------ 查詢

    @staticmethod
    def _get(session: Session, role_id: str) -> Role:
        role = session.get(Role, role_id)
        if role is None or role.missing:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        return role

    def _state_time(self, role_id: str) -> datetime | None:
        path = self.storage.role_state(role_id)
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            return None

    def _activities(self) -> dict[str, tuple[str | None, "_LoginSession | None"]]:
        """每個角色現在的背景工作（checking、login）與人工登入的工作階段。

        要在讀資料庫**之前**取得：背景工作都是先把結果寫進資料庫才結束，
        所以這裡看到「沒有在做」時，之後讀到的一定是最後的結果，不會拿到舊的狀態卻以為已經做完。
        """
        with self._lock:
            roles = self._checking | self._logins.keys()
            activities: dict[str, tuple[str | None, _LoginSession | None]] = {}
            for role_id in roles:
                login = self._logins.get(role_id)
                if login is not None and login.active:
                    activities[role_id] = ("login", login)
                elif role_id in self._checking:
                    activities[role_id] = ("checking", login)
                else:
                    activities[role_id] = (None, login)
        return activities

    def _record(
        self,
        role: Role,
        used: Mapping[str, str],
        activities: Mapping[str, tuple[str | None, "_LoginSession | None"]],
    ) -> RoleRecord:
        saved = self._state_time(role.id)
        activity, login = activities.get(role.id, (None, None))
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
            domain_id=role.domain_id,
        )

    def list_roles(self) -> list[RoleRecord]:
        used = self.scene_roles()
        activities = self._activities()
        with self.sessions() as session:
            roles = session.scalars(select(Role).where(Role.missing.is_(False)).order_by(Role.id))
            return [self._record(role, used, activities) for role in roles]

    def get_role(self, role_id: str) -> RoleRecord:
        used = self.scene_roles()
        activities = self._activities()
        with self.sessions() as session:
            return self._record(self._get(session, role_id), used, activities)

    def exists(self, role_id: str) -> bool:
        with self.sessions() as session:
            role = session.get(Role, role_id)
            return role is not None and not role.missing

    def login_settings(self, role_id: str) -> LoginSettings | None:
        """執行與調試用的登入設定；角色沒有登記時回傳 None。"""
        with self.sessions() as session:
            role = session.get(Role, role_id)
            if role is None or role.missing:
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
        """登記角色；``domainId`` 是定義放在哪個領域資料夾，沒有時放「未分類」。"""
        role_id = role_id.strip()
        if not DOMAIN_ID.fullmatch(role_id):
            raise _error(422, "role_id_invalid", t("error.role_id_invalid", id=role_id))
        fields = self._fields(values, creating=True)
        domain_id = self._domain_id(values)
        with self._pack_lock(), self.sessions() as session:
            self._check_domain(session, domain_id)
            role = session.get(Role, role_id)
            if role is not None and not role.missing:
                raise _error(409, "role_exists", t("error.role_exists", id=role_id))
            moment = now()
            if role is None:
                role = Role(id=role_id, status="none", created_at=moment, updated_at=moment)
                session.add(role)
            for name, value in {**fields, "domain_id": domain_id, "missing": False}.items():
                setattr(role, name, value)
            role.updated_at = moment
            session.flush()
            if self.packs is not None:
                self.packs.write_role(role)
            session.commit()
        return self.get_role(role_id)

    def update_role(self, role_id: str, values: Mapping[str, object]) -> RoleRecord:
        """修改角色；``domainId`` 有指定時把定義搬到那個領域資料夾。"""
        fields = self._fields(values, creating=False)
        with self._pack_lock(), self.sessions() as session:
            role = self._get(session, role_id)
            previous = role.domain_id
            if values.get("domainId"):
                fields["domain_id"] = self._check_domain(session, str(values["domainId"]))
            for name, value in fields.items():
                setattr(role, name, value)
            role.updated_at = now()
            if self.packs is not None:
                if previous != role.domain_id:
                    self.packs.remove_role(previous, role_id)
                self.packs.write_role(role)
            session.commit()
        return self.get_role(role_id)

    def _domain_id(self, values: Mapping[str, object]) -> str | None:
        domain_id = str(values.get("domainId") or "").strip()
        if domain_id:
            return domain_id
        return self.default_domain() if self.default_domain is not None else None

    @staticmethod
    def _check_domain(session: Session, domain_id: str | None) -> str | None:
        if domain_id is not None and session.get(Domain, domain_id) is None:
            raise _error(404, "domain_not_found", t("error.domain_not_found", id=domain_id))
        return domain_id

    def _pack_lock(self) -> contextlib.AbstractContextManager[object]:
        """寫入領域資料夾時持有它的鎖（和存檔、載入同一把）。"""
        if self.packs is None:
            return contextlib.nullcontext()
        return self.packs.lock

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
        with self._pack_lock(), self.sessions() as session:
            role = self._get(session, role_id)
            if used:
                raise _error(
                    409, "role_in_use", t("error.role_in_use", id=role_id, scenes=", ".join(used))
                )
            self.cancel_login(role_id, missing_ok=True)
            if self.packs is not None:
                self.packs.remove_role(role.domain_id, role_id)
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

    def import_examples(
        self, path: Path, wanted: Sequence[str], *, domain_id: str | None = None
    ) -> list[str]:
        """從範例的 roles.json 建立場景用到、還沒登記的角色（放在 domain_id 這個領域）。"""
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
                self.create_role(role_id, {**values, "domainId": domain_id})
            except Exception:  # 範例檔有誤時略過，不影響匯入場景
                continue
            created.append(role_id)
        return created

    # ------------------------------------------------------------ 執行結果

    def save_state(self, role_id: str, data: bytes) -> None:
        """遠端 worker 自動登入後傳回的登入狀態（M9a）：先寫暫存檔再改名，只有本人能讀寫。

        內容必須是 Playwright storageState 的 JSON 物件（cookies、origins 是清單），
        否則拋出 ValueError。
        """
        _check_state_data(data)
        with self.sessions() as session:
            if session.get(Role, role_id) is None:
                raise ValueError(f"unknown role: {role_id}")
        path = self.storage.role_state(role_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.remote")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        temporary.replace(path)

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

    def check_launcher(self, engine: str, features: Collection[str] = ()) -> Launch:
        """登入檢查在哪台跑：這台有下載這個瀏覽器時在這台；沒有時，請求透過錄製端就交給錄製端
        （無頭，不必能顯示視窗）；都不行時拋出說明。``features`` 是登入設定用到的 DSL 擴充
        （錄製端的 App 要看得懂，M7a）。"""
        if engine in self.local_engines():
            return launch
        via = self.hosts.current() if self.hosts is not None else None
        if via is not None and self.hosts is not None:
            self.hosts.check(via, engine=engine, headed=False, features=features)
            return self.hosts.launcher(via)
        raise _error(
            422,
            "role_check_unavailable",
            t("error.role_check_unavailable", browser=DISPLAY_NAMES.get(engine, engine)),
        )

    def can_check(self, engine: str) -> bool:
        """頁面用：「檢查」能不能按（這台有瀏覽器，或請求透過錄製端）。"""
        if engine in self.local_engines():
            return True
        return self.hosts is not None and self.hosts.current() is not None

    def _check_process(
        self,
        settings: LoginSettings,
        engine: str,
        out: Path,
        *,
        state: Path,
        launcher: Launch = launch,
    ) -> tuple[int, dict[str, object]]:
        """執行一次登入檢查子程序（這台或錄製端），回傳 (結束碼, login.json)。

        檢查的是 ``state`` 的複本 ``out/state.json``：子程序通過後把最新的狀態寫回複本，
        由呼叫端決定要不要取代角色的狀態。交給錄製端時，這個資料夾就是它的工作資料夾，
        複本跟著送過去、寫回後傳回來。
        """
        names = settings.secrets
        values = self.secrets.values()
        env = child_env(
            self.locale,
            {
                ENV_LOGIN: json.dumps(settings.to_json(), ensure_ascii=False),
                # 錄製端只拿得到這裡另外給的變數：沒保存的 Secret 也從這台的同名環境變數帶過去
                **{
                    name: values[name] if name in values else os.environ[name]
                    for name in names
                    if name in values or name in os.environ
                },
            },
        )
        out.mkdir(parents=True, exist_ok=True)
        copy = out / STATE_COPY
        with contextlib.suppress(OSError):
            data = state.read_bytes()
            descriptor = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        command = module_command(
            "rpa_runner.login",
            [
                "check",
                "--out",
                str(out),
                "--deadline",
                str(CHECK_SECONDS),
                "--engine",
                engine,
                "--state",
                str(copy),
            ],
        )
        process = launcher(command, env=env, log=out / "login.log", cwd=out, pipes=False)
        try:
            code = process.wait(timeout=CHECK_SECONDS + 30)
        except subprocess.TimeoutExpired:
            stop(process)
            code = 3
        details = read_json_or(out / LOGIN, {})
        return code, cast("dict[str, object]", details) if isinstance(details, dict) else {}

    def _outcome(
        self, code: int, details: Mapping[str, object], out: Path | None = None
    ) -> tuple[RoleStatus, str | None]:
        if code == 0:
            return "logged_in", t("role.auto_logged_in") if details.get("refreshed") else None
        if code == EXIT_NEEDS_LOGIN:
            return "needs_login", t("role.not_logged_in", url=details.get("url") or "")
        if not details and out is not None and _outdated(out / "login.log"):
            return "unknown", t("role.check_device_outdated")
        error = str(details.get("error") or t("role.check_crashed", code=code))
        return "unknown", error

    def _adopt(self, role_id: str, copy: Path, before: int | None) -> None:
        """檢查通過後，用檢查寫回的複本（可能自動登入過、換發了 cookie）取代角色的登入狀態。

        這段期間角色的狀態被別人更新過（人工登入、執行時的自動登入）就不取代，免得舊的蓋掉新的；
        複本的內容不對也不取代。
        """
        state = self.storage.role_state(role_id)
        try:
            _check_state_data(copy.read_bytes())
        except (OSError, ValueError):
            return
        if _mtime(state) != before:
            return
        if os.name != "nt":
            copy.chmod(0o600)
        copy.replace(state)

    def check(self, role_id: str) -> RoleRecord:
        """在背景檢查是否已登入（必要時自動登入）；馬上回傳，進度看 activity。

        在哪台跑見 :meth:`check_launcher`；沒有地方可以跑時拋出說明，角色的狀態不變。
        """
        settings = self.login_settings(role_id)
        if settings is None:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        engine = self.get_role(role_id).engine
        launcher = self.check_launcher(engine, data_features(settings.to_json()))
        with self._lock:
            login = self._logins.get(role_id)
            if role_id in self._checking or (login is not None and login.active):
                raise _error(409, "role_busy", t("error.role_busy", id=role_id))
            self._checking.add(role_id)
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
                    state = self.storage.role_state(role_id)
                    before = _mtime(state)
                    code, details = self._check_process(
                        settings, engine, out, state=state, launcher=launcher
                    )
                    status, message = self._outcome(code, details, out)
                    if status == "logged_in":
                        self._adopt(role_id, out / STATE_COPY, before)
                    (out / STATE_COPY).unlink(missing_ok=True)
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
        """在操作的這台電腦開瀏覽器視窗到登入網址，等使用者登入。

        請求透過錄製端時視窗開在那台（M10.2）；存下的登入狀態傳回這台，確認與保存照舊在這台。
        """
        via = self.hosts.current() if self.hosts is not None else None
        if via is None and not self.display:
            raise _error(422, "display_unavailable", t("error.login_display_unavailable"))
        settings = self.login_settings(role_id)
        if settings is None:
            raise _error(404, "role_not_found", t("error.role_not_found", id=role_id))
        engine = self.get_role(role_id).engine
        launcher = self.launcher
        if via is not None and self.hosts is not None:
            self.hosts.check(via, engine=engine, features=data_features(settings.to_json()))
            launcher = self.hosts.launcher(via)
        folder = self.storage.roles / role_id
        folder.mkdir(parents=True, exist_ok=True)
        candidate = folder / "candidate.json"
        candidate.unlink(missing_ok=True)
        with self._lock:
            current = self._logins.get(role_id)
            if (current is not None and current.active) or role_id in self._checking:
                raise _error(409, "role_busy", t("error.role_busy", id=role_id))
            process = launcher(
                module_command(
                    "rpa_runner.login",
                    [
                        "capture",
                        "--state",
                        str(candidate),
                        "--engine",
                        engine,
                    ],
                ),
                env=child_env(self.locale, {ENV_LOGIN: json.dumps(settings.to_json())}),
                log=folder / "capture.log",
            )
            login = _LoginSession(
                role_id=role_id,
                process=process,
                candidate=candidate,
                device=via.id if via is not None else None,
            )
            self._logins[role_id] = login
        threading.Thread(
            target=self._follow,
            args=(login, settings, engine),
            name=f"login-{role_id}",
            daemon=True,
        ).start()
        return self.get_role(role_id)

    def _follow(self, login: _LoginSession, settings: LoginSettings, engine: str) -> None:
        """讀人工登入子程序的進度，登入成功才取代原本的登入狀態。

        開視窗的那台確認過（``saved`` 附 ``verified``）就直接取代；還沒登入（``not_logged_in``）
        時把說明顯示在頁面、繼續等使用者登入。舊版的子程序不會自己確認：這台有瀏覽器時照舊在
        這台確認，沒有就說明要更新錄製端。
        """
        with use_locale(self.locale):
            lines = Lines(login.process)
            deadline = time.monotonic() + LOGIN_SECONDS
            saved = verified = False
            problem: str | None = None
            """最近一次確認沒通過的原因；子程序因此結束（使用者關了視窗）時當作失敗的說明。"""
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
                with contextlib.suppress(ValueError, AttributeError):
                    event = cast("dict[str, object]", json.loads(line))
                    kind = event.get("event")
                    if kind == "ready":
                        self._set(login, "waiting")
                    elif kind == "checking":
                        self._set(login, "checking")
                    elif kind == "not_logged_in":
                        problem = _login_problem(event, final=True)
                        self._set(login, "waiting", _login_problem(event, final=False))
                    elif kind == "saved":
                        saved = True
                        verified = event.get("verified") is True
                    elif kind == "cancelled":
                        self._finish(login, "cancelled", None)
                    elif kind == "error":
                        self._finish(login, "failed", str(event.get("message") or ""))
            login.process.wait()
            if not saved:
                if login.active:
                    message = problem or t("role.login_ended", code=login.process.returncode)
                    self._finish(login, "failed", message)
                login.candidate.unlink(missing_ok=True)
                return
            if verified:
                if self._replace_state(login.role_id, login.candidate):
                    self._save_status(login.role_id, "logged_in", None)
                    self._finish(login, "done", t("role.login_done"))
                else:
                    self._finish(login, "failed", t("role.login_not_confirmed"))
                login.candidate.unlink(missing_ok=True)
                return
            self._set(login, "checking")
            if engine not in self.local_engines():
                login.candidate.unlink(missing_ok=True)
                browser = DISPLAY_NAMES.get(engine, engine)
                self._finish(login, "failed", t("role.login_device_outdated", browser=browser))
                return
            out = self.storage.roles / login.role_id / "check"
            shutil.rmtree(out, ignore_errors=True)
            code, details = self._check_process(settings, engine, out, state=login.candidate)
            status, message = self._outcome(code, details, out)
            copy = out / STATE_COPY
            source = copy if copy.is_file() else login.candidate
            if status == "logged_in" and self._replace_state(login.role_id, source):
                self._save_status(login.role_id, "logged_in", None)
                self._finish(login, "done", t("role.login_done"))
            else:
                self._finish(login, "failed", message or t("role.login_not_confirmed"))
            login.candidate.unlink(missing_ok=True)
            copy.unlink(missing_ok=True)

    def _replace_state(self, role_id: str, source: Path) -> bool:
        """確認過的登入狀態取代角色原本的（只有本人能讀寫）；檔案不在或內容不對時回傳 False。"""
        try:
            _check_state_data(source.read_bytes())
            if os.name != "nt":
                source.chmod(0o600)
            source.replace(self.storage.role_state(role_id))
        except (OSError, ValueError):
            return False
        return True

    def _set(self, login: _LoginSession, status: str, message: str | None = None) -> None:
        with self._lock:
            if not login.active:
                return
            login.status = status
            login.message = message

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
