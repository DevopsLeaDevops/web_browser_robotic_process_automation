"""錄製端（M10.2，ADR 0014）：登記、邀請、上線，以及交給它執行的互動子程序。

- **登記與邀請**：和 worker 一樣在裝置頁新增、產生邀請（一次性、24 小時內有效）；錄製端用
  邀請代碼換權杖（:meth:`rpa_server.dispatch.WorkerHub.pair`，``app=recorder``）。代號和 worker
  共用命名空間。權杖只存雜湊。
- **Portal**：對外埠上的頁面與 API 要錄製端的權杖（:class:`rpa_server.middleware.PortGateMiddleware`
  用 :meth:`RecorderHub.authenticate` 驗證），驗過的請求記在 :mod:`rpa_server.context`。
  叢集管理與管理後台的選單預設不顯示，裝置頁可以替個別錄製端打開（``menus``，三段分工）。
- **互動子程序**：錄製、逐步調試、人工登入在請求透過錄製端進來時，改用 :meth:`RecorderHub.launcher`
  啟動。它和本機的 :func:`rpa_server.processes.launch` 介面相同，回傳的 :class:`RemoteProcess`
  也像 ``subprocess.Popen``，所以三個服務讀輸出、送命令、等結束的程式都不用改。
  指令、檔案與輸出的格式見 :mod:`rpa_worker.interactive`。
- **App 太舊**（M7a）：錄製端上線時回報看得懂的 DSL 擴充（``features``）。交給它的場景或登入設定
  用到它不懂的（例如 iframe 的 ``frame``）時，:meth:`RecorderHub.check` 直接說明要更新 RPA 錄製端，
  不讓舊 App 只回一句「場景校驗失敗」。
- **失聯**：超過 :data:`rpa_worker.interactive.LOST_SECONDS` 沒有輪詢、錄製端重新啟動、
  停用或刪除時，它的子程序視為結束（結束碼 :data:`LOST_EXIT`，日誌最後加一行原因）。

這一層的狀態（指令佇列、子程序）只在記憶體：管理 Portal 重新啟動後，錄製端的子程序在下一次
回報輸出時得到 404，錄製端自己結束它們；上線時拿到新的通道代號，指令序號從 0 重新開始。
錄製端每次輪詢附上正在執行的子程序，確認收到「啟動」卻不在裡面的也視為結束。
"""

import logging
import secrets
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, cast

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl.features import missing_features
from rpa_core.i18n import Locale, use_locale
from rpa_runner.commands import FROZEN_MODULE
from rpa_runner.run import ENV_STORAGE_STATE
from rpa_server.config import RECORDER_MENUS
from rpa_server.context import Via, via_recorder
from rpa_server.dispatch import hash_token, reported_names
from rpa_server.domain import DOMAIN_ID, LOCAL_WORKER, RecorderRecord, RecorderStatus, now
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.models import DeviceInvite, Recorder, RemoteWorker
from rpa_server.processes import ChildEnv, ChildProcess, Launch
from rpa_worker.environment import PROTOCOL, code_fingerprint
from rpa_worker.interactive import (
    CONTROL_WAIT_SECONDS,
    INPUTS,
    LOST_SECONDS,
    WORK,
    SyncError,
    b64encode,
    unpack_files,
)
from rpa_worker.pairing import INVITE_HOURS

__all__ = ["LOST_EXIT", "Invitation", "RecorderHub", "RemoteProcess"]

logger = logging.getLogger("rpa_server.devices")

LOST_EXIT: Final = -1001
"""錄製端失聯、重新啟動或被停用時，它的子程序的結束碼。"""
REAP_SECONDS: Final = 5.0
_SEEN_WRITE_SECONDS: Final = 10.0
"""輪詢很頻繁：最後上線時間最多這麼久寫一次資料庫。"""
MAX_INPUT_BYTES: Final = 20 * 1024 * 1024
"""啟動時送給錄製端的檔案（場景、入參、登入狀態）最多這麼大。"""


@dataclass(frozen=True, slots=True)
class Invitation:
    """剛產生的錄製端邀請：代碼只有這時候拿得到。"""

    recorder: RecorderRecord
    code: str
    expires_at: datetime


