"""RPA Worker 的視窗版（M10.1，ADR 0014）：雙擊 ``rpa-worker.exe`` 開啟的就是這個。

- 狀態視窗：pywebview（Windows 上是 WebView2），頁面見 :mod:`rpa_desktop.ui`；頁面透過 js_api
  （:class:`Api`）讀狀態、呼叫動作，狀態與動作都在
  :class:`rpa_desktop.controller.WorkerController`。
- 通知區：:class:`rpa_desktop.tray.Tray`。關閉視窗是縮到通知區（第一次提示一次）；
  結束要從選單或視窗裡的按鈕。
- 只執行一份：已經在執行時叫出那一份的視窗後結束（:mod:`rpa_desktop.single_instance`）。
- ``--background``：登入 Windows 時自動啟動用，只出現在通知區；還沒配對時仍然打開視窗。
- 沒有 WebView2：說明怎麼安裝，之後只靠通知區接任務。
- Windows 登出或關機：立刻取消執行中的任務並回報（只等幾秒），不擋住關機。
- ``--smoke-test``：CI 用，打開真的視窗與通知區圖示、確認頁面的腳本跑起來後結束。
"""

import argparse
import importlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, MutableMapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from rpa_core.i18n import ENV_VAR, Locale, parse_locale, set_locale, use_locale
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import load
from rpa_desktop.controller import QUICK_STOP_SECONDS, WorkerController
from rpa_desktop.credentials import Credentials, TokenStoreError
from rpa_desktop.i18n import resolve_locale, t
from rpa_desktop.logs import setup_logging
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.tray import Tray
from rpa_desktop.ui import render_page
from rpa_desktop.worker_app import data_dir, ensure_browsers_path

if TYPE_CHECKING:
    import webview

__all__ = ["Api", "DesktopApp", "main", "smoke_test", "system_shutting_down", "webview2_version"]

logger = logging.getLogger("rpa_desktop.gui")

WINDOW_SIZE: Final = (800, 760)
MIN_SIZE: Final = (560, 480)
SMOKE_SECONDS: Final = 90.0
_WEBVIEW2_CLIENT: Final = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
"""WebView2 Runtime 在 EdgeUpdate 登錄的產品代碼（Microsoft 文件建議的偵測方式）。"""


def webview2_version() -> str | None:
    """已安裝的 WebView2 Runtime 版本；沒有時回傳 None。

    只在 Windows 上檢查，其他系統（開發環境）回傳 ``"n/a"``。
    """
    if sys.platform != "win32":
        return "n/a"
    import winreg

    places = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}",
        ),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}"),
    )
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if isinstance(value, str) and value and value != "0.0.0.0":
            return value
    return None


def _message_box(title: str, text: str) -> None:
    """Windows 的訊息方塊（沒有視窗可以顯示時用）。"""
    if sys.platform != "win32":
        logger.warning("%s：%s", title, text)
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION


def system_shutting_down() -> bool:
    """Windows 是否正在登出或關機（``GetSystemMetrics(SM_SHUTTINGDOWN)``）。

    關機時 Windows 也會要求視窗關閉；這時不能縮到通知區，否則會擋住關機。
    """
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))  # SM_SHUTTINGDOWN


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Api:
    """給頁面的 js_api：pywebview 把公開的方法變成 ``window.pywebview.api.<方法>``（回傳 Promise）。

    每次呼叫在各自的執行緒執行；屬性一律以底線開頭，免得 pywebview 把內部物件也公開給頁面。
    """

    def __init__(self, app: "DesktopApp") -> None:
        self._app = app

    def state(self) -> dict[str, object]:
        return self._app.controller.snapshot()

    def pair(self, invite: str, server: str = "", firefox: bool = False) -> bool:
        return self._app.controller.pair(str(invite), str(server or "") or None, bool(firefox))

    def pause(self, paused: bool) -> None:
        self._app.controller.set_paused(bool(paused))

    def retry(self) -> bool:
        return self._app.controller.retry()

    def set_setting(self, name: str, value: object) -> None:
        controller = self._app.controller
        if name == "autostart":
            controller.set_autostart(bool(value))
        elif name == "firefox":
            controller.set_firefox(bool(value))
        elif name == "download_host":
            controller.set_download_host(str(value or ""))
        elif name == "language":
            language = parse_locale(str(value))
            if language is not None:
                self._app.set_language(language)

    def reset_pairing(self) -> None:
        self._app.controller.reset_pairing()

    def open_logs(self) -> None:
        _open_folder(self._app.controller.home / "logs")

    def quit(self, confirmed: bool = False) -> None:
        self._app.request_quit(confirmed=bool(confirmed))

    def ready(self, user_agent: str = "") -> bool:
        logger.info("視窗已載入：%s", user_agent)
        return True


