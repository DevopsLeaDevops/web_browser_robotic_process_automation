"""RPA Worker App 的狀態與動作（M10.1，ADR 0014）：視窗、通知區與 ``--no-window`` 共用，和畫面無關。

流程（背景執行緒）::

    讀配對 ─沒有→ 等使用者貼邀請（unpaired）→ 配對（pairing）
       └有→ 下載缺少的瀏覽器（downloading）→ 啟動測試網站 → 連線（connecting）
            → 接任務（online／offline／paused），直到結束（stopped）
    權杖被拒（重新邀請、停用、刪除）→ 清除配對，回到 unpaired 並說明原因。

- 接任務的迴圈就是 ``rpa worker`` 用的 :func:`rpa_worker.service.run_remote_worker`。
- 暫停：做完目前的執行後不再領取（伺服器不改，Portal 約一分鐘後顯示離線）。
- 結束：取消執行中的任務並回報；Windows 關機時只等幾秒
  （:meth:`WorkerController.stop` 的 ``fast``）。
- 畫面上的文字在 :meth:`WorkerController.snapshot` 時才依目前語言產生：語言存在 ContextVar，
  背景執行緒（這裡、通知區、視窗的 JS 橋接）看不到主執行緒設定的語言。
- 更新（ADR 0018）：上線時在背景問管理 Portal 有沒有新版本，有就下載、裝好
  （:mod:`rpa_desktop.updates`）。視窗版（設了 :attr:`WorkerController.on_update_ready`）暫停領新
  任務，閒置時重新啟動套用；使用者按「繼續接任務」就取消，和 ``--no-window`` 一樣下次啟動時套用。
  使用者自己暫停時也不重新啟動。
- 外部的動作（配對、下載、接任務……）都經由 :class:`Services`，測試換成替身。
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final, Literal, Protocol

from rpa_core.i18n import Locale, use_locale
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.credentials import Credentials, Pairing, TokenStoreError
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.i18n import t
from rpa_desktop.settings import SETTINGS_FILE, Settings, load_settings, save_settings
from rpa_desktop.updates import Updater, detect_updater
from rpa_update.errors import UpdateError
from rpa_worker.environment import WorkerInfo
from rpa_worker.pairing import App, Invite, InviteError, PairResult, parse_invite
from rpa_worker.remote import ConnectionLostError, Notify, WorkerApiError, WorkerClient
from rpa_worker.service import STOP_SECONDS

__all__ = [
    "OPTIONAL_ENGINE",
    "QUICK_STOP_SECONDS",
    "RECENT_RUNS",
    "REQUIRED_ENGINE",
    "Phase",
    "RunRecord",
    "Services",
    "WorkerController",
    "default_services",
]

logger = logging.getLogger("rpa_desktop.controller")

REQUIRED_ENGINE: Final = "chromium"
OPTIONAL_ENGINE: Final = "firefox"
BROWSER_NAMES: Final = {"chromium": "Chromium", "firefox": "Firefox"}
RECENT_RUNS: Final = 10
QUICK_STOP_SECONDS: Final = 3.0
"""Windows 關機或登出時，最多等執行中的任務這麼久（Windows 只給幾秒）。"""
DOWNLOAD_HOST_ENV: Final = "PLAYWRIGHT_DOWNLOAD_HOST"
_CONNECTION: Final = frozenset({"worker.event_offline"})
"""重新上線時要清掉的訊息（連線問題已經解決）；其他警告留著給使用者看。"""
TESTSITE_PORT: Final = 8765

Phase = Literal[
    "starting",
    "unpaired",
    "pairing",
    "downloading",
    "connecting",
    "online",
    "offline",
    "paused",
    "stopping",
    "stopped",
    "error",
]
Level = Literal["info", "warn", "error"]


class Closable(Protocol):
    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...


class RunWorker(Protocol):
    """:func:`rpa_worker.service.run_remote_worker` 的形狀。"""

    def __call__(
        self,
        client: WorkerClient,
        info: WorkerInfo,
        work_dir: Path,
        *,
        stop: threading.Event,
        notify: Notify,
        keep_runs: bool = False,
        on_stopping: Callable[[], None] = ...,
        poll_seconds: float = 0.5,
        paused: threading.Event | None = None,
        stop_seconds: Callable[[], float] = ...,
        input_folders: Callable[[], Sequence[Path]] | None = None,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class Services:
    """外部的動作；預設值見 :func:`default_services`。"""

    pair: Callable[[Invite, App], PairResult]
    missing: Callable[[Sequence[str]], list[str]]
    download: Callable[[str, Progress, Mapping[str, str], threading.Event], DownloadResult]
    run: RunWorker
    testsite: Callable[[int], tuple[Closable | None, str, str]]
    detect: Callable[[str | None, str, str], WorkerInfo]
    client: Callable[[str, str], WorkerClient] = WorkerClient
    updater: Callable[[App, str], Updater | None] = detect_updater
    """這個 App 的更新（打包的 App 才有，開發環境是 None）。"""


def default_services() -> Services:
    """真的連管理 Portal、真的下載與執行。重的模組（Playwright、runner）用到時才載入。"""

    def pair(invite: Invite, app: App) -> PairResult:
        from rpa_worker.pairing import pair as pair_with

        return pair_with(invite, app)

    def missing(engines: Sequence[str]) -> list[str]:
        from rpa_runner.installed import missing_browsers

        return missing_browsers(engines)

    def download(
        engine: str, progress: Progress, environ: Mapping[str, str], cancel: threading.Event
    ) -> DownloadResult:
        from rpa_desktop.downloads import download_browser

        return download_browser(engine, progress, environ, cancel=cancel)

    def testsite(port: int) -> tuple[Closable | None, str, str]:
        from testsite.server import start_in_background

        return start_in_background(port)

    def detect(name: str | None, fingerprint: str, version: str) -> WorkerInfo:
        return WorkerInfo.detect(name, fingerprint=fingerprint, version=version)

    from rpa_worker.service import run_remote_worker

    return Services(
        pair=pair,
        missing=missing,
        download=download,
        run=run_remote_worker,
        testsite=testsite,
        detect=detect,
    )


@dataclass(slots=True)
class RunRecord:
    """一次執行：給狀態視窗的「目前執行」與「最近的執行」。"""

    run: str
    headless: bool
    engine: str
    started: float
    status: str | None = None
    """結束時的結果（passed、failed、cancelled……）；執行中為 None。"""
    finished: float | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "run": self.run,
            "headless": self.headless,
            "engine": self.engine,
            "started": round(self.started * 1000),
            "status": self.status,
            "finished": round(self.finished * 1000) if self.finished is not None else None,
        }


@dataclass(slots=True)
class _Message:
    key: str
    params: dict[str, object] = field(default_factory=lambda: {})
    level: Level = "info"


class WorkerController:
    """一份 RPA Worker 的狀態與動作。執行緒安全：畫面從任何執行緒呼叫都可以。"""

    def __init__(
        self,
        *,
        home: Path,
        build: BuildInfo,
        environ: MutableMapping[str, str],
        credentials: Credentials,
        autostart: AutoStart,
        services: Services | None = None,
        name: str | None = None,
        testsite: bool = True,
        keep_runs: bool = False,
        firefox: bool = False,
        language: Locale | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.home = home
        self.build = build
        self.environ = environ
        self.credentials = credentials
        self.autostart = autostart
        self.services = services or default_services()
        self.name = name
        self.testsite = testsite
        self.keep_runs = keep_runs
        self.clock = clock
        self.language_override: Locale | None = language
        """環境變數 ``RPA_LANG`` 指定的語言：優先於設定，但不存進設定。"""
        self.settings_path = home / SETTINGS_FILE
        self.settings: Settings = load_settings(self.settings_path)
        if firefox and not self.settings.firefox:
            self._save(firefox=True)
        if self.settings.download_host:
            environ[DOWNLOAD_HOST_ENV] = self.settings.download_host
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self._phase: Phase = "starting"
        self._message: _Message | None = None
        self._pairing: Pairing | None = None
        self._progress: dict[str, object] | None = None
        self._current: RunRecord | None = None
        self._recent: deque[RunRecord] = deque(maxlen=RECENT_RUNS)
        self._device_name: str | None = None
        self._same_version: bool | None = None
        self._server_fingerprint: str | None = None
        self._testsite_state: str | None = None
        self._rejected_status: int | None = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._quick = False
        self._thread: threading.Thread | None = None
        self._exit_code = 0
        self.on_update_ready: Callable[[], bool] | None = None
        """裝好更新、閒置時呼叫（視窗版：重新啟動 App 套用，回傳有沒有開始）。

        None 時下次啟動才套用。"""
        self._updater: Updater | None = None
        self._update_client: WorkerClient | None = None
        self._checking = False
        self._update_ready: str | None = None
        self._holding = False
        self._declined: str | None = None
        self._claims_paused = False
        self._looping = False

    # ------------------------------------------------------------ 訂閱

    def subscribe(self, listener: Callable[[], None]) -> None:
        """狀態改變時呼叫（在背景執行緒；畫面自己決定怎麼更新）。"""
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                logger.exception("狀態通知失敗")

    def _set(
        self, phase: Phase | None = None, message: _Message | Literal[False] | None = False
    ) -> None:
        """改變狀態；``message`` 為 False 時保留原本的訊息。"""
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

    # ------------------------------------------------------------ 狀態

    @property
    def locale(self) -> Locale:
        return self.language_override or self.settings.language

    @property
    def phase(self) -> Phase:
        with self._lock:
            return self._phase

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def busy(self) -> bool:
        """正在執行任務（結束 App 前要確認）。"""
        with self._lock:
            return self._current is not None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def exit_code(self) -> int:
        """``--no-window`` 的結束碼：0 正常停止、1 被拒、2 沒有配對、3 瀏覽器下載失敗。"""
        return self._exit_code

    def snapshot(self) -> dict[str, object]:
        """畫面要顯示的全部內容（JSON 可序列化），文字依目前語言。"""
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
                "name": self._device_name or (pairing.name if pairing else None),
                "storage": pairing.storage if pairing else None,
                "progress": dict(self._progress) if self._progress else None,
                "current": self._current.to_json() if self._current else None,
                "recent": [record.to_json() for record in self._recent],
                "paused": self._paused.is_set(),
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
                    "inputFolders": list(self.settings.input_folders),
                    "autostart": self.autostart.enabled(),
                    "autostartSupported": self.autostart.supported,
                },
            }

    # ------------------------------------------------------------ 動作

    def start(self, invite: str | None = None, server: str | None = None) -> bool:
        """在背景開始：給了邀請就先配對；否則有存下的配對就連線，沒有就等使用者配對。

        已經在執行時不理會（回傳 False）。每次開始用新的停止旗標，背景工作只看自己的那一個：
        舊的工作就算還沒結束，也不會被之後的開始誤用。
        """
        with self._lock:
            if self.running:
                return False
            stop = threading.Event()
            self._stop = stop
            self._quick = False
            self._thread = threading.Thread(
                target=self._main, args=(invite, server, stop), name="rpa-worker-app", daemon=True
            )
            self._thread.start()
        return True

    def pair(self, text: str, server: str | None = None, firefox: bool | None = None) -> bool:
        """使用者在畫面上貼了邀請；開始配對時回傳 True（已經在連線或配對時不理會）。"""
        with self._lock:
            if self.running or self._phase not in ("unpaired", "error", "starting"):
                return False
            if firefox is not None and firefox != self.settings.firefox:
                self._save(firefox=firefox)
            return self.start(text, server)

    def retry(self) -> bool:
        """出錯停下後（例如瀏覽器下載失敗、認證管理員讀不到）再試一次；回傳有沒有開始。"""
        with self._lock:
            if self.running or self._phase != "error":
                return False
            return self.start()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
        else:
            self._paused.clear()
        with self._lock:
            phase = self._phase
        if phase in ("online", "offline", "paused", "connecting"):
            self._set("paused" if paused else "connecting")
        else:
            self._changed()

    def stop(self, *, fast: bool = False) -> None:
        """結束：取消執行中的任務並回報。``fast`` 時只等幾秒（Windows 關機、登出）。"""
        self._quick = self._quick or fast
        if self.running:
            self._set("stopping")
        self._stop.set()

    def wait(self, timeout: float | None = None) -> bool:
        """等背景的工作結束；回傳是否已經結束。"""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self.running

    def reset_pairing(self, timeout: float = STOP_SECONDS + 30) -> bool:
        """重新配對：停止接任務（執行中的會被取消）、清除配對，回到貼邀請的畫面。

        背景工作在 ``timeout`` 秒內沒有停下來時不清除（回傳 False），免得舊的工作拿著舊的權杖繼續。
        """
        self.stop()
        if not self.wait(timeout):
            self._set(message=_Message("window.reset_busy", level="warn"))
            return False
        self.credentials.clear()
        with self._lock:
            self._pairing = None
            self._current = None
            self._device_name = None
            self._same_version = None
        self._set("unpaired", _Message("window.pairing_reset"))
        return True

    def set_language(self, language: Locale) -> None:
        self.language_override = None  # 使用者在畫面上選的語言優先於環境變數
        self._save(language=language)
        self._changed()

    def set_firefox(self, firefox: bool) -> None:
        self._save(firefox=firefox)
        with self._lock:
            connected = self._phase in ("online", "offline", "paused", "connecting")
        if firefox and connected:
            self._set(message=_Message("window.firefox_next_start"))
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

    def set_input_folders(self, text: str) -> None:
        """檔案入參的 path 可以讀的資料夾（M7c D5）：一行一個；下一個任務開始時生效。"""
        folders = tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
        self._save(input_folders=folders)
        self._changed()

    def _input_folders(self) -> tuple[Path, ...]:
        with self._lock:
            folders = self.settings.input_folders
        return tuple(Path(item).expanduser() for item in folders)

    def set_autostart(self, enabled: bool) -> None:
        try:
            if enabled:
                self.autostart.enable()
            else:
                self.autostart.disable()
        except OSError as error:
            self._set(message=_Message("window.autostart_failed", {"error": error}, "error"))
            return
        self._save(autostart_offered=True)
        self._changed()

    def mark_tray_hint_shown(self) -> bool:
        """第一次縮到通知區時回傳 True（要提示），之後回傳 False。"""
        with self._lock:
            if self.settings.tray_hint_shown:
                return False
            self._save(tray_hint_shown=True)
            return True

    def _save(
        self,
        *,
        language: Locale | None = None,
        firefox: bool | None = None,
        download_host: str | None = None,
        autostart_offered: bool | None = None,
        tray_hint_shown: bool | None = None,
        input_folders: tuple[str, ...] | None = None,
    ) -> None:
        with self._lock:
            self._save_locked(language, firefox, download_host, autostart_offered, tray_hint_shown)
            if input_folders is not None:
                self.settings = replace(self.settings, input_folders=input_folders)
                self._write_settings()

    def _save_locked(
        self,
        language: Locale | None,
        firefox: bool | None,
        download_host: str | None,
        autostart_offered: bool | None,
        tray_hint_shown: bool | None,
    ) -> None:
        current = self.settings
        self.settings = Settings(
            language=current.language if language is None else language,
            firefox=current.firefox if firefox is None else firefox,
            download_host=current.download_host if download_host is None else download_host,
            autostart_offered=(
                current.autostart_offered if autostart_offered is None else autostart_offered
            ),
            tray_hint_shown=current.tray_hint_shown if tray_hint_shown is None else tray_hint_shown,
            input_folders=current.input_folders,
        )
        self._write_settings()

    def _write_settings(self) -> None:
        try:
            save_settings(self.settings_path, self.settings)
        except OSError as error:
            logger.warning("設定存不下來：%s", error)

    # ------------------------------------------------------------ 背景工作

    def _main(self, invite: str | None, server: str | None, stop: threading.Event) -> None:
        self._exit_code = 0
        self._rejected_status = None
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
                    self._set("error", _Message("window.keyring_failed", params, "error"))
                    return
                if pairing is None:
                    self._exit_code = 2
                    self._set("unpaired")
                    return
                with self._lock:
                    self._pairing = pairing
            self._work(stop)
        except Exception as error:
            logger.exception("RPA Worker 停止了")
            self._exit_code = 1
            self._set("error", _Message("window.crashed", {"error": error}, "error"))

    def _pair_now(self, text: str, server: str | None) -> bool:
        self._set("pairing", None)
        try:
            invite = parse_invite(text, server or None)
        except InviteError as error:
            self._set("unpaired", _Message("worker.invite_" + error.reason, level="error"))
            return False
        try:
            result = self.services.pair(invite, "worker")
        except WorkerApiError as error:
            message = _Message("worker.pair_rejected", {"message": error.message}, "error")
            self._set("unpaired", message)
            return False
        except ConnectionLostError as error:
            params: dict[str, object] = {"server": invite.server, "reason": error}
            self._set("unpaired", _Message("worker.pair_offline", params, "error"))
            return False
        except ValueError as error:
            self._set("unpaired", _Message("window.pair_failed", {"error": error}, "error"))
            return False
        pairing = self.credentials.save(result)
        with self._lock:
            self._pairing = pairing
        logger.info(
            "已配對：裝置 %s（%s），權杖存在 %s", result.device, result.name, pairing.storage
        )
        if not self.settings.autostart_offered and self.autostart.supported:
            self._save(autostart_offered=True)  # 第一次配對依預設開啟，之後只照使用者的選擇
            try:
                self.autostart.enable()
            except OSError as error:
                logger.warning("自動啟動開不了：%s", error)
        params = {"name": result.name, "device": result.device}
        self._set(message=_Message("worker.paired", params))
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
            self._set("downloading", None)  # 進度與說明在下載的面板上
            result = self.services.download(engine, progress, self.environ, stop)
            with self._lock:
                self._progress = None
            if stop.is_set():
                return False  # 結束或重新配對：下載被取消
            if result.code != 0:
                params: dict[str, object] = {"browser": name, "code": result.code}
                if engine == REQUIRED_ENGINE:
                    self._set("error", _Message("window.download_failed", params, "error"))
                    if result.tail:
                        logger.warning("下載的輸出：\n%s", result.tail)
                    return False
                self._set(message=_Message("window.download_failed", params, "warn"))
                continue
            self._set(message=_Message("worker.downloaded", {"browser": name}))
        return True

    def _work(self, stop: threading.Event) -> None:
        pairing = self._pairing
        assert pairing is not None
        self.autostart.refresh()
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
        if not info.display:
            self._set(message=_Message("worker.no_display", level="warn"))
        with self._lock:
            self._updater = self.services.updater("worker", self.build.version)
            self._update_client = self.services.client(pairing.server, pairing.token)
            self._looping = True
        self._set("paused" if self._paused.is_set() else "connecting")
        try:
            fatal = self.services.run(
                self.services.client(pairing.server, pairing.token),
                info,
                self.home / "work",
                stop=stop,
                notify=self._notify,
                keep_runs=self.keep_runs,
                paused=self._paused,
                stop_seconds=lambda: QUICK_STOP_SECONDS if self._quick else STOP_SECONDS,
                input_folders=self._input_folders,
            )
        finally:
            with self._lock:
                self._looping = False
            if site is not None:
                site.shutdown()
                site.server_close()
        with self._lock:
            if self._current is not None and self._current.status is None:
                self._current.status = "cancelled"
                self._current.finished = self.clock()
            self._current = None
        if fatal is None:
            self._set("stopped")
            return
        self._exit_code = 1
        if self._rejected_status in (401, 403):
            self.credentials.clear()
            with self._lock:
                self._pairing = None
            self._set("unpaired", _Message("window.rejected", {"message": fatal}, "error"))
            return
        self._set("error", _Message("worker.event_rejected", {"message": fatal}, "error"))

    def _finish(self, run: str, status: str) -> None:
        with self._lock:
            for record in self._recent:
                if record.run == run and record.status is None:
                    record.status = status
                    record.finished = self.clock()
            if self._current is not None and self._current.run == run:
                self._current = None

    def _notify(self, event: str, details: Mapping[str, object]) -> None:
        """接任務的迴圈回報的事件（見 :class:`rpa_worker.remote.RemoteJobSource`）。"""
        from rpa_desktop.worker_app import describe_event

        with use_locale(self.locale):
            line = describe_event(event, details)
        if line is not None:
            logger.info("%s", line)
        if event == "online":
            fingerprint = details.get("serverFingerprint")
            worker = details.get("worker")
            with self._lock:
                self._same_version = details.get("sameVersion") is not False
                self._server_fingerprint = str(fingerprint) if fingerprint else None
                self._device_name = str(worker) if worker else None
                self._claims_paused = False
            with self._lock:
                message = self._message
            keep = (
                message is not None and message.level != "info" and message.key not in _CONNECTION
            )
            self._set("paused" if self._paused.is_set() else "online", False if keep else None)
            self._check_update()
        elif event == "offline":
            params = {"server": details.get("server"), "reason": details.get("reason")}
            self._set("offline", _Message("worker.event_offline", params, "warn"))
        elif event == "paused":
            with self._lock:
                self._claims_paused = True
            self._set("paused")
        elif event == "claimed":
            record = RunRecord(
                run=str(details.get("run")),
                headless=bool(details.get("headless")),
                engine=str(details.get("engine") or ""),
                started=self.clock(),
            )
            with self._lock:
                self._current = record
                self._recent.appendleft(record)
                self._claims_paused = False
            self._changed()
        elif event == "reported":
            self._finish(str(details.get("run")), str(details.get("status")))
            self._changed()
        elif event == "abandoned":
            self._finish(str(details.get("run")), "abandoned")
            self._changed()
        elif event == "report_failed":
            params = {"reason": details.get("reason")}
            self._set(message=_Message("worker.event_report_failed", params, "warn"))
        elif event == "done":
            self._finish(str(details.get("run")), "unreported")  # 已經有結果的不會被改
            self._changed()
        elif event == "rejected":
            status = details.get("status")
            with self._lock:
                self._rejected_status = status if isinstance(status, int) else 0
            if details.get("code") == "protocol_mismatch":
                self._check_update()  # 更新到管理 Portal 的版本就能再連上

    # ------------------------------------------------------------ 更新（ADR 0018）

    def _check_update(self) -> None:
        """在背景問管理 Portal 有沒有新版本；同時只問一次，已經在等重新啟動時不再問。"""
        with self._lock:
            updater, client, stop = self._updater, self._update_client, self._stop
            if updater is None or client is None or self._checking or self._holding:
                return
            self._checking = True
        threading.Thread(
            target=self._update, args=(updater, client, stop), name="rpa-update", daemon=True
        ).start()

    def _update(self, updater: Updater, client: WorkerClient, stop: threading.Event) -> None:
        try:
            checked = updater.check(client)
        except WorkerApiError as error:
            if error.status == 404:
                logger.info("管理 Portal 沒有提供更新（較舊的版本，或更新檔剛被移走）")
            else:
                params: dict[str, object] = {"error": error.message}
                self._set(message=_Message("worker.update_error", params, "warn"))
            return
        except (ConnectionLostError, UpdateError, OSError) as error:
            self._set(message=_Message("worker.update_error", {"error": error}, "warn"))
            return
        finally:
            with self._lock:
                self._checking = False
        offer = checked.offer
        if offer.status in ("full", "failed"):
            params = {"version": offer.version}
            self._set(message=_Message(f"worker.update_{offer.status}", params, "warn"))
        elif checked.ready:
            self._apply(offer.version, stop)

    def _apply(self, version: str, stop: threading.Event) -> None:
        """新版本裝好了：視窗版暫停領新任務、閒置時重新啟動；其他下次啟動時套用。"""
        with self._lock:
            if self._holding:
                return
            self._update_ready = version
            restart = self.on_update_ready
            # 使用者自己暫停、或已經取消過這個版本的重新啟動：不打擾
            hold = restart is not None and not self._paused.is_set() and self._declined != version
            self._holding = hold
        if restart is None or not hold:
            self._set(message=_Message("worker.update_next_start", {"version": version}))
            return
        self.set_paused(True)
        self._set(message=_Message("worker.update_restarting", {"version": version}))
        declined = False
        while not stop.wait(1.0):
            if not self._paused.is_set():
                declined = True  # 使用者按了「繼續接任務」
                break
            with self._lock:
                idle = self._current is None and (self._claims_paused or not self._looping)
            if idle:
                logger.info("閒置了：重新啟動套用 %s", version)
                if restart():
                    return
                self.set_paused(False)
                declined = True
                break
        with self._lock:
            self._holding = False  # 結束、重新配對，或不重新啟動了
            if declined:
                self._declined = version
        if declined:
            self._set(message=_Message("worker.update_next_start", {"version": version}))