# ---------------------------------------------------------------- 子程序


class _Stdin:
    """寫到錄製端子程序的標準輸入：一行一個指令。"""

    def __init__(self, process: "RemoteProcess") -> None:
        self._process = process
        self._buffer = ""
        self._closed = False

    def write(self, s: str, /) -> int:
        if self._closed:
            raise ValueError("I/O operation on closed file")
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._process.command({"type": "input", "line": line})
        return len(s)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._process.command({"type": "close"})


class _Stdout:
    """錄製端傳回的標準輸出，一行一個；子程序結束後迭代結束。"""

    def __init__(self) -> None:
        self._lines: deque[str] = deque()
        self._closed = False
        self._condition = threading.Condition()

    def put(self, lines: Sequence[str]) -> None:
        with self._condition:
            self._lines.extend(line.rstrip("\n") + "\n" for line in lines)
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def __iter__(self) -> "_Stdout":
        return self

    def __next__(self) -> str:
        with self._condition:
            while not self._lines and not self._closed:
                self._condition.wait()
            if self._lines:
                return self._lines.popleft()
            raise StopIteration


class RemoteProcess:
    """在錄製端執行的子程序，介面是 :class:`rpa_server.processes.ChildProcess`。"""

    def __init__(
        self,
        hub: "RecorderHub",
        device: str,
        process_id: str,
        *,
        workdir: Path,
        log: Path,
        pipes: bool,
    ) -> None:
        self.hub = hub
        self.device = device
        self.id = process_id
        self.workdir = workdir
        self.log = log
        self.pid = 0
        """錄製端的程序沒有這台的 pid；結束改用 :meth:`kill_tree`。"""
        self._stdin = _Stdin(self) if pipes else None
        self._stdout = _Stdout() if pipes else None
        self._returncode: int | None = None
        self._done = threading.Event()
        self._lock = threading.Lock()
        self.start_seq: int | None = None
        """「啟動」指令的序號：錄製端確認收到之後，還在跑的清單裡沒有它就是不見了。"""

    @property
    def stdin(self) -> _Stdin | None:
        return self._stdin

    @property
    def stdout(self) -> _Stdout | None:
        return self._stdout

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        if not self._done.wait(timeout):
            raise subprocess.TimeoutExpired(f"{self.device}:{self.id}", timeout or 0)
        return cast("int", self._returncode)

    def command(self, values: Mapping[str, object]) -> None:
        """送一個指令給錄製端（結束了就不送）。"""
        if self._returncode is None:
            self.hub.enqueue(self.device, {**values, "process": self.id})

    def kill_tree(self) -> None:
        """請錄製端結束這個子程序與它開的瀏覽器。"""
        self.command({"type": "kill"})

    # 由 Client API 呼叫 ------------------------------------------------

    def deliver(self, lines: Sequence[str]) -> None:
        if self._stdout is not None and self._returncode is None:
            self._stdout.put(lines)

    def finish(self, code: int, message: str | None = None) -> bool:
        """子程序結束（錄製端回報結束碼，或失聯）；已經結束過時回傳 False。"""
        with self._lock:
            if self._returncode is not None:
                return False
            self._returncode = code
        if message:
            try:
                self.log.parent.mkdir(parents=True, exist_ok=True)
                with self.log.open("a", encoding="utf-8") as handle:
                    handle.write(f"\n{message}\n")
            except OSError:
                logger.warning("寫不進日誌 %s", self.log)
        if self._stdout is not None:
            self._stdout.close()
        self._done.set()
        return True


# ---------------------------------------------------------------- 指令通道


@dataclass(slots=True)
class _Channel:
    """一台錄製端的指令佇列與最近的輪詢。"""

    boot: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """通道的代號：管理 Portal 重新啟動或通道重建時換掉；錄製端看到不同的代號就從序號 0 開始。"""
    seq: int = 0
    pending: deque[tuple[int, dict[str, object]]] = field(
        default_factory=deque[tuple[int, dict[str, object]]]
    )
    last_poll: float | None = None
    """最近一次輪詢（time.monotonic）；None 代表這次啟動以來還沒連上。"""
    seen_written: float = 0.0
    info: dict[str, object] = field(default_factory=dict[str, object])


