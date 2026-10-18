"""遠端 worker 的登記與分派（M9a，ADR 0012）。

管理 Portal 是唯一存取資料庫的程序（ADR 0008）；遠端 worker 經由 Worker API
（:mod:`rpa_server.worker_api`）呼叫這裡。

- **登記**：每台 worker 一個權杖，產生時只顯示一次，資料庫只存 sha256；可以停用、重新產生、刪除。
- **上線**（hello）：worker 回報協定版本、程式指紋、作業系統、瀏覽器、能不能顯示視窗。
  協定版本不同就拒絕；程式指紋不同只提醒（頁面顯示「版本不同」）。
- **領取**（claim）：長輪詢；只給這台 worker 能跑的任務（位置是 remote 或 any、瀏覽器有下載、
  有頭模式要能顯示視窗、指定給它的）。領取時設租約，心跳延長。
- **租約過期**：背景執行緒每隔幾秒檢查，過期的執行標為失敗「worker 失聯」；**不自動重跑**，
  因為可能已經有副作用。之後 worker 才回報的結果一律 409。
- **結果**：上傳的執行目錄（zip）解到 data/runs/<執行編號>/；result.json 的內容照本機的規則寫回
  （包括發布門檻的雜湊比對）；自動登入後的登入狀態傳回角色。
- **邀請與配對**（M10.1，ADR 0014）：裝置頁產生邀請時，舊權杖立刻失效、之前的邀請作廢；
  邀請代碼一次性、24 小時內有效、限定 App 種類，資料庫只存雜湊。App 用代碼呼叫
  Client API 的 ``/pair``，管理 Portal 重新產生權杖交給它。
"""

import hashlib
import logging
import secrets
import shutil
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, cast

from sqlalchemy import CursorResult, delete, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.i18n import Locale, use_locale
from rpa_server import __version__
from rpa_server.domain import (
    DOMAIN_ID,
    LOCAL_WORKER,
    TARGETS,
    Target,
    WorkerRecord,
    WorkerStatus,
    now,
)
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import page_t, t
from rpa_server.jobs import Outcome, RunQueue
from rpa_server.models import DeviceInvite, Recorder, RemoteWorker, Run, Setting
from rpa_server.roles import RoleService
from rpa_server.storage import Storage
from rpa_worker.environment import PROTOCOL, code_fingerprint
from rpa_worker.pairing import INVITE_HOURS
from rpa_worker.protocol import (
    CLAIM_WAIT_SECONDS,
    LEASE_SECONDS,
    ArtifactError,
    JobPayload,
    unpack_directory,
)

__all__ = ["ONLINE_SECONDS", "Invitation", "WorkerHub", "hash_token"]

logger = logging.getLogger("rpa_server.dispatch")

ONLINE_SECONDS: Final = CLAIM_WAIT_SECONDS + 35
"""這麼久內有報到（領取、心跳）就算線上。"""
REAP_SECONDS: Final = 5.0
_STAGES: Final = frozenset({"input", "login", "automation", "verify", "output"})
_DEFAULT_TARGET: Final = "default_target"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _info(row: RemoteWorker) -> dict[str, object]:
    return dict(row.info or {})


@dataclass(frozen=True, slots=True)
class Invitation:
    """剛產生的邀請（M10.1）：代碼只有這時候拿得到，資料庫只存雜湊。"""

    worker: WorkerRecord
    code: str
    app: str
    expires_at: datetime


def _invite_invalid() -> ServiceError:
    return ServiceError(401, "invite_invalid", t("error.invite_invalid"))