class DesktopApp:
    """視窗、通知區與 controller 的接線。"""

    def __init__(
        self,
        controller: WorkerController,
        lock: InstanceLock,
        *,
        background: bool = False,
        invite: str | None = None,
        server: str | None = None,
    ) -> None:
        self.controller = controller
        self.lock = lock
        self.background = background
        self.invite = invite
        self.server = server
        self.window: webview.Window | None = None
        self.tray = Tray(controller, on_open=self.show, on_quit=self.request_quit)
        self._quitting = False
        self._session_ending = False
        self._finished = threading.Event()
        self._push = threading.Event()
        self._shown_for_pairing = False

    # ------------------------------------------------------------ 執行

    def run(self) -> int:
        if webview2_version() is None:
            return self._run_tray_only()
        import webview

        with use_locale(self.controller.locale):
            title = t("window.title")
        # 自動啟動時只開通知區；還沒配對（或讀不到配對）時一開始就打開視窗讓人貼邀請
        hidden = self.background and self.invite is None and self._paired()
        self._shown_for_pairing = not hidden
        self.window = webview.create_window(
            title,
            html=render_page(self.controller.locale),
            js_api=Api(self),
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_SIZE,
            hidden=hidden,
            text_select=True,
        )
        self.window.events.closing += self._on_closing
        try:
            self.tray.start()
            self.controller.subscribe(self._on_change)
            self.lock.watch(self.show, self._finished, on_stop=lambda: self.request_quit(True))
            threading.Thread(target=self._pusher, name="rpa-window-push", daemon=True).start()
            webview.start(
                self._on_started,
                gui="edgechromium" if sys.platform == "win32" else None,
                private_mode=True,
            )
        finally:
            self._finish()
        return 0

    def _paired(self) -> bool:
        try:
            return self.controller.credentials.load() is not None
        except TokenStoreError:
            return False

    def _run_tray_only(self) -> int:
        with use_locale(self.controller.locale):
            title, text = t("window.webview2_missing_title"), t("window.webview2_missing")
        logger.warning("沒有 WebView2 Runtime，只用通知區")
        self.tray.on_open = lambda: _message_box(title, text)
        self.tray.on_quit = self._quit_tray_only
        self.controller.subscribe(self.tray.update)
        self.controller.start(self.invite, self.server)
        threading.Thread(target=_message_box, args=(title, text), daemon=True).start()
        self.tray.run_blocking()
        self._finish()
        return 0

    def _quit_tray_only(self) -> None:
        self._quitting = True
        self.controller.stop()
        self.tray.stop()

    def _on_started(self) -> None:
        """pywebview 的介面迴圈開始後（在另一個執行緒）。

        這時才開始配對與連線：狀態一改變就可能要叫出視窗，視窗必須已經建好。
        """
        self._watch_session_end()
        self.controller.start(self.invite, self.server)

    def _finish(self) -> None:
        self._finished.set()
        self._push.set()
        self.controller.stop(fast=self._session_ending)
        limit = QUICK_STOP_SECONDS + 2 if self._session_ending else 150.0
        if not self.controller.wait(limit):
            logger.warning("等不到執行中的任務結束，直接關閉")
        self.tray.stop()

    # ------------------------------------------------------------ 視窗

    def show(self) -> bool:
        """叫出視窗；回傳是否成功。"""
        window = self.window
        if window is None:
            return False
        try:
            window.show()
            window.restore()
        except Exception:
            logger.warning("叫出視窗失敗", exc_info=True)
            return False
        self._push.set()
        return True

    def _hide_with_hint(self) -> None:
        window = self.window
        if window is None:
            return
        window.hide()
        if self.controller.mark_tray_hint_shown():
            with use_locale(self.controller.locale):
                self.tray.notify(t("window.close_hint_title"), t("window.close_hint"))

    def _on_closing(self) -> bool:
        """按視窗的關閉鈕：縮到通知區（回傳 False 取消關閉）；結束或關機時才真的關。"""
        if self._quitting or self._session_ending:
            return True
        if system_shutting_down():  # 關機的通知可能比關閉視窗的要求晚到
            self._session_ending_now()
            return True
        threading.Thread(target=self._hide_with_hint, daemon=True).start()
        return False

    def _on_change(self) -> None:
        self.tray.update()
        if self.controller.phase == "unpaired" and not self._shown_for_pairing:
            # 自動啟動時配對失效（例如在裝置頁重新邀請）：打開視窗讓人貼新的邀請
            self._shown_for_pairing = self.show()
        self._push.set()

    def _pusher(self) -> None:
        """狀態一改變就叫頁面重新整理（頁面本身也每秒更新一次）。"""
        while not self._finished.is_set():
            self._push.wait()
            self._push.clear()
            window = self.window
            if window is None or self._finished.is_set():
                continue
            try:
                window.evaluate_js("window.rpa && window.rpa.refresh()")
            except Exception:
                logger.debug("頁面還沒準備好", exc_info=True)
            time.sleep(0.2)  # 狀態變化很密集時（下載進度）不要一直打擾頁面

    def set_language(self, language: Locale) -> None:
        self.controller.set_language(language)
        set_locale(language)
        window = self.window
        if window is not None:
            with use_locale(language):
                window.set_title(t("window.title"))
            window.load_html(render_page(language))
        self.tray.update()

    # ------------------------------------------------------------ 結束

    def request_quit(self, confirmed: bool = False) -> None:
        """結束：有任務在執行時先在視窗裡確認（從通知區選「結束」也一樣）。"""
        if self.controller.busy and not confirmed:
            self.show()
            window = self.window
            if window is not None:
                try:
                    window.evaluate_js("window.rpa && window.rpa.askQuit()")
                    return
                except Exception:
                    logger.warning("無法在視窗裡確認，直接結束", exc_info=True)
        self.quit()

    def quit(self, *, fast: bool = False) -> None:
        self._quitting = True
        self.controller.stop(fast=fast)
        window = self.window
        if window is not None:
            window.destroy()
        else:
            self.tray.stop()

    def _session_ending_now(self, sender: object = None, args: object = None) -> None:
        logger.info("Windows 正在登出或關機：取消執行中的任務並回報")
        self._session_ending = True
        self._quitting = True
        self.controller.stop(fast=True)

    def _watch_session_end(self) -> None:
        """Windows 登出或關機時通知。

        用 .NET 的 ``SystemEvents.SessionEnding``（經由 pywebview 在 Windows 上用的 pythonnet）。
        """
        if sys.platform != "win32":
            return
        try:
            clr = importlib.import_module("clr")
            clr.AddReference("System")
            win32 = importlib.import_module("Microsoft.Win32")
            handler = win32.SessionEndingEventHandler(self._session_ending_now)
            win32.SystemEvents.SessionEnding += handler
        except Exception:
            logger.warning(
                "收不到 Windows 關機的通知（關機時任務會在一分鐘後被判定失聯）", exc_info=True
            )