def _module(command: Sequence[str]) -> tuple[str, list[str]]:
    """``python -m 模組 …`` 或打包後的 ``App --rpa-module 模組 …`` → (模組, 參數)。"""
    if len(command) >= 3 and command[1] in ("-m", FROZEN_MODULE):
        return command[2], list(command[3:])
    raise ValueError(f"not a module command: {command[:3]}")


_PATH_ENV: Final = frozenset({ENV_STORAGE_STATE})
"""值是伺服器路徑的環境變數：換成錄製端的工作資料夾。其他（Secrets、語言）原樣送出。"""


class _Translator:
    """把參數、環境變數裡伺服器的路徑換成錄製端的工作資料夾，並收集要送過去的檔案。"""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir.absolute()
        self._resolved = workdir.resolve()
        self.files: dict[str, bytes] = {}
        self._outside: dict[Path, str] = {}

    def relative(self, path: Path) -> str | None:
        """工作資料夾裡的相對路徑（``.`` 是資料夾本身）；在外面時是 None。符號連結也考慮。"""
        for candidate, root in ((path, self.workdir), (path.resolve(), self._resolved)):
            try:
                return candidate.relative_to(root).as_posix()
            except ValueError:
                continue
        return None

    def __call__(self, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            return value
        relative = self.relative(path)
        if relative is None:
            if not path.is_file():
                return value
            name = self._outside.get(path)
            if name is None:
                name = f"{INPUTS}/{len(self._outside)}-{path.name}"
                self._outside[path] = name
                self.files[name] = path.read_bytes()
            return f"{WORK}/{name}"
        if relative == ".":
            return WORK
        if path.is_file():
            self.files[relative] = path.read_bytes()
        return f"{WORK}/{relative}"


def _menus(value: Collection[str] | None) -> tuple[str, ...]:
    """另外顯示的選單：只留 RECORDER_MENUS 裡有的，依它的順序（資料庫裡可能是空的或舊的值）。"""
    chosen = set(value or ())
    return tuple(menu for menu in RECORDER_MENUS if menu in chosen)


class RecorderHub:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        locale: Locale,
        lost_seconds: float = LOST_SECONDS,
    ) -> None:
        self.sessions = sessions
        self.locale: Locale = locale
        self.lost_seconds = lost_seconds
        self._lock = threading.Condition()
        self._channels: dict[str, _Channel] = {}
        self._processes: dict[str, RemoteProcess] = {}
        self._closing = threading.Event()
        self._reaper: threading.Thread | None = None
        self._fingerprint: str | None = None

    @property
    def fingerprint(self) -> str:
        if self._fingerprint is None:
            self._fingerprint = code_fingerprint()
        return self._fingerprint

    # ------------------------------------------------------------ 背景工作

    def start_reaper(self) -> None:
        if self._reaper is not None:
            return
        self._reaper = threading.Thread(target=self._reap_loop, name="recorder-reaper", daemon=True)
        self._reaper.start()

    def close(self) -> None:
        """管理 Portal 關閉：錄製端的子程序都視為結束。"""
        self._closing.set()
        with self._lock:
            processes = list(self._processes.values())
            self._lock.notify_all()
        for process in processes:
            self._lose(process, "error.recorder_server_stopped")

    def _reap_loop(self) -> None:
        while not self._closing.wait(REAP_SECONDS):
            try:
                self.reap()
            except Exception:
                logger.exception("檢查錄製端失聯時出錯")

    def reap(self) -> int:
        """把太久沒有輪詢的錄製端的子程序視為結束；回傳處理了幾個。"""
        moment = time.monotonic()
        with self._lock:
            lost = [
                process
                for process in self._processes.values()
                if (last := self._channels.get(process.device, _Channel()).last_poll) is None
                or moment - last > self.lost_seconds
            ]
        for process in lost:
            self._lose(process, "error.recorder_lost")
        return len(lost)

    def _lose(self, process: RemoteProcess, key: str) -> None:
        with use_locale(self.locale):
            message = t(key, name=process.device)
        if process.finish(LOST_EXIT, message):
            logger.warning("錄製端 %s 的子程序 %s 視為結束：%s", process.device, process.id, key)
        # 錄製端如果之後連回來，請它結束殘留的子程序
        self.enqueue(process.device, {"type": "kill", "process": process.id})
        with self._lock:
            self._processes.pop(process.id, None)

    # ------------------------------------------------------------ 登記

    @staticmethod
    def _row(session: Session, recorder_id: str) -> Recorder:
        row = session.get(Recorder, recorder_id)
        if row is None:
            raise not_found("recorder_not_found", t("error.recorder_not_found", id=recorder_id))
        return row

    def _status(self, row: Recorder, active: int) -> RecorderStatus:
        if row.disabled:
            return "disabled"
        if not self.online(row.id):
            return "offline"
        return "busy" if active else "online"

    def _record(self, row: Recorder) -> RecorderRecord:
        with self._lock:
            channel = self._channels.get(row.id)
            info = dict(channel.info) if channel is not None and channel.info else dict(row.info)
            active = sum(1 for item in self._processes.values() if item.device == row.id)
        browsers = info.get("browsers")
        fingerprint = info.get("fingerprint")
        protocol = info.get("protocol")

        def text(key: str) -> str | None:
            value = info.get(key)
            return str(value) if value else None

        return RecorderRecord(
            id=row.id,
            name=row.name,
            status=self._status(row, active),
            disabled=row.disabled,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            protocol=protocol if isinstance(protocol, int) else None,
            fingerprint=str(fingerprint) if fingerprint else None,
            same_version=not fingerprint or fingerprint == self.fingerprint,
            version=text("version"),
            os=text("os"),
            host=text("host"),
            browsers=tuple(str(item) for item in cast("list[object]", browsers))
            if isinstance(browsers, list)
            else (),
            display=info.get("display") is not False,
            active=active,
            features=reported_names(info.get("features")),
            menus=_menus(row.menus),
        )

    def list_recorders(self) -> list[RecorderRecord]:
        with self.sessions() as session:
            rows = session.scalars(select(Recorder).order_by(Recorder.id)).all()
            return [self._record(row) for row in rows]

    def get_recorder(self, recorder_id: str) -> RecorderRecord:
        with self.sessions() as session:
            return self._record(self._row(session, recorder_id))

    def create_recorder(self, recorder_id: str, name: str | None = None) -> RecorderRecord:
        """登記一台錄製端；權杖要用邀請配對才拿得到。"""
        recorder_id = recorder_id.strip()
        if not DOMAIN_ID.fullmatch(recorder_id) or recorder_id == LOCAL_WORKER:
            raise invalid("worker_id_invalid", t("error.worker_id_invalid", id=recorder_id))
        display_name = (name or "").strip() or recorder_id
        with self.sessions() as session:
            if (
                session.get(Recorder, recorder_id) is not None
                or session.get(RemoteWorker, recorder_id) is not None
            ):
                raise conflict("worker_exists", t("error.worker_exists", id=recorder_id))
            row = Recorder(
                id=recorder_id,
                name=display_name[:100],
                # 沒有人拿得到這個權杖：配對時才產生真正交給錄製端的權杖
                token_hash=hash_token(secrets.token_urlsafe(32)),
                disabled=False,
                info={},
                created_at=now(),
                last_seen_at=None,
            )
            session.add(row)
            session.commit()
            return self._record(row)

    def update_recorder(
        self,
        recorder_id: str,
        *,
        name: str | None = None,
        disabled: bool | None = None,
        menus: Collection[str] | None = None,
    ) -> RecorderRecord:
        """改名稱、停用，或設定透過這台時另外顯示的選單（RECORDER_MENUS 中的哪些）。"""
        with self.sessions() as session:
            row = self._row(session, recorder_id)
            if name is not None and name.strip():
                row.name = name.strip()[:100]
            if disabled is not None:
                row.disabled = disabled
            if menus is not None:
                unknown = sorted(set(menus) - set(RECORDER_MENUS))
                if unknown:
                    raise invalid(
                        "recorder_menu_invalid",
                        t("error.recorder_menu_invalid", menus=", ".join(unknown)),
                    )
                row.menus = list(_menus(menus))
            session.commit()
            record = self._record(row)
        if disabled:
            self._drop(recorder_id, "error.recorder_disabled")
        return record

    def delete_recorder(self, recorder_id: str) -> None:
        with self.sessions() as session:
            row = self._row(session, recorder_id)
            session.execute(delete(DeviceInvite).where(DeviceInvite.device_id == recorder_id))
            session.delete(row)
            session.commit()
        self._drop(recorder_id, "error.recorder_removed")
        with self._lock:
            self._channels.pop(recorder_id, None)

    def _drop(self, recorder_id: str, key: str) -> None:
        """停用、刪除、重新邀請：這台的子程序都結束。"""
        with self._lock:
            processes = [item for item in self._processes.values() if item.device == recorder_id]
        for process in processes:
            self._lose(process, key)
        with self._lock:
            channel = self._channels.get(recorder_id)
            if channel is not None:
                channel.last_poll = None
            self._lock.notify_all()

    def create_invite(self, recorder_id: str) -> Invitation:
        """產生這台錄製端的邀請：舊權杖立刻失效，之前的邀請作廢，進行中的子程序結束。"""
        code = secrets.token_urlsafe(24)
        moment = now()
        expires = moment + timedelta(hours=INVITE_HOURS)
        with self.sessions() as session:
            row = self._row(session, recorder_id)
            if row.disabled:
                raise conflict("worker_disabled", t("error.worker_disabled", id=recorder_id))
            row.token_hash = hash_token(secrets.token_urlsafe(32))
            session.execute(
                delete(DeviceInvite).where(
                    or_(DeviceInvite.device_id == recorder_id, DeviceInvite.expires_at <= moment)
                )
            )
            session.add(
                DeviceInvite(
                    code_hash=hash_token(code),
                    app="recorder",
                    device_id=recorder_id,
                    created_at=moment,
                    expires_at=expires,
                    used_at=None,
                )
            )
            session.commit()
            record = self._record(row)
        self._drop(recorder_id, "error.recorder_reinvited")
        return Invitation(recorder=record, code=code, expires_at=expires)

    # ------------------------------------------------------------ 權杖與上線

    def authenticate(self, token: str | None) -> Via:
        """權杖 → 錄製端；沒有、不對或已停用時拋出 401。"""
        if token:
            with self.sessions() as session:
                row = session.scalars(
                    select(Recorder).where(Recorder.token_hash == hash_token(token))
                ).first()
                if row is not None and not row.disabled:
                    return Via(row.id, row.name, _menus(row.menus))
        raise ServiceError(401, "recorder_unauthorized", t("error.recorder_unauthorized"))

    def online(self, recorder_id: str) -> bool:
        """這次管理 Portal 啟動以來連上過，而且最近有輪詢。"""
        with self._lock:
            channel = self._channels.get(recorder_id)
            last = channel.last_poll if channel is not None else None
        return last is not None and time.monotonic() - last <= self.lost_seconds

    def hello(self, recorder_id: str, info: Mapping[str, object]) -> dict[str, object]:
        """錄製端上線：協定版本不同就拒絕；換了啟動代號（App 重新啟動）時，舊的子程序都結束。"""
        protocol = info.get("protocol")
        if protocol != PROTOCOL:
            raise conflict(
                "protocol_mismatch",
                t("error.recorder_protocol", recorder=protocol, server=PROTOCOL),
            )
        values = {
            key: info[key]
            for key in (
                "protocol",
                "fingerprint",
                "version",
                "os",
                "host",
                "browsers",
                "display",
                "features",
            )
            if key in info
        }
        boot = str(info.get("boot") or "")
        with self._lock:
            channel = self._channels.setdefault(recorder_id, _Channel())
            restarted = channel.boot is not None and channel.boot != boot
            channel.boot = boot
            channel.info = dict(values)
            channel.last_poll = time.monotonic()
            if restarted:
                channel.pending.clear()
            stale = [item for item in self._processes.values() if item.device == recorder_id]
        if restarted:
            for process in stale:
                self._lose(process, "error.recorder_restarted")
        with self.sessions() as session:
            row = self._row(session, recorder_id)
            row.info = dict(values)
            row.last_seen_at = now()
            session.commit()
        with self._lock:
            channel_id, seq = channel.id, channel.seq
        return {
            "device": recorder_id,
            "channel": channel_id,
            "seq": seq,
            "protocol": PROTOCOL,
            "fingerprint": self.fingerprint,
            "sameVersion": not values.get("fingerprint")
            or values.get("fingerprint") == self.fingerprint,
        }

    # ------------------------------------------------------------ 指令

    def enqueue(self, recorder_id: str, command: Mapping[str, object]) -> int:
        with self._lock:
            channel = self._channels.setdefault(recorder_id, _Channel())
            channel.seq += 1
            channel.pending.append((channel.seq, dict(command)))
            self._lock.notify_all()
            return channel.seq

    def poll(
        self,
        recorder_id: str,
        after: int,
        wait: float = CONTROL_WAIT_SECONDS,
        running: Collection[str] | None = None,
    ) -> dict[str, object]:
        """長輪詢：丟掉已經處理到 ``after`` 的指令，回傳還沒處理的（沒有就等到有或逾時）。

        ``running`` 是錄製端正在執行的子程序：確認收到「啟動」之後卻不在裡面的（啟動失敗沒回報到、
        處理指令時出錯），視為結束，不讓服務一直等下去。
        """
        deadline = time.monotonic() + max(0.0, min(wait, CONTROL_WAIT_SECONDS))
        write_seen = False
        with self._lock:
            channel = self._channels.get(recorder_id)
            if channel is None or channel.boot is None or after > channel.seq:
                # 序號比這邊發過的還大：錄製端以為還是上一次的通道（例如管理 Portal 重新啟動過）
                raise conflict("recorder_hello_first", t("error.recorder_hello_first"))
            gone: list[RemoteProcess] = []
            if running is not None:
                still = set(running)
                gone = [
                    process
                    for process in self._processes.values()
                    if process.device == recorder_id
                    and process.start_seq is not None
                    and process.start_seq <= after
                    and process.id not in still
                ]
        for process in gone:
            self._lose(process, "error.recorder_process_gone")
        with self._lock:
            channel = self._channels.get(recorder_id)
            if channel is None:
                raise conflict("recorder_hello_first", t("error.recorder_hello_first"))
            while True:
                channel.last_poll = time.monotonic()
                while channel.pending and channel.pending[0][0] <= after:
                    channel.pending.popleft()
                if channel.pending or self._closing.is_set():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._lock.wait(min(remaining, REAP_SECONDS))
                if self._channels.get(recorder_id) is not channel:  # 刪除了
                    break
            commands = [{"seq": seq, **command} for seq, command in channel.pending]
            if time.monotonic() - channel.seen_written >= _SEEN_WRITE_SECONDS:
                channel.seen_written = time.monotonic()
                write_seen = True
        if write_seen:
            with self.sessions() as session:
                row = session.get(Recorder, recorder_id)
                if row is not None:
                    row.last_seen_at = now()
                    session.commit()
        return {"commands": commands}

    # ------------------------------------------------------------ 子程序

    def _process(self, recorder_id: str, process_id: str) -> RemoteProcess:
        with self._lock:
            process = self._processes.get(process_id)
        if process is None or process.device != recorder_id:
            raise not_found("process_not_found", t("error.process_not_found", id=process_id))
        return process

    def output(
        self,
        recorder_id: str,
        process_id: str,
        lines: Sequence[str],
        exit_code: int | None,
        error: str | None = None,
    ) -> None:
        process = self._process(recorder_id, process_id)
        process.deliver(lines)
        if exit_code is not None:
            process.finish(exit_code, error)
            with self._lock:
                self._processes.pop(process_id, None)

    def store_files(self, recorder_id: str, process_id: str, archive: Path) -> list[str]:
        process = self._process(recorder_id, process_id)
        try:
            return unpack_files(archive, process.workdir)
        except SyncError as error:
            raise invalid("files_invalid", t("error.files_invalid", detail=str(error))) from None

    def display(self, via: Via) -> bool:
        """這台錄製端能不能顯示瀏覽器視窗（還沒回報時當作可以）。"""
        with self._lock:
            channel = self._channels.get(via.id)
            return channel is None or channel.info.get("display") is not False

    def check(
        self,
        via: Via,
        *,
        engine: str | None = None,
        headed: bool = True,
        features: Collection[str] = (),
    ) -> None:
        """要交給這台錄製端之前：上線中、能顯示視窗、有這個瀏覽器、看得懂要用到的 DSL 擴充
        （``features``，見 :mod:`rpa_core.dsl.features`）；不行就拋出說明。"""
        if not self.online(via.id):
            raise conflict("recorder_offline", t("error.recorder_offline", name=via.name))
        with self._lock:
            channel = self._channels.get(via.id)
            info = dict(channel.info) if channel is not None else {}
        if headed and info.get("display") is False:
            raise invalid("display_unavailable", t("error.recorder_no_display", name=via.name))
        browsers = info.get("browsers")
        if engine is not None and isinstance(browsers, list) and engine not in browsers:
            raise invalid(
                "recorder_browser_missing",
                t("error.recorder_browser_missing", name=via.name, engine=engine),
            )
        missing = missing_features(features, info.get("features"))
        if missing:
            raise invalid(
                "recorder_outdated",
                t("error.recorder_outdated", name=via.name, features=", ".join(missing)),
            )

    def launcher(self, via: Via) -> Launch:
        """交給這台錄製端執行的啟動函式，介面和 :func:`rpa_server.processes.launch` 相同。"""

        def launch(
            command: Sequence[str],
            *,
            env: Mapping[str, str],
            log: Path,
            cwd: Path | None = None,
            pipes: bool = True,
        ) -> ChildProcess:
            return self.start(via.id, command, env=env, log=log, cwd=cwd, pipes=pipes)

        return launch

    def start(
        self,
        recorder_id: str,
        command: Sequence[str],
        *,
        env: Mapping[str, str],
        log: Path,
        cwd: Path | None = None,
        pipes: bool = True,
    ) -> RemoteProcess:
        """在錄製端啟動子程序：模組、參數、這次另外給的環境變數，以及參數用到的檔案。"""
        if not self.online(recorder_id):
            raise conflict("recorder_offline", t("error.recorder_offline", name=recorder_id))
        module, args = _module(command)
        workdir = (cwd or log.parent).absolute()
        translate = _Translator(workdir)
        log_name = translate.relative(log.absolute())
        if log_name is None or log_name == ".":
            raise ValueError("log must be inside the working folder")
        if not isinstance(env, ChildEnv):
            # 伺服器自己的環境（PATH、HOME…）不能送到錄製端：只送 child_env() 另外給的
            raise TypeError("env for a recorder must come from child_env()")
        values = {
            "module": module,
            "args": [translate(arg) for arg in args],
            "env": {
                key: translate(value) if key in _PATH_ENV else value
                for key, value in env.extra.items()
            },
            "pipes": pipes,
            "log": log_name,
        }
        if sum(len(data) for data in translate.files.values()) > MAX_INPUT_BYTES:
            raise invalid("files_invalid", t("error.files_invalid", detail="inputs too large"))
        values["files"] = {name: b64encode(data) for name, data in translate.files.items()}
        process_id = uuid.uuid4().hex[:16]
        workdir.mkdir(parents=True, exist_ok=True)
        process = RemoteProcess(
            self, recorder_id, process_id, workdir=workdir, log=log, pipes=pipes
        )
        with self._lock:  # 可重入：enqueue 也拿這個鎖
            self._processes[process_id] = process
            process.start_seq = self.enqueue(
                recorder_id, {"type": "start", "process": process_id, **values}
            )
        logger.info("在錄製端 %s 啟動 %s（%s）", recorder_id, module, process_id)
        return process

    # ------------------------------------------------------------ 請求的錄製端

    def current(self) -> Via | None:
        """目前的請求透過哪台錄製端（見 :mod:`rpa_server.context`）。"""
        return via_recorder()
