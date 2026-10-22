"""RPA 錄製端 App（M10.2，ADR 0014）：雙擊「RPA 錄製端」開啟的就是這個（macOS，WKWebView）。

- 視窗只載入本機閘道（:class:`rpa_worker.gateway.Gateway`）的網址：管理 Portal 的頁面經由閘道加上
  權杖轉送；App 自己的頁面（狀態、配對、下載瀏覽器、設定）在閘道**另一個埠**的 ``/__desktop/``
  （:mod:`rpa_desktop.recorder_pages`），和 Portal 不同來源，Portal 的頁面叫不動 App。狀態與動作在
  :class:`rpa_desktop.recorder_controller.RecorderController`。配對失效時主視窗回到 App 的頁面。
- 選單「RPA 錄製端」：狀態與設定、管理 Portal、重新整理。系統預設的「編輯」選單讓 ⌘V 能貼上邀請。
- ``target="_blank"`` 的連結（報告、截圖、執行檔案）在 App 內開新視窗；連到別的網站（例如角色的
  登入網址）時用預設瀏覽器。下載的檔案存到使用者選的位置（預設「下載項目」）。
- 關掉主視窗就結束 App；有錄製、調試或人工登入在進行時先確認（⌘Q 也一樣）。結束時不等管理
  Portal 的長輪詢回來：直接結束這台的子程序、刪暫存，讓馬上再打開也行。
- 只執行一份：已經在執行時叫出那一份的視窗後結束（:mod:`rpa_desktop.single_instance`）。
- ``--smoke-test``：CI 用，打開真的視窗，確認 App 的頁面經由閘道（含 Cookie）載入後結束。
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from rpa_core.i18n import ENV_VAR, Locale, parse_locale, set_locale, use_locale
from rpa_desktop import macos
from rpa_desktop.build_info import load
from rpa_desktop.credentials import Credentials, KeyringStore, TokenStore
from rpa_desktop.i18n import resolve_locale, t
from rpa_desktop.logs import setup_logging
from rpa_desktop.recorder_controller import SERVICE, RecorderController
from rpa_desktop.recorder_pages import DesktopPages, notice_page, offline_page
from rpa_desktop.release import RELEASES_URL
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.worker_app import ensure_browsers_path
from rpa_worker.gateway import COOKIE, Gateway

if TYPE_CHECKING:
    import webview

__all__ = ["ENV_HOME", "LOG_FILE", "RecorderApp", "main", "recorder_dir", "smoke_test"]

logger = logging.getLogger("rpa_desktop.recorder_gui")

ENV_HOME: Final = "RPA_RECORDER_HOME"
WINDOW_SIZE: Final = (1280, 860)
MIN_SIZE: Final = (720, 520)
CHILD_SIZE: Final = (1100, 800)
SMOKE_SECONDS: Final = 90.0
_BROWSER_NAME: Final = "rpa-recorder-windows"
LOG_FILE: Final = "recorder.log"


def recorder_dir(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """RPA 錄製端的資料夾：配對、設定、日誌、錄製與調試的暫存。"""
    override = environ.get(ENV_HOME)
    if override:
        return Path(override).expanduser()
    home = Path(environ.get("HOME") or environ.get("USERPROFILE") or Path.home())
    if platform == "darwin":
        return home / "Library" / "Application Support" / "rpa" / "recorder"
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "rpa" / "recorder"
    base = environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(base) / "rpa" / "recorder"


def _open_external(url: str) -> bool:
    """用系統的預設瀏覽器打開（不經過 App 的視窗）；只接受 http、https（不讓頁面叫起別的程式）。"""
    if urlsplit(url).scheme not in ("http", "https"):
        logger.warning("不打開這種網址：%s", url.split(":", 1)[0])
        return False
    return _launch(url)


def _launch(target: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.Popen(["xdg-open", target])
    except OSError:
        logger.warning("打不開 %s", target, exc_info=True)
        return False
    return True


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _launch(str(path))


class _WindowBrowser(webbrowser.BaseBrowser):
    """``webbrowser.open`` 的去處：閘道的網址開 App 的新視窗，其他的交給系統的預設瀏覽器。

    pywebview 遇到 ``target="_blank"`` 的連結時，在主執行緒（WKUIDelegate）呼叫
    ``webbrowser.open``；系統瀏覽器沒有閘道的 Cookie，所以閘道的網址要留在 App 裡。pywebview 在
    主執行緒呼叫 ``create_window`` 時不會建出視窗，所以新視窗在另一個執行緒開。
    """

    def __init__(self, gateway: Gateway, open_window: Callable[[str], object]) -> None:
        super().__init__(_BROWSER_NAME)
        self.gateway = gateway
        self.open_window = open_window

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        origin = self.gateway.origin
        if url == origin or url.startswith(origin + "/"):
            threading.Thread(target=self.open_window, args=(url,), daemon=True).start()
            return True
        return _open_external(url)


def _share_cookie_with_downloads(gateway: Gateway) -> None:
    """macOS：下載不能顯示的檔案時，pywebview 用 ``NSURLSession`` 重新下載，
    不帶 WKWebView 的 Cookie。

    把閘道的 Cookie 也放進 App 的 ``NSHTTPCookieStorage``，那些下載才進得了閘道。
    """
    if sys.platform != "darwin":
        return
    try:
        import Foundation  # pyright: ignore[reportMissingImports]

        cookie = Foundation.NSHTTPCookie.cookieWithProperties_(  # pyright: ignore
            {"Domain": "127.0.0.1", "Path": "/", "Name": COOKIE, "Value": gateway.secret}
        )
        Foundation.NSHTTPCookieStorage.sharedHTTPCookieStorage().setCookie_(cookie)  # pyright: ignore
    except Exception:
        logger.warning("下載用的 Cookie 設不上：無法顯示的檔案可能下載不了", exc_info=True)


class RecorderApp:
    """視窗、閘道與 controller 的接線。"""

    def __init__(
        self,
        controller: RecorderController,
        lock: InstanceLock,
        *,
        invite: str | None = None,
        server: str | None = None,
    ) -> None:
        self.controller = controller
        self.lock = lock
        self.invite = invite
        self.server = server
        self.pages = DesktopPages(
            controller,
            on_quit=lambda: self.request_quit(confirmed=True),
            on_logs=lambda: _open_folder(controller.home / "logs"),
            on_download=lambda: _open_external(RELEASES_URL),
            on_language=self._set_language,
            portal_url=lambda: self.gateway.login_url("/"),
        )
        self.gateway = Gateway(
            None,
            controller.token,
            local=self.pages,
            on_unauthorized=controller.unauthorized,
            offline_page=offline_page(lambda: controller.locale, lambda: self.gateway.server),
            notice_page=notice_page(lambda: controller.locale),
        )
        controller.attach(self.gateway)
        self.window: webview.Window | None = None
        self.children: list[webview.Window] = []
        self._quitting = False
        self._asking = False
        self._finished = threading.Event()
        self._phase: str | None = None

    # ------------------------------------------------------------ 執行

    def run(self) -> int:
        import webview
        from webview.menu import Menu, MenuAction, MenuSeparator

        self.gateway.start()
        webbrowser.register(
            _BROWSER_NAME, None, _WindowBrowser(self.gateway, self.open_window), preferred=True
        )
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # 經由上面的 _WindowBrowser
        with use_locale(self.controller.locale):
            title = t("recorder.title")
            menu = [
                Menu(
                    t("recorder.menu"),
                    [
                        MenuAction(t("recorder.menu_status"), self.go_desktop),
                        MenuAction(t("recorder.menu_portal"), self.go_portal),
                        MenuSeparator(),
                        MenuAction(t("recorder.menu_reload"), self.reload),
                    ],
                )
            ]
        self.window = webview.create_window(
            title,
            url=self.gateway.desktop_url(),
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_SIZE,
            text_select=True,
            zoomable=True,
        )
        self.window.events.closing += self._on_closing
        self.window.events.closed += self._on_closed
        self.controller.subscribe(self._on_change)
        try:
            self.lock.watch(self.show, self._finished, on_stop=lambda: self.request_quit(True))
            # 不用私密模式：管理 Portal 記住的介面語言之類的 Cookie 留著；閘道的 Cookie 每次啟動都換
            webview.start(self._on_started, private_mode=False, menu=menu)
        finally:
            self._finish()
        return 0

    def _on_started(self) -> None:
        _share_cookie_with_downloads(self.gateway)
        self.controller.start(self.invite, self.server)

    def _finish(self) -> None:
        # 先結束子程序、刪暫存，不等管理 Portal 的長輪詢（最多 25 秒）回來：
        # 程序還在、鎖還沒放開時，馬上再打開 App 會什麼都沒發生
        self.controller.stop_now()
        if not self.controller.wait(10):
            logger.info("錄製端的連線還沒結束，直接關閉")
        self._finished.set()
        self.gateway.close()

    # ------------------------------------------------------------ 視窗

    def go_desktop(self) -> None:
        window = self.window
        if window is not None:
            window.load_url(self.gateway.desktop_url())

    def go_portal(self) -> None:
        window = self.window
        if window is not None and self.gateway.server is not None:
            window.load_url(self.gateway.login_url("/"))

    def _on_change(self) -> None:
        """配對失效（重新邀請、停用、刪除）時，主視窗回到 App 的頁面貼新的邀請。"""
        phase = self.controller.phase
        previous, self._phase = self._phase, phase
        if phase == "unpaired" and previous not in (None, "starting", "unpaired", "pairing"):
            self.go_desktop()

    def reload(self) -> None:
        window = self.window
        if window is not None:
            window.evaluate_js("location.reload()")

    def show(self) -> bool:
        window = self.window
        if window is None:
            return False
        try:
            window.show()
            window.restore()
        except Exception:
            logger.warning("叫出視窗失敗", exc_info=True)
            return False
        return True

    def open_window(self, url: str) -> None:
        """在 App 裡開新視窗（報告、截圖）；和主視窗共用 Cookie。"""
        import webview

        with use_locale(self.controller.locale):
            title = t("recorder.title")
        if self._quitting:
            return
        child = webview.create_window(
            title, url=url, width=CHILD_SIZE[0], height=CHILD_SIZE[1], text_select=True
        )
        self.children.append(child)
        child.events.closed += lambda: self._forget(child)

    def _forget(self, child: "webview.Window") -> None:
        if child in self.children:
            self.children.remove(child)

    def _set_language(self, language: Locale) -> None:
        set_locale(language)
        window = self.window
        if window is not None:
            with use_locale(language):
                window.set_title(t("recorder.title"))

    # ------------------------------------------------------------ 結束

    def _on_closing(self) -> bool:
        """按主視窗的關閉鈕或 ⌘Q：一律先取消（回傳 False），在另一個執行緒確認後由 :meth:`quit` 關。

        ⌘Q 時直接放行的話 AppKit 會立刻結束程序，``webview.start`` 不會回來，子程序與暫存都
        來不及收拾；由 :meth:`quit` 關掉主視窗則會照常回到 :meth:`run` 的 ``_finish``。
        """
        if self._quitting:
            return True
        if not self._asking:
            self._asking = True
            threading.Thread(target=self._confirm_quit, daemon=True).start()
        return False

    def _confirm_quit(self) -> None:
        """有進行中的工作時先確認；沒有就直接結束。"""
        try:
            window = self.window
            if window is None:
                return
            active = self.controller.active
            if active:
                with use_locale(self.controller.locale):
                    title = t("recorder.quit_title")
                    text = t("recorder.quit_active", count=active)
                if not window.create_confirmation_dialog(title, text):
                    return
            self.quit()
        finally:
            self._asking = False

    def _on_closed(self) -> None:
        """主視窗關了：其他視窗一起關，App 結束。"""
        self._quitting = True
        for child in list(self.children):
            try:
                child.destroy()
            except Exception:
                logger.debug("視窗已經關了", exc_info=True)

    def request_quit(self, confirmed: bool = False) -> None:
        if not confirmed:
            threading.Thread(target=self._confirm_quit, daemon=True).start()
            return
        self.quit()

    def quit(self) -> None:
        self._quitting = True
        self.controller.stop()
        window = self.window
        if window is not None:
            window.destroy()


# ---------------------------------------------------------------- CI 的視窗自我測試


def smoke_test(
    controller: RecorderController, report: Path | None, seconds: float = SMOKE_SECONDS
) -> int:
    """打開真的視窗，確認 App 的頁面經由本機閘道（密語 Cookie）載入、頁面的腳本跑起來後結束。

    不配對、不連線。結果的格式和自我測試相同（``tools/ci_annotations.py self-test`` 可以讀）。
    """
    steps: list[dict[str, object]] = []
    loaded = threading.Event()
    agent: list[str] = []

    def ready(user_agent: str) -> None:
        agent.append(user_agent)
        loaded.set()

    pages = DesktopPages(controller, on_ready=ready)
    gateway = Gateway(None, controller.token, local=pages)
    gateway.start()
    try:
        import webview

        window = webview.create_window(
            "RPA Recorder", url=gateway.desktop_url(), width=WINDOW_SIZE[0]
        )

        def check() -> None:
            page = loaded.wait(seconds)
            user_agent = agent[0] if agent else ""
            steps.append(
                {
                    "step": "window",
                    "ok": page and ("AppleWebKit" in user_agent or sys.platform != "darwin"),
                    "detail": user_agent or "page script did not report",
                }
            )
            window.destroy()

        webview.start(check, private_mode=True)
    except Exception as error:
        logger.exception("視窗自我測試失敗")
        steps.append({"step": "window", "ok": False, "detail": f"{type(error).__name__}: {error}"})
    finally:
        gateway.close()
    if not steps:
        steps.append({"step": "window", "ok": False, "detail": "window did not start"})
    lingering = _lingering()
    steps.append(
        {"step": "threads", "ok": True, "detail": ", ".join(lingering) or "none"}
    )  # 只是記錄：結束時由 _exit 直接結束程序
    summary: dict[str, object] = {"ok": all(bool(step["ok"]) for step in steps), "steps": steps}
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    logger.info("視窗自我測試：%s", text)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text + "\n", encoding="utf-8")
    return 0 if summary["ok"] else 1


# ---------------------------------------------------------------- 入口


def _alert(title: str, text: str) -> None:
    """沒有視窗可以顯示時的提示（macOS 用 osascript；其他系統只記日誌）。"""
    macos.alert(title, text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rpa-recorder", description=t("recorder.description"))
    parser.add_argument("--invite", metavar="INVITE", help=t("recorder.invite_help"))
    parser.add_argument("--server", metavar="URL", help=t("recorder.server_help"))
    parser.add_argument("--smoke-test", action="store_true", help=t("recorder.smoke_help"))
    parser.add_argument("--report", type=Path, metavar="FILE", help=t("recorder.report_help"))
    return parser


def _lingering() -> list[str]:
    """還在跑、會擋住程序結束的執行緒（pywebview 的事件與注入腳本的執行緒都不是 daemon）。"""
    return macos.lingering_threads()


def _exit(code: int) -> int:
    """視窗關了、收拾完之後直接結束程序。

    pywebview 在背景開的執行緒（例如頁面載入時注入腳本、等 JavaScript 的結果）在視窗關掉後
    可能永遠等不到，又不是 daemon：一般的結束會一直等它們，App 關不掉。
    """
    return macos.exit_process(code)


def main(
    argv: Sequence[str] = (),
    *,
    environ: MutableMapping[str, str] | None = None,
    store: TokenStore | None = None,
    exit_process: bool = True,
) -> int:
    """錄製端 App 的入口；回傳結束碼。

    ``exit_process`` 時開過視窗就直接結束程序（見 :func:`_exit`），不會回來。
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    set_locale(resolve_locale(env))
    # macOS 的 App 啟動時可能帶著 -psn_… 之類系統給的參數：不認得的參數略過
    args, _ = _parser().parse_known_args(list(argv))
    ensure_browsers_path(env)
    home = recorder_dir(env)
    setup_logging(home / "logs", file=home / "logs" / LOG_FILE)
    build = load()
    logger.info("RPA 錄製端 %s，資料夾 %s", build.version, home)
    override = env.get(ENV_VAR)
    controller = RecorderController(
        home=home,
        build=build,
        environ=env,
        credentials=Credentials(home, KeyringStore(SERVICE) if store is None else store),
        language=parse_locale(override) if override else None,
    )
    set_locale(controller.locale)
    if args.smoke_test:
        code = smoke_test(controller, args.report)
        return _exit(code) if exit_process else code
    lock = InstanceLock(home)
    if not lock.acquire():
        logger.info("已經有一份在執行：請它叫出視窗")
        lock.request_show()
        return 0
    try:
        code = RecorderApp(controller, lock, invite=args.invite, server=args.server).run()
    except Exception as error:
        logger.exception("RPA 錄製端停止了")
        with use_locale(controller.locale):
            _alert(t("recorder.title"), t("recorder.crashed", error=error))
        code = 1
    finally:
        lock.release()
    return _exit(code) if exit_process else code