class WorkerHub:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: Storage,
        queue: RunQueue,
        roles: RoleService,
        *,
        locale: Locale,
        lease_seconds: float = LEASE_SECONDS,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.queue = queue
        self.roles = roles
        self.locale: Locale = locale
        self.lease_seconds = lease_seconds
        self._condition = threading.Condition()
        self._generation = 0
        self._closing = threading.Event()
        self._reaper: threading.Thread | None = None
        self._fingerprint: str | None = None

    @property
    def fingerprint(self) -> str:
        """管理 Portal 這邊的程式指紋（第一次用到時計算）。"""
        if self._fingerprint is None:
            self._fingerprint = code_fingerprint()
        return self._fingerprint

    # ------------------------------------------------------------ 通知與背景工作

    def notify(self) -> None:
        """有新的執行排入佇列：叫醒等待中的領取。"""
        with self._condition:
            self._generation += 1
            self._condition.notify_all()

    def start_reaper(self) -> None:
        if self._reaper is not None:
            return
        self._closing.clear()
        self._reaper = threading.Thread(target=self._reap_loop, name="worker-leases", daemon=True)
        self._reaper.start()

    def close(self) -> None:
        self._closing.set()
        self.notify()
        if self._reaper is not None:
            self._reaper.join(10)
            self._reaper = None

    def _reap_loop(self) -> None:
        while not self._closing.wait(REAP_SECONDS):
            try:
                with use_locale(self.locale):  # 「worker 失聯」的訊息用伺服器的語言
                    self.expire_leases()
            except Exception:
                logger.exception("檢查 worker 租約失敗")

    # ------------------------------------------------------------ 登記

    @staticmethod
    def _row(session: Session, worker_id: str) -> RemoteWorker:
        row = session.get(RemoteWorker, worker_id)
        if row is None:
            raise not_found("worker_not_found", t("error.worker_not_found", id=worker_id))
        return row

    def _status(self, row: RemoteWorker, moment: datetime) -> WorkerStatus:
        if row.disabled:
            return "disabled"
        seen = row.last_seen_at
        if seen is None or moment - seen > timedelta(seconds=ONLINE_SECONDS):
            return "offline"
        return "busy" if row.current_run else "online"

    def _record(self, row: RemoteWorker, moment: datetime | None = None) -> WorkerRecord:
        info = _info(row)
        browsers = info.get("browsers")
        fingerprint = info.get("fingerprint")
        protocol = info.get("protocol")

        def text(key: str) -> str | None:
            value = info.get(key)
            return str(value) if value else None

        return WorkerRecord(
            id=row.id,
            name=row.name,
            status=self._status(row, moment or now()),
            disabled=row.disabled,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current_run=row.current_run,
            protocol=protocol if isinstance(protocol, int) else None,
            fingerprint=str(fingerprint) if fingerprint else None,
            same_version=not fingerprint or fingerprint == self.fingerprint,
            os=text("os"),
            python=text("python"),
            host=text("host"),
            browsers=tuple(str(item) for item in cast("list[object]", browsers))
            if isinstance(browsers, list)
            else (),
            display=info.get("display") is True,
            version=text("version"),
        )

    def list_workers(self) -> list[WorkerRecord]:
        moment = now()
        with self.sessions() as session:
            rows = session.scalars(select(RemoteWorker).order_by(RemoteWorker.id)).all()
            return [self._record(row, moment) for row in rows]

    def get_worker(self, worker_id: str) -> WorkerRecord:
        with self.sessions() as session:
            return self._record(self._row(session, worker_id))

    def names(self) -> dict[str, str]:
        """worker 代號 → 名稱（報告顯示用；本機是「本機」）。"""
        with self.sessions() as session:
            rows = session.execute(select(RemoteWorker.id, RemoteWorker.name)).all()
        return {LOCAL_WORKER: page_t("worker.local"), **{row[0]: row[1] for row in rows}}

    def has_remote(self) -> bool:
        """有沒有登記（沒停用的）遠端 worker。"""
        with self.sessions() as session:
            row = session.scalars(
                select(RemoteWorker.id).where(RemoteWorker.disabled.is_(False)).limit(1)
            ).first()
            return row is not None

    def remote_display(self) -> bool:
        """有沒有能顯示瀏覽器視窗的遠端 worker（還沒上線過的，先當作可以）。"""
        with self.sessions() as session:
            rows = session.scalars(
                select(RemoteWorker).where(RemoteWorker.disabled.is_(False))
            ).all()
            return any(_info(row).get("display", True) is not False for row in rows)

    def create_worker(self, worker_id: str, name: str | None = None) -> tuple[WorkerRecord, str]:
        """登記一台 worker，回傳 (紀錄, 權杖)。權杖只在這時候拿得到。"""
        worker_id = worker_id.strip()
        if not DOMAIN_ID.fullmatch(worker_id) or worker_id == LOCAL_WORKER:
            raise invalid("worker_id_invalid", t("error.worker_id_invalid", id=worker_id))
        display_name = (name or "").strip() or worker_id
        token = secrets.token_urlsafe(32)
        with self.sessions() as session:
            # 代號和錄製端（M10.2）共用：邀請用代號找裝置
            if (
                session.get(RemoteWorker, worker_id) is not None
                or session.get(Recorder, worker_id) is not None
            ):
                raise conflict("worker_exists", t("error.worker_exists", id=worker_id))
            row = RemoteWorker(
                id=worker_id,
                name=display_name[:100],
                token_hash=hash_token(token),
                disabled=False,
                info={},
                current_run=None,
                created_at=now(),
                last_seen_at=None,
            )
            session.add(row)
            session.commit()
            return self._record(row), token

    def update_worker(
        self, worker_id: str, *, name: str | None = None, disabled: bool | None = None
    ) -> WorkerRecord:
        with self.sessions() as session:
            row = self._row(session, worker_id)
            if name is not None and name.strip():
                row.name = name.strip()[:100]
            if disabled is not None:
                row.disabled = disabled
            session.commit()
            record = self._record(row)
        self.notify()
        return record

    def rotate_token(self, worker_id: str) -> tuple[WorkerRecord, str]:
        """重新產生權杖：舊的立刻失效。"""
        token = secrets.token_urlsafe(32)
        with self.sessions() as session:
            row = self._row(session, worker_id)
            row.token_hash = hash_token(token)
            session.commit()
            return self._record(row), token

    def delete_worker(self, worker_id: str) -> None:
        """刪除 worker：執行中時不行；指定給它的排隊中執行標為失敗。執行紀錄保留。"""
        with self.sessions() as session:
            row = self._row(session, worker_id)
            running = session.scalars(
                select(Run.id).where(Run.worker_id == worker_id, Run.status == "running").limit(1)
            ).first()
            if running is not None:
                raise conflict("worker_busy", t("error.worker_busy", id=worker_id, run=running))
            waiting = session.scalars(
                select(Run.id).where(Run.required_worker == worker_id, Run.status == "queued")
            ).all()
            session.execute(delete(DeviceInvite).where(DeviceInvite.device_id == worker_id))
            session.delete(row)
            session.commit()
        for run_id in waiting:
            self.queue.fail_run(run_id, t("run.worker_removed", worker=worker_id))

    # ------------------------------------------------------------ 邀請與配對（M10.1）

    def create_invite(self, worker_id: str) -> Invitation:
        """產生這台 worker 的邀請：舊權杖立刻失效，之前的邀請作廢。停用中的 worker 不能邀請。"""
        code = secrets.token_urlsafe(24)
        moment = now()
        expires = moment + timedelta(hours=INVITE_HOURS)
        with self.sessions() as session:
            row = self._row(session, worker_id)
            if row.disabled:
                raise conflict("worker_disabled", t("error.worker_disabled", id=worker_id))
            # 沒有人拿得到這個權杖：配對時才產生真正交給 App 的權杖
            row.token_hash = hash_token(secrets.token_urlsafe(32))
            session.execute(
                delete(DeviceInvite).where(
                    or_(DeviceInvite.device_id == worker_id, DeviceInvite.expires_at <= moment)
                )
            )
            session.add(
                DeviceInvite(
                    code_hash=hash_token(code),
                    app="worker",
                    device_id=worker_id,
                    created_at=moment,
                    expires_at=expires,
                    used_at=None,
                )
            )
            session.commit()
            record = self._record(row, moment)
        return Invitation(worker=record, code=code, app="worker", expires_at=expires)

    def pair(self, code: str, app: str) -> dict[str, object]:
        """Client API 的配對：邀請代碼換權杖。代碼只能用一次；App 種類不對時代碼保留。

        Worker 的權杖存在 workers，錄製端（M10.2）的存在 recorders；邀請記著是哪一種。
        """
        digest = hash_token(code.strip())
        moment = now()
        token = secrets.token_urlsafe(32)
        with self.sessions() as session:
            invite = session.get(DeviceInvite, digest)
            if invite is None or invite.used_at is not None:
                raise _invite_invalid()
            if invite.expires_at <= moment:
                raise ServiceError(
                    401, "invite_expired", t("error.invite_expired", hours=INVITE_HOURS)
                )
            if invite.app != app:
                raise conflict(
                    "invite_wrong_app",
                    t("error.invite_wrong_app", app=t("device.app_" + invite.app)),
                    app=invite.app,
                )
            model = Recorder if invite.app == "recorder" else RemoteWorker
            row = session.get(model, invite.device_id)
            if row is None:
                raise _invite_invalid()
            if row.disabled:
                raise conflict("worker_disabled", t("error.worker_disabled", id=row.id))
            used = cast(
                "CursorResult[Any]",
                session.execute(
                    update(DeviceInvite)
                    .where(DeviceInvite.code_hash == digest, DeviceInvite.used_at.is_(None))
                    .values(used_at=moment)
                ),
            )
            if used.rowcount != 1:  # 同一個代碼同時被用了兩次
                session.rollback()
                raise _invite_invalid()
            row.token_hash = hash_token(token)
            session.commit()
            device, name = row.id, row.name
        logger.info("裝置 %s 已配對（%s）", device, app)
        return {
            "device": device,
            "name": name,
            "app": app,
            "token": token,
            "server": {
                "protocol": PROTOCOL,
                "fingerprint": self.fingerprint,
                "version": __version__,
            },
        }

    # ------------------------------------------------------------ 設定

    def default_target(self) -> Target:
        """預設執行位置；沒設定過是本機（跟沒有遠端 worker 時一樣）。"""
        with self.sessions() as session:
            row = session.get(Setting, _DEFAULT_TARGET)
            value = row.value.get("value") if row is not None else None
        return value if value in TARGETS else "local"

    def set_default_target(self, target: str) -> Target:
        if target not in TARGETS:
            raise invalid("target_invalid", t("error.target_invalid", target=target))
        with self.sessions() as session:
            row = session.get(Setting, _DEFAULT_TARGET)
            if row is None:
                session.add(Setting(key=_DEFAULT_TARGET, value={"value": target}))
            else:
                row.value = {"value": target}
            session.commit()
        return target

    # ------------------------------------------------------------ Worker API

    def authenticate(self, token: str | None) -> str:
        """權杖 → worker 代號；沒有、不對或已停用時拋出 401。"""
        if token:
            with self.sessions() as session:
                row = session.scalars(
                    select(RemoteWorker).where(RemoteWorker.token_hash == hash_token(token))
                ).first()
                if row is not None and not row.disabled:
                    return row.id
        raise ServiceError(401, "worker_unauthorized", t("error.worker_unauthorized"))

    def _touch(self, session: Session, worker_id: str) -> RemoteWorker:
        row = self._row(session, worker_id)
        row.last_seen_at = now()
        return row

    def hello(self, worker_id: str, info: Mapping[str, object]) -> dict[str, object]:
        protocol = info.get("protocol")
        if protocol != PROTOCOL:
            raise conflict(
                "protocol_mismatch",
                t("error.worker_protocol", worker=protocol, server=PROTOCOL),
            )
        keys = ("protocol", "fingerprint", "os", "python", "host", "browsers", "display", "version")
        with self.sessions() as session:
            row = self._touch(session, worker_id)
            row.info = {key: info.get(key) for key in keys}
            # 剛上線的 worker 不會有執行中的任務（上一次的已經被它放棄或標為失聯）
            current = row.current_run
            if current is not None:
                run = session.get(Run, current)
                if run is None or run.status != "running" or run.worker_id != worker_id:
                    row.current_run = None
            session.commit()
            name = row.name
        return {
            "worker": worker_id,
            "name": name,
            "protocol": PROTOCOL,
            "fingerprint": self.fingerprint,
            "leaseSeconds": self.lease_seconds,
        }

    def _capabilities(self, worker_id: str) -> tuple[set[str] | None, bool]:
        with self.sessions() as session:
            info = _info(self._touch(session, worker_id))
            session.commit()
        browsers = info.get("browsers")
        engines = (
            {str(item) for item in cast("list[object]", browsers)}
            if isinstance(browsers, list) and browsers
            else None
        )
        return engines, info.get("display") is not False

    def claim(
        self, worker_id: str, wait_seconds: float = CLAIM_WAIT_SECONDS
    ) -> dict[str, object] | None:
        """長輪詢領取一個任務；等到 wait_seconds 都沒有就回傳 None。"""
        deadline = time.monotonic() + max(0.0, min(wait_seconds, CLAIM_WAIT_SECONDS))
        while not self._closing.is_set():
            with self._condition:
                generation = self._generation
            engines, display = self._capabilities(worker_id)

            def accepts(
                run: Run, engines: set[str] | None = engines, display: bool = display
            ) -> bool:
                if not run.headless and not display:
                    return False
                return engines is None or self.queue.engine_of(run) in engines

            lease = now() + timedelta(seconds=self.lease_seconds)
            run = self.queue.claim_run(
                worker_id, ("remote", "any"), accepts=accepts, lease_until=lease
            )
            if run is not None:
                payload = self._payload(run)
                if payload is not None:
                    self._set_current(worker_id, run.id)
                    return payload
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            with self._condition:
                if self._generation == generation:
                    self._condition.wait(min(remaining, REAP_SECONDS))
        return None

    def _set_current(self, worker_id: str, run_id: str | None) -> None:
        with self.sessions() as session:
            row = session.get(RemoteWorker, worker_id)
            if row is not None:
                row.current_run = run_id
                session.commit()

    def _payload(self, run: Run) -> dict[str, object] | None:
        """把執行打包成任務；版本的檔案讀不到時，執行標為失敗並回傳 None。"""
        try:
            folder = self.storage.revision_dir(run.scene_id, run.revision_number)
            files = {
                path.relative_to(folder).as_posix(): path.read_bytes()
                for path in sorted(folder.rglob("*"))
                if path.is_file()
            }
            if not files:
                raise FileNotFoundError(folder)
            login, values = self.queue.extras(run.scene_id, run.revision_number)
            state = None
            if login is not None and login.state.exists():
                state = login.state.read_bytes()
            payload = JobPayload(
                run_id=run.id,
                files=files,
                inputs=dict(run.input),
                engine=run.engine,
                base_url=run.base_url,
                headless=run.headless,
                locale=self.locale,
                login=login,
                login_state=state,
                secrets=values,
            )
        except Exception as error:
            logger.exception("無法打包任務 %s", run.id)
            self.queue.fail_run(run.id, t("run.crashed", detail=f"{type(error).__name__}: {error}"))
            return None
        return payload.to_json()

    def _owned_run(self, session: Session, worker_id: str, run_id: str) -> Run:
        run = session.get(Run, run_id)
        if run is None or run.worker_id != worker_id or run.status != "running":
            raise conflict("run_not_assigned", t("error.run_not_assigned", id=run_id))
        return run

    def heartbeat(self, worker_id: str, run_id: str, stage: str | None = None) -> dict[str, object]:
        """執行中的報到：延長租約、記下階段；回傳要不要取消。"""
        with self.sessions() as session:
            self._touch(session, worker_id)
            try:
                run = self._owned_run(session, worker_id, run_id)
            except ServiceError:
                session.commit()
                raise
            run.lease_until = now() + timedelta(seconds=self.lease_seconds)
            if stage in _STAGES:
                run.stage = stage
            cancel = run.cancel_requested
            session.commit()
        return {"cancel": cancel}

    def store_artifacts(self, worker_id: str, run_id: str, archive: Path) -> list[str]:
        """上傳的執行目錄：先解到暫存資料夾，成功了才換上（重送時覆蓋上一次的）。"""
        with self.sessions() as session:
            self._owned_run(session, worker_id, run_id)
        temporary = self.storage.runs / f".upload-{run_id}-{uuid.uuid4().hex[:8]}"
        try:
            names = unpack_directory(archive, temporary)
        except ArtifactError as error:
            raise invalid(
                "artifacts_invalid", t("error.artifacts_invalid", detail=str(error))
            ) from None
        target = self.storage.run_dir(run_id)
        shutil.rmtree(target, ignore_errors=True)
        temporary.replace(target)
        return names

    def store_role_state(self, worker_id: str, run_id: str, data: bytes) -> None:
        """自動登入後的登入狀態：只接受這次執行的場景所用的角色。"""
        with self.sessions() as session:
            run = self._owned_run(session, worker_id, run_id)
            scene_id, number = run.scene_id, run.revision_number
        scenario = self.queue.scenario(scene_id, number)
        if scenario is None or scenario.login is None:
            raise conflict("run_without_login", t("error.run_without_login", id=run_id))
        try:
            self.roles.save_state(scenario.login.role, data)
        except (ValueError, UnicodeDecodeError) as error:
            raise invalid(
                "role_state_invalid", t("error.role_state_invalid", detail=str(error))
            ) from None

    def finish(self, worker_id: str, run_id: str, result: Mapping[str, object]) -> None:
        try:
            outcome = Outcome.from_json(result)
        except ValueError as error:
            raise invalid("result_invalid", t("error.result_invalid", detail=str(error))) from None
        if not self.queue.complete(run_id, outcome, worker_id=worker_id):
            raise conflict("run_not_assigned", t("error.run_not_assigned", id=run_id))
        self._set_current(worker_id, None)

    def fail(self, worker_id: str, run_id: str, kind: str, detail: str) -> None:
        if kind == "scenario_invalid":
            try:
                count = int(detail)
            except ValueError:
                count = 1
            message = t("run.scenario_invalid", count=count)
        else:
            message = t("run.crashed", detail=detail[:2000])
        if not self.queue.fail_run(run_id, message, worker_id=worker_id):
            raise conflict("run_not_assigned", t("error.run_not_assigned", id=run_id))
        self._set_current(worker_id, None)

    # ------------------------------------------------------------ 租約

    def expire_leases(self) -> int:
        """租約過期的遠端執行標為失敗（worker 失聯）。回傳處理了幾個。"""
        moment = now()
        with self.sessions() as session:
            expired = session.execute(
                select(Run.id, Run.worker_id).where(
                    Run.status == "running",
                    Run.lease_until.is_not(None),
                    Run.lease_until < moment,
                )
            ).all()
        names = self.names() if expired else {}
        count = 0
        for run_id, worker_id in expired:
            name = names.get(worker_id or "", worker_id or "?")
            if self.queue.fail_run(run_id, t("run.worker_lost", worker=name), worker_id=worker_id):
                count += 1
            with self.sessions() as session:
                session.execute(
                    update(RemoteWorker)
                    .where(RemoteWorker.current_run == run_id)
                    .values(current_run=None)
                )
                session.commit()
        return count

    def resume_after_restart(self) -> int:
        """管理 Portal 重新啟動：遠端執行中的任務給 worker 一次租約的時間重新報到。"""
        lease = now() + timedelta(seconds=self.lease_seconds)
        with self.sessions() as session:
            result = session.execute(
                update(Run)
                .where(
                    Run.status == "running",
                    Run.worker_id.is_not(None),
                    Run.worker_id != LOCAL_WORKER,
                )
                .values(lease_until=lease)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