# ---------------------------------------------------------------- CI 的視窗自我測試


class _SmokeApi:
    """自我測試的 js_api：頁面照常畫出「尚未配對」，載入後回報 User-Agent。"""

    def __init__(self, state: dict[str, object], loaded: Callable[[str], None]) -> None:
        self._state = state
        self._loaded = loaded

    def state(self) -> dict[str, object]:
        return self._state

    def ready(self, user_agent: str = "") -> bool:
        self._loaded(str(user_agent))
        return True


def smoke_test(
    controller: WorkerController, report: Path | None, seconds: float = SMOKE_SECONDS
) -> int:
    """打開真的視窗與通知區圖示，確認頁面的腳本跑起來（WebView2 與 js_api 都正常）後結束。

    不配對、不連線。結果的格式和自我測試相同（``tools/ci_annotations.py self-test`` 可以讀）。
    """
    steps: list[dict[str, object]] = []
    loaded = threading.Event()
    agent: list[str] = []
    version = webview2_version()
    steps.append({"step": "webview2", "ok": version is not None, "detail": version or "missing"})
    if version is not None:
        import webview

        def on_loaded(user_agent: str) -> None:
            agent.append(user_agent)
            loaded.set()

        api = _SmokeApi(controller.snapshot(), on_loaded)
        window = webview.create_window(
            "RPA Worker", html=render_page(controller.locale), js_api=api, width=WINDOW_SIZE[0]
        )
        tray = Tray(controller, on_open=lambda: None, on_quit=lambda: None)

        def check() -> None:
            tray_ready = tray.start()
            page = loaded.wait(seconds)
            shown = tray_ready.wait(15)
            user_agent = agent[0] if agent else ""
            steps.append(
                {
                    "step": "window",
                    "ok": page and ("Edg/" in user_agent or sys.platform != "win32"),
                    "detail": user_agent or "page script did not report",
                }
            )
            steps.append(
                {"step": "tray", "ok": shown, "detail": "icon shown" if shown else "no icon"}
            )
            tray.stop()
            window.destroy()

        webview.start(
            check, gui="edgechromium" if sys.platform == "win32" else None, private_mode=True
        )
    summary: dict[str, object] = {"ok": all(bool(step["ok"]) for step in steps), "steps": steps}
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    logger.info("視窗自我測試：%s", text)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text + "\n", encoding="utf-8")
    return 0 if summary["ok"] else 1


