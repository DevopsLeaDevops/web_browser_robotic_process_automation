"""RPA Worker 的通知區圖示（M10.1，ADR 0014）：pystray。

選單：開啟視窗（預設，雙擊圖示也是）／暫停接任務（勾選）／結束。圖示右下角的圓點與滑鼠移上去的
說明跟著狀態變（:func:`rpa_desktop.icon.status_color`）。選單文字依使用者選的語言。

pystray 在 Windows 上可以在任何執行緒執行（:meth:`Tray.start` 開一個背景執行緒）；視窗（pywebview）
要在主執行緒。沒有 WebView2 時改由 :meth:`Tray.run_blocking` 在主執行緒執行，只靠通知區工作。
"""

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from rpa_core.i18n import use_locale
from rpa_desktop.controller import WorkerController
from rpa_desktop.i18n import t
from rpa_desktop.icon import draw, status_color

if TYPE_CHECKING:
    import pystray

__all__ = ["Tray"]

logger = logging.getLogger("rpa_desktop.tray")


class Tray:
    """通知區圖示。動作由呼叫的人提供（開啟視窗、結束）。"""

    def __init__(
        self,
        controller: WorkerController,
        *,
        on_open: Callable[[], object],
        on_quit: Callable[[], object],
    ) -> None:
        self.controller = controller
        self.on_open = on_open
        self.on_quit = on_quit
        self.ready = threading.Event()
        self._icon: pystray.Icon | None = None
        self._shown: tuple[str, str] | None = None
        self._lock = threading.Lock()  # 狀態通知可能同時從幾個執行緒來

    def _menu(self) -> "pystray.Menu":
        import pystray

        with use_locale(self.controller.locale):
            return pystray.Menu(
                pystray.MenuItem(t("tray.open"), self._open, default=True),
                pystray.MenuItem(
                    t("tray.pause"), self._toggle_pause, checked=lambda item: self.controller.paused
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(t("tray.quit"), self._quit),
            )

    def _tooltip(self) -> str:
        with use_locale(self.controller.locale):
            status = t("window.phase." + self.controller.phase)
            return t("tray.tooltip", status=status)

    def _create(self) -> "pystray.Icon":
        import pystray

        phase = self.controller.phase
        icon = pystray.Icon(
            "rpa-worker", draw(64, status_color(phase)), self._tooltip(), self._menu()
        )
        self._icon = icon
        self._shown = (phase, self.controller.locale)
        return icon

    def _setup(self, icon: "pystray.Icon") -> None:
        icon.visible = True
        self.ready.set()

    def start(self) -> threading.Event:
        """在背景執行緒顯示圖示；回傳圖示出現時設定的 Event。"""
        icon = self._create()

        def run() -> None:
            try:
                icon.run(self._setup)
            except Exception:
                logger.exception("通知區圖示停止了")

        threading.Thread(target=run, name="rpa-tray", daemon=True).start()
        return self.ready

    def run_blocking(self) -> None:
        """在目前的執行緒顯示圖示，直到 :meth:`stop`（沒有視窗時用）。"""
        self._create().run(self._setup)

    def update(self) -> None:
        """狀態或語言改變時更新圖示、說明與選單。"""
        icon = self._icon
        if icon is None:
            return
        with self._lock:
            phase, locale = self.controller.phase, self.controller.locale
            if self._shown == (phase, locale):
                return
            try:
                if self._shown is None or self._shown[0] != phase:
                    icon.icon = draw(64, status_color(phase))
                if self._shown is None or self._shown[1] != locale:
                    icon.menu = self._menu()
                icon.title = self._tooltip()
                icon.update_menu()
            except Exception:
                logger.exception("更新通知區圖示失敗")
            self._shown = (phase, locale)

    def notify(self, title: str, message: str) -> None:
        icon = self._icon
        if icon is None:
            return
        try:
            icon.notify(message, title)
        except Exception:
            logger.warning("通知區的提示顯示失敗", exc_info=True)

    def stop(self) -> None:
        icon = self._icon
        if icon is None:
            return
        try:
            icon.visible = False
            icon.stop()
        except Exception:
            logger.warning("通知區圖示停不下來", exc_info=True)

    # ------------------------------------------------------------ 選單動作

    def _open(self, icon: object = None, item: object = None) -> None:
        self.on_open()

    def _toggle_pause(self, icon: object = None, item: object = None) -> None:
        self.controller.set_paused(not self.controller.paused)

    def _quit(self, icon: object = None, item: object = None) -> None:
        self.on_quit()
