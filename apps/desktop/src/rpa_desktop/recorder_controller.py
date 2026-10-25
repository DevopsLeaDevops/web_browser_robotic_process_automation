"""RPA 錄製端 App 的狀態與動作（M10.2，ADR 0014）：和畫面無關，視窗與測試共用。

流程（背景執行緒）::

    讀配對 ─沒有→ 等使用者在 App 的頁面貼邀請（unpaired）→ 配對（pairing）
       └有→ 下載缺少的瀏覽器（downloading）→ 啟動測試網站 → 連線（connecting）
            → 執行管理 Portal 交來的錄製、逐步調試、人工登入（online／offline），直到結束（stopped）
    權杖被拒（重新邀請、停用、刪除）→ 清除配對，回到 unpaired 並說明原因。

- 執行子程序的是 ``rpa recorder`` 也用的 :class:`rpa_worker.recorder.RecorderHost`；視窗連的
  本機閘道（:class:`rpa_worker.gateway.Gateway`）用 :meth:`RecorderController.token` 取權杖，
  配對好或清除時由 :meth:`RecorderController.attach` 換掉轉送的目標。
- 權杖存在鑰匙圈的「RPA Recorder」項目（:data:`SERVICE`），和 RPA Worker 分開。
- 畫面上的文字在 :meth:`RecorderController.snapshot` 時才依目前語言產生（同 RPA Worker）。
- 更新（ADR 0018）：上線時在背景問管理 Portal 有沒有新版本，有就下載、裝好
  （:mod:`rpa_desktop.updates`），提示使用者重新開啟 App 套用；不會自己重新啟動。
- 外部的動作（配對、下載、執行……）都經由 :class:`RecorderServices`，測試換成替身。
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol

from rpa_core.i18n import Locale, use_locale
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import (
    BROWSER_NAMES,
    DOWNLOAD_HOST_ENV,
    OPTIONAL_ENGINE,
    REQUIRED_ENGINE,
    TESTSITE_PORT,
    Closable,
)
from rpa_desktop.credentials import Credentials, Pairing, TokenStoreError
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.i18n import t
from rpa_desktop.settings import SETTINGS_FILE, Settings, load_settings, save_settings
from rpa_desktop.updates import Updater, detect_updater
from rpa_update.errors import UpdateError
from rpa_worker.environment import WorkerInfo
from rpa_worker.pairing import CLIENT_API_PREFIX, App, Invite, InviteError, PairResult, parse_invite
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient

__all__ = [
    "SERVICE",
    "Phase",
    "RecorderController",
    "RecorderServices",
    "default_services",
]

logger = logging.getLogger("rpa_desktop.recorder_controller")

SERVICE: Final = "RPA Recorder"
"""鑰匙圈裡的項目名稱。"""

Phase = Literal[
    "starting",
    "unpaired",
    "pairing",
    "downloading",
    "connecting",
    "online",
    "offline",
    "stopping",
    "stopped",
    "error",
]
Level = Literal["info", "warn", "error"]
Notify = Callable[[str, Mapping[str, object]], None]


class Host(Protocol):
    """:class:`rpa_worker.recorder.RecorderHost` 用到的部分。"""

    def run(self, stop: threading.Event | None = None) -> str | None: ...

    def active(self) -> int: ...

    def stop_all(self) -> None: ...


class Server(Protocol):
    """本機閘道用到的部分（:class:`rpa_worker.gateway.Gateway`）。"""

    def set_server(self, server: str | None) -> None: ...


@dataclass(frozen=True, slots=True)
class RecorderServices:
    """外部的動作；預設值見 :func:`default_services`。"""

    pair: Callable[[Invite, App], PairResult]
    missing: Callable[[Sequence[str]], list[str]]
    download: Callable[[str, Progress, Mapping[str, str], threading.Event], DownloadResult]
    testsite: Callable[[int], tuple[Closable | None, str, str]]
    detect: Callable[[str | None, str, str], WorkerInfo]
    host: Callable[[WorkerClient, Mapping[str, object], Path, Notify], Host]
    client: Callable[[str, str], WorkerClient] = lambda server, token: WorkerClient(
        server, token, prefix=CLIENT_API_PREFIX
    )
    updater: Callable[[App, str], Updater | None] = detect_updater


def default_services() -> RecorderServices:
    """真的連管理 Portal、真的下載與執行。"""
    from rpa_desktop.controller import default_services as worker_services

    worker = worker_services()

    def host(client: WorkerClient, info: Mapping[str, object], work: Path, notify: Notify) -> Host:
        from rpa_worker.recorder import RecorderHost

        return RecorderHost(client, info, work, notify=notify)

    return RecorderServices(
        pair=worker.pair,
        missing=worker.missing,
        download=worker.download,
        testsite=worker.testsite,
        detect=worker.detect,
        host=host,
    )


@dataclass(slots=True)
class _Message:
    key: str
    params: dict[str, object] = field(default_factory=lambda: {})
    level: Level = "info"


class RecorderController:
    """一份 RPA 錄製端的狀態與動作。執行緒安全：畫面從任何執行緒呼叫都可以。"""

    def __init__(
        self,
        *,
        home: Path,
        build: BuildInfo,
        environ: MutableMapping[str, str],
        credentials: Credentials,
        services: RecorderServices | None = None,
        name: str | None = None,
        testsite: bool = True,
        language: Locale | None = None,
    ) -> None:
        self.home = home
        self.build = build
        self.environ = environ
        self.credentials = credentials
        self.services = services or default_services()
        self.name = name
        self.testsite = testsite
        self.language_override: Locale | None = language
        self.settings_path = home / SETTINGS_FILE
        self.settings: Settings = load_settings(self.settings_path)
        if self.settings.download_host:
            environ[DOWNLOAD_HOST_ENV] = self.settings.download_host
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self._phase: Phase = "starting"
        self._message: _Message | None = None
        self._pairing: Pairing | None = None
        self._progress: dict[str, object] | None = None
        self._host: Host | None = None
        self._gateway: Server | None = None
        self._same_version: bool | None = None
        self._server_fingerprint: str | None = None
        self._testsite_state: str | None = None
        self._display = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rejected = False
        self._exit_code = 0
        self._updater: Updater | None = None
        self._update_client: WorkerClient | None = None
        self._checking = False
        self._update_ready: str | None = None

    # ------------------------------------------------------------ 訂閱與閘道

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def attach(self, gateway: Server) -> None:
        """本機閘道：配對好時轉送到那個管理 Portal，沒有配對時只給 App 自己的頁面。"""
        with self._lock:
            self._gateway = gateway
            server = self._pairing.server if self._pairing is not None else None
        gateway.set_server(server)

    def token(self) -> str | None:
        """閘道轉送時加上的權杖（沒有配對時 None）。"""
        with self._lock:
            return self._pairing.token if self._pairing is not None else None

    def unauthorized(self) -> None:
        """閘道看到管理 Portal 回 401：權杖失效了，錄製端程式下次輪詢就會知道並清除配對。"""
        logger.info("管理 Portal 不接受這台錄製端的權杖")

    def _changed(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                logger.exception("狀態通知失敗")

    def _set(
        self, phase: Phase | None = None, message: _Message | Literal[False] | None = False
    ) -> None:
        with self._lock:
            if phase is not None:
                self._phase = phase
            if message is not False:
                self._message = message
        if message:
            log = logger.warning if message.level != "info" else logger.info
            with use_locale(self.locale):
                log("%s", t(message.key, **message.params))
        self._changed()

    def _use(self, pairing: Pairing | None) -> None:
        with self._lock:
            self._pairing = pairing
            gateway = self._gateway
        if gateway is not None:
            gateway.set_server(pairing.server if pairing is not None else None)

    # ------------------------------------------------------------ 狀態

    @property
    def locale(self) -> Locale:
        return self.language_override or self.settings.language

    @property
    def phase(self) -> Phase:
        with self._lock:
            return self._phase

    @property
    def active(self) -> int:
        """正在這台執行的錄製、調試、人工登入（結束 App 前要確認）。"""
        with self._lock:
            host = self._host
        return host.active() if host is not None else 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def exit_code(self) -> int:
        """``--no-window`` 的結束碼（同 RPA Worker）：0 正常停止、1 被拒或出錯、2 沒有配對或
        配對失敗、3 必要的瀏覽器下載失敗。"""
        return self._exit_code

    def snapshot(self) -> dict[str, object]:
        """畫面要顯示的全部內容（JSON 可序列化），文字依目前語言。"""
        active = self.active
        with self._lock, use_locale(self.locale):
            message = None
            if self._message is not None:
                message = {
                    "text": t(self._message.key, **self._message.params),
                    "level": self._message.level,
                }
            pairing = self._pairing
            return {
                "phase": self._phase,
                "message": message,
                "paired": pairing is not None,
                "server": pairing.server if pairing else None,
                "device": pairing.device if pairing else None,
                "name": pairing.name if pairing else None,
                "storage": pairing.storage if pairing else None,
                "progress": dict(self._progress) if self._progress else None,
                "active": active,
                "display": self._display,
                "version": self.build.version,
                "fingerprint": self.build.fingerprint,
                # 已經裝好管理 Portal 的版本：不用再提示下載安裝檔
                "sameVersion": self._same_version if self._update_ready is None else None,
                "serverFingerprint": self._server_fingerprint,
                "testsite": self._testsite_state,
                "home": str(self.home),
                "settings": {
                    "language": self.locale,
                    "firefox": self.settings.firefox,
                    "downloadHost": self.settings.download_host,
                },
            }

    # ------------------------------------------------------------ 動作

    def start(self, invite: str | None = None, server: str | None = None) -> bool:
        """在背景開始；已經在執行時不理會（回傳 False）。"""
        with self._lock:
            if self.running:
                return False
            stop = threading.Event()
            self._stop = stop
            self._thread = threading.Thread(
                target=self._main, args=(invite, server, stop), name="rpa-recorder-app", daemon=True
            )
            self._thread.start()
        return True

    def pair(self, text: str, server: str | None = None, firefox: bool | None = None) -> bool:
        """使用者在頁面上貼了邀請；開始配對時回傳 True。"""
        with self._lock:
            if self.running or self._phase not in ("unpaired", "error", "starting"):
                return False
            if firefox is not None and firefox != self.settings.firefox:
                self._save(firefox=firefox)
            return self.start(text, server)

    def retry(self) -> bool:
        with self._lock:
            if self.running or self._phase != "error":
                return False
            return self.start()

    def stop(self) -> None:
        """結束：進行中的錄製、調試、人工登入會結束（管理 Portal 那邊標成結束）。"""
        if self.running:
            self._set("stopping")
        self._stop.set()

    def stop_now(self) -> None:
        """結束 App 時：除了 :meth:`stop`，直接結束這台的子程序並刪掉暫存資料夾。

        錄製端程式正在等管理 Portal 的長輪詢（最多 25 秒）時，停止旗標要等它回來才看得到；
        App 不等它，免得關掉之後程序還留著、鎖也還沒放開。
        """
        self.stop()
        with self._lock:
            host = self._host
        if host is not None:
            host.stop_all()

    def wait(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self.running

    def reset_pairing(self, timeout: float = 40.0) -> bool:
        """重新配對：停止、清除配對，回到貼邀請的頁面。背景工作停不下來時不清除。"""
        self.stop()
        if not self.wait(timeout):
            self._set(message=_Message("recorder.reset_busy", level="warn"))
            return False
        self.credentials.clear()
        self._use(None)
        with self._lock:
            self._same_version = None
        self._set("unpaired", _Message("recorder.pairing_reset"))
        return True

    def set_language(self, language: Locale) -> None:
        self.language_override = None
        self._save(language=language)
        self._changed()

    def set_firefox(self, firefox: bool) -> None:
        self._save(firefox=firefox)
        with self._lock:
            connected = self._phase in ("online", "offline", "connecting")
        if firefox and connected:
            self._set(message=_Message("recorder.firefox_next_start"))
        else:
            self._changed()

    def set_download_host(self, host: str) -> None:
        value = host.strip()
        self._save(download_host=value)
        if value:
            self.environ[DOWNLOAD_HOST_ENV] = value
        else:
            self.environ.pop(DOWNLOAD_HOST_ENV, None)
        self._changed()

    def _save(
        self,
        *,
        language: Locale | None = None,
        firefox: bool | None = None,
        download_host: str | None = None,
    ) -> None:
        with self._lock:
            current = self.settings
            self.settings = Settings(
                language=current.language if language is None else language,
                firefox=current.firefox if firefox is None else firefox,
                download_host=current.download_host if download_host is None else download_host,
                autostart_offered=current.autostart_offered,
                tray_hint_shown=current.tray_hint_shown,
            )
            try:
                save_settings(self.settings_path, self.settings)
            except OSError as error:
                logger.warning("設定存不下來：%s", error)

    # ------------------------------------------------------------ 背景工作

    def _main(self, invite: str | None, server: str | None, stop: threading.Event) -> None:
        self._exit_code = 0
        try:
            if invite is not None:
                if not self._pair_now(invite, server):
                    self._exit_code = 2
                    return
            else:
                try:
                    pairing = self.credentials.load()
                except TokenStoreError as error:
                    self._exit_code = 1
                    params: dict[str, object] = {"error": error}
                    self._set("error", _Message("recorder.keyring_failed", params, "error"))
                    return
                if pairing is None:
                    self._exit_code = 2
                    self._set("unpaired")
                    return
                self._use(pairing)
            self._work(stop)
        except Exception as error:
            logger.exception("RPA 錄製端停止了")
            self._exit_code = 1
            self._set("error", _Message("recorder.crashed", {"error": error}, "error"))

    def _pair_now(self, text: str, server: str | None) -> bool:
        self._set("pairing", None)
        try:
            invite = parse_invite(text, server or None)
        except InviteError as error:
            self._set("unpaired", _Message("worker.invite_" + error.reason, level="error"))
            return False
        try:
            result = self.services.pair(invite, "recorder")
        except WorkerApiError as error:
            message = _Message("worker.pair_rejected", {"message": error.message}, "error")
            self._set("unpaired", message)
            return False
        except ConnectionLostError as error:
            params: dict[str, object] = {"server": invite.server, "reason": error}
            self._set("unpaired", _Message("worker.pair_offline", params, "error"))
            return False
        except ValueError as error:
            self._set("unpaired", _Message("recorder.pair_failed", {"error": error}, "error"))
            return False
        pairing = self.credentials.save(result)
        self._use(pairing)
        logger.info(
            "已配對：錄製端 %s（%s），權杖存在 %s", result.device, result.name, pairing.storage
        )
        params = {"name": result.name, "device": result.device}
        self._set(message=_Message("recorder.paired", params))
        return True

    def _prepare_browsers(self, stop: threading.Event) -> bool:
        engines = [REQUIRED_ENGINE]
        if self.settings.firefox:
            engines.append(OPTIONAL_ENGINE)
        for engine in self.services.missing(engines):
            name = BROWSER_NAMES.get(engine, engine)

            def progress(percent: int | None, name: str = name) -> None:
                with self._lock:
                    self._progress = {"browser": name, "percent": percent}
                self._changed()

            logger.info("下載 %s", name)
            self._set("downloading", None)
            result = self.services.download(engine, progress, self.environ, stop)
            with self._lock:
                self._progress = None
            if stop.is_set():
                return False
            if result.code != 0:
                params: dict[str, object] = {"browser": name, "code": result.code}
                if engine == REQUIRED_ENGINE:
                    self._set("error", _Message("recorder.download_failed", params, "error"))
                    if result.tail:
                        logger.warning("下載的輸出：\n%s", result.tail)
                    return False
                self._set(message=_Message("recorder.download_failed", params, "warn"))
                continue
            self._set(message=_Message("worker.downloaded", {"browser": name}))
        return True

    def _work(self, stop: threading.Event) -> None:
        pairing = self._pairing
        assert pairing is not None
        if not self._prepare_browsers(stop):
            if stop.is_set():
                self._set("stopped")
            else:
                self._exit_code = 3
            return
        if stop.is_set():
            self._set("stopped")
            return
        site: Closable | None = None
        if self.testsite:
            site, state, detail = self.services.testsite(TESTSITE_PORT)
            with self._lock:
                self._testsite_state = state
            if state in ("busy", "failed"):
                params: dict[str, object] = {
                    "url": f"http://127.0.0.1:{TESTSITE_PORT}/",
                    "port": TESTSITE_PORT,
                    "error": detail,
                }
                self._set(message=_Message(f"worker.testsite_{state}", params, "warn"))
        info = self.services.detect(self.name, self.build.fingerprint, self.build.version)
        with self._lock:
            self._display = info.display
        with self._lock:
            self._updater = self.services.updater("recorder", self.build.version)
            self._update_client = self.services.client(pairing.server, pairing.token)
        self._set("connecting")
        self._rejected = False
        host = self.services.host(
            self.services.client(pairing.server, pairing.token),
            info.to_json(),
            self.home / "sessions",
            self._notify,
        )
        with self._lock:
            self._host = host
        try:
            fatal = host.run(stop)
        finally:
            with self._lock:
                self._host = None
            if site is not None:
                site.shutdown()
                site.server_close()
        if fatal is None:
            self._set("stopped")
            return
        self._exit_code = 1
        if self._rejected:
            self.credentials.clear()
            self._use(None)
            self._set("unpaired", _Message("recorder.rejected", {"message": fatal}, "error"))
            return
        self._set("error", _Message("recorder.event_rejected", {"message": fatal}, "error"))

    def _notify(self, event: str, details: Mapping[str, object]) -> None:
        """錄製端程式的事件（見 :class:`rpa_worker.recorder.RecorderHost`）。"""
        if event == "online":
            fingerprint = details.get("serverFingerprint")
            with self._lock:
                self._same_version = details.get("sameVersion") is not False
                self._server_fingerprint = str(fingerprint) if fingerprint else None
                message = self._message
            # 連線問題解決了：清掉離線的訊息；其他警告（例如測試網站沒啟動）留著
            keep = (
                message is not None
                and message.level != "info"
                and message.key != "recorder.event_offline"
            )
            self._set("online", False if keep else None)
            self._check_update()
        elif event == "offline":
            params = {"server": details.get("server"), "reason": details.get("reason")}
            self._set("offline", _Message("recorder.event_offline", params, "warn"))
        elif event == "rejected":
            with self._lock:
                # 權杖被拒（401／403）時清除配對；協定版本不同只停下來說明
                self._rejected = details.get("status") in (401, 403)
            self._changed()
            if details.get("code") == "protocol_mismatch":
                self._check_update()  # 更新到管理 Portal 的版本就能再連上
        elif event in ("started", "finished"):
            logger.info("%s：%s", event, dict(details))
            self._changed()

    # ------------------------------------------------------------ 更新（ADR 0018）

    def _check_update(self) -> None:
        """在背景問管理 Portal 有沒有新版本（同時只問一次）。"""
        with self._lock:
            updater, client = self._updater, self._update_client
            if updater is None or client is None or self._checking:
                return
            self._checking = True
        threading.Thread(
            target=self._update, args=(updater, client), name="rpa-update", daemon=True
        ).start()

    def _update(self, updater: Updater, client: WorkerClient) -> None:
        try:
            checked = updater.check(client)
        except WorkerApiError as error:
            if error.status == 404:
                logger.info("管理 Portal 沒有提供更新（較舊的版本，或更新檔剛被移走）")
            else:
                params: dict[str, object] = {"error": error.message}
                self._set(message=_Message("recorder.update_error", params, "warn"))
            return
        except (ConnectionLostError, UpdateError, OSError) as error:
            self._set(message=_Message("recorder.update_error", {"error": error}, "warn"))
            return
        finally:
            with self._lock:
                self._checking = False
        offer = checked.offer
        params = {"version": offer.version}
        if offer.status in ("full", "failed"):
            self._set(message=_Message(f"recorder.update_{offer.status}", params, "warn"))
        elif checked.ready:
            with self._lock:
                self._update_ready = offer.version
            self._set(message=_Message("recorder.update_next_start", params))


def wait_for(check: Callable[[], bool], timeout: float, interval: float = 0.05) -> bool:
    """等到 ``check()`` 成立；逾時回傳 False（測試與自我測試用）。"""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            return False
        time.sleep(interval)
    return True