# ---------------------------------------------------------------- 入口


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rpa-worker", description=t("worker.description"))
    parser.add_argument("--background", action="store_true", help=t("window.background_help"))
    parser.add_argument("--invite", metavar="INVITE", help=t("worker.invite_help"))
    parser.add_argument("--server", metavar="URL", help=t("worker.server_help"))
    parser.add_argument("--smoke-test", action="store_true", help=t("window.smoke_help"))
    parser.add_argument("--report", type=Path, metavar="FILE", help=t("window.report_help"))
    return parser


def main(argv: Sequence[str] = (), *, environ: MutableMapping[str, str] | None = None) -> int:
    """視窗版的入口；回傳結束碼。"""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    set_locale(resolve_locale(env))
    args = _parser().parse_args(list(argv))
    ensure_browsers_path(env)
    home = data_dir(env)
    setup_logging(home / "logs")
    build = load()
    logger.info("RPA Worker %s 視窗版，資料夾 %s", build.version, home)
    override = env.get(ENV_VAR)

    def controller(autostart: AutoStart) -> WorkerController:
        return WorkerController(
            home=home,
            build=build,
            environ=env,
            credentials=Credentials(home),
            autostart=autostart,
            language=parse_locale(override) if override else None,
        )

    if args.smoke_test:
        return smoke_test(controller(AutoStart(None, Path(sys.executable))), args.report)
    lock = InstanceLock(home)
    if not lock.acquire():
        logger.info("已經有一份在執行：請它叫出視窗")
        lock.request_show()
        return 0
    try:
        worker = controller(AutoStart.for_this_app())
        set_locale(worker.locale)
        app = DesktopApp(
            worker, lock, background=bool(args.background), invite=args.invite, server=args.server
        )
        return app.run()
    except Exception as error:
        # 視窗程式沒有主控台：記在日誌並用訊息方塊說明，不讓 PyInstaller 跳出原始的錯誤對話框
        logger.exception("RPA Worker 視窗版停止了")
        with use_locale(resolve_locale(env)):
            _message_box(t("window.title"), t("window.crashed", error=error))
        return 1
    finally:
        lock.release()
