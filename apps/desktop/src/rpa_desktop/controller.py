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
- 外部的動作（配對、下載、接任務……）都經由 :class:`Services`，測試換成替身。
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol

from rpa_core.i18n import Locale, use_locale
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.credentials import Credentials, Pairing
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.i18n import t
from rpa_desktop.settings import SETTINGS_FILE, Settings, load_settings, save_settings
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
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class Services:
    """外部的動作；預設值見 :func:`default_services`。"""

    pair: Callable[[Invite, App], PairResult]
    missing: Callable[[Sequence[str]], list[str]]
    download: Callable[[str, Progress, Mapping[str, str]], DownloadResult]
    run: RunWorker
    testsite: Callable[[int], tuple[Closable | None, str, str]]
    detect: Callable[[str | None, str, str], WorkerInfo]
    client: Callable[[str, str], WorkerClient] = WorkerClient


def default_services() -> Services:
    """真的連管理 Portal、真的下載與執行。重的模組（Playwright、runner）用到時才載入。"""

    def pair(invite: Invite, app: App) -> PairResult:
        from rpa_worker.pairing import pair as pair_with

        return pair_with(invite, app)

    def missing(engines: Sequence[str]) -> list[str]:
        from rpa_runner.installed import missing_browsers

        return missing_browsers(engines)

    def download(engine: str, progress: Progress, environ: Mapping[str, str]) -> DownloadResult:
        from rpa_desktop.downloads import download_browser

        return download_browser(engine, progress, environ)

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
                "sameVersion": self._same_version,
                "serverFingerprint": self._server_fingerprint,
                "testsite": self._testsite_state,
                "home": str(self.home),
                "settings": {
                    "language": self.locale,
                    "firefox": self.settings.firefox,
                    "downloadHost": self.settings.download_host,
                    "autostart": self.autostart.enabled(),
                    "autostartSupported": self.autostart.supported,
                },
            }

    # ------------------------------------------------------------ 動作

    def start(self, invite: str | None = None, server: str | None = None) -> None:
        """在背景開始：給了邀請就先配對；否則有存下的配對就連線，沒有就等使用者配對。"""
        if self.running:
            return
        self._thread = threading.Thread(
            target=self._main, args=(invite, server), name="rpa-worker-app", daemon=True
        )
        self._thread.start()

    def pair(self, text: str, server: str | None = None, firefox: bool | None = None) -> bool:
        """使用者在畫面上貼了邀請；開始配對時回傳 True（已經在連線或配對時不理會）。"""
        with self._lock:
            if self.running or self._phase not in ("unpaired", "error", "starting"):
                return False
        if firefox is not None and firefox != self.settings.firefox:
            self._save(firefox=firefox)
        self._stop = threading.Event()
        self.start(text, server)
        return True

    def retry(self) -> bool:
        """出錯停下後（例如瀏覽器下載失敗）再試一次；回傳有沒有開始。"""
        with self._lock:
            if self.running or self._phase != "error":
                return False
        self._stop = threading.Event()
        self._quick = False
        self.start()
        return True

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

    def reset_pairing(self) -> None:
        """重新配對：停止接任務（執行中的會被取消）、清除配對，回到貼邀請的畫面。"""
        self._stop.set()
        self.wait(150.0)
        self.credentials.clear()
        with self._lock:
            self._pairing = None
            self._current = None
            self._device_name = None
            self._same_version = None
        self._stop = threading.Event()
        self._set("unpaired", _Message("window.pairing_reset"))

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
        )
        try:
            save_settings(self.settings_path, self.settings)
        except OSError as error:
            logger.warning("設定存不下來：%s", error)

    # ------------------------------------------------------------ 背景工作

    def _main(self, invite: str | None, server: str | None) -> None:
        self._exit_code = 0
        self._rejected_status = None
        try:
            if invite is not None:
                if not self._pair_now(invite, server):
                    self._exit_code = 2
                    return
            else:
                pairing = self.credentials.load()
                if pairing is None:
                    self._exit_code = 2
                    self._set("unpaired")
                    return
                with self._lock:
                    self._pairing = pairing
            self._work()
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

    def _prepare_browsers(self) -> bool:
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
            result = self.services.download(engine, progress, self.environ)
            with self._lock:
                self._progress = None
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

    def _work(self) -> None:
        pairing = self._pairing
        assert pairing is not None
        self.autostart.refresh()
        if not self._prepare_browsers():
            self._exit_code = 3
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
        self._set("paused" if self._paused.is_set() else "connecting")
        try:
            fatal = self.services.run(
                self.services.client(pairing.server, pairing.token),
                info,
                self.home / "work",
                stop=self._stop,
                notify=self._notify,
                keep_runs=self.keep_runs,
                paused=self._paused,
                stop_seconds=lambda: QUICK_STOP_SECONDS if self._quick else STOP_SECONDS,
            )
        finally:
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
            self._set("paused" if self._paused.is_set() else "online", None)
        elif event == "offline":
            params = {"server": details.get("server"), "reason": details.get("reason")}
            self._set("offline", _Message("worker.event_offline", params, "warn"))
        elif event == "paused":
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
        elif event == "rejected":
            status = details.get("status")
            with self._lock:
                self._rejected_status = status if isinstance(status, int) else 0
