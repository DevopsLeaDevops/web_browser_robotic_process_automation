"""macOS 的 RPA Worker：選單列圖示與 App 層級的系統事件（2026-10-22，ADR 0014 的保留方案）。

Windows 的通知區（:mod:`rpa_desktop.tray`）用 pystray；在 macOS 上 pystray 與 pywebview 都要在
主執行緒跑 NSApplication 的迴圈，會互相搶。這裡直接用 PyObjC 的 ``NSStatusItem``，掛在 pywebview
的迴圈裡；AppKit 只能在主執行緒呼叫，所以一律經由 ``AppHelper.callAfter`` 排到主執行緒。

- :class:`MenuBar`：選單列圖示，介面和 :class:`rpa_desktop.tray.Tray` 相同（開啟視窗、暫停接任務、
  結束；圖示右下角的圓點跟著狀態）。選單的動作在另一個執行緒執行：pywebview 的視窗操作在主執行緒
  呼叫會等不到自己。
- :func:`set_dock_visible`：視窗收起來時不佔 Dock（``Accessory``），叫出視窗時恢復（``Regular``）。
- :func:`on_reopen`：App 已經在執行時，在 Finder 再雙擊或點 Dock 圖示（``rapp`` 事件）→ 叫出視窗。
  Windows 版靠第二份程式寫 ``show.request``；macOS 的 LaunchServices 不另外啟動第二份。
- :func:`on_power_off`：登出、重新開機、關機前（``NSWorkspaceWillPowerOffNotification``）。
- :func:`terminating`：AppKit 正在問要不要結束 App（⌘Q、選單的「結束」、Apple 事件），而不是按了
  視窗的關閉鈕：pywebview 兩種都只送一個 closing 事件，要看主執行緒是不是在
  ``applicationShouldTerminate_`` 裡。
- :func:`notify`、:func:`alert`：通知與提示（``osascript``；沒有簽章的 App 也能用）。
- :func:`exit_process`：視窗關了、收拾完之後直接結束程序（pywebview 留下的執行緒不是 daemon）。

其他系統上都不做事（Linux 的 CI 也能載入、測試這個模組）。真的選單列圖示在 CI 的 macOS 上以打包版的
``--smoke-test`` 打開。
"""

import contextlib
import importlib
import io
import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any, Final

from rpa_core.i18n import use_locale
from rpa_desktop.controller import WorkerController
from rpa_desktop.i18n import t
from rpa_desktop.icon import draw, status_color

__all__ = [
    "MenuBar",
    "alert",
    "exit_process",
    "lingering_threads",
    "notify",
    "on_power_off",
    "on_reopen",
    "set_dock_visible",
    "terminating",
]

logger = logging.getLogger("rpa_desktop.macos")

ICON_POINTS: Final = 18.0
"""選單列圖示的大小（點）；圖片用兩倍的像素，Retina 螢幕上才清楚。"""
_TERMINATE: Final = "applicationShouldTerminate_"
_REOPEN: Final = b"applicationShouldHandleReopen:hasVisibleWindows:"
_ACTIONS: Final = {"openWindow_": "open", "togglePause_": "pause", "quit_": "quit"}

_active: list["MenuBar"] = []
"""目前的選單列圖示（一個程序只有一個）；選單動作經由它找到 controller。"""
_retained: list[Any] = []
"""要一直留著的 Objective-C 物件（通知的觀察者）；釋放了就收不到通知。"""


def _darwin(platform: str | None = None) -> bool:
    return (sys.platform if platform is None else platform) == "darwin"


def _appkit() -> Any:
    return importlib.import_module("AppKit")


def _foundation() -> Any:
    return importlib.import_module("Foundation")


def _on_main(action: Callable[[], object], what: str) -> None:
    """在主執行緒執行（已經在主執行緒就直接執行）；失敗只記日誌，不影響接任務。"""

    def guarded() -> None:
        try:
            action()
        except Exception:
            logger.warning("%s失敗", what, exc_info=True)

    if threading.current_thread() is threading.main_thread():
        guarded()
        return
    helper = importlib.import_module("PyObjCTools.AppHelper")
    helper.callAfter(guarded)


# ---------------------------------------------------------------- 選單列圖示


def _dispatch(action: str) -> None:
    """選單項目被按了（主執行緒）：交給另一個執行緒處理。"""
    menu = _active[0] if _active else None
    if menu is not None:
        threading.Thread(target=menu.act, args=(action,), name="rpa-menubar", daemon=True).start()


def _target() -> Any:
    """選單項目的 target：一個 NSObject，三個動作各一個 selector。

    用 ``type()`` 建立 Objective-C 類別（PyObjC 依名稱推出 ``openWindow:`` 這類 selector）；
    一個程序只建一次，同名的類別不能註冊第二次。
    """
    foundation = _foundation()
    objc = importlib.import_module("objc")
    cls: Any
    try:
        cls = objc.lookUpClass("RPAWorkerMenuTarget")
    except objc.nosuchclass_error:

        def method(action: str) -> Callable[[object, object], None]:
            def handler(self: object, sender: object) -> None:
                _dispatch(action)

            return handler

        methods = {name: method(action) for name, action in _ACTIONS.items()}
        cls = type("RPAWorkerMenuTarget", (foundation.NSObject,), methods)
    return cls.alloc().init()


def _image(phase: str) -> Any:
    buffer = io.BytesIO()
    draw(int(ICON_POINTS * 2), status_color(phase)).save(buffer, format="PNG")
    raw = buffer.getvalue()
    data = _foundation().NSData.dataWithBytes_length_(raw, len(raw))
    image = _appkit().NSImage.alloc().initWithData_(data)
    image.setSize_((ICON_POINTS, ICON_POINTS))
    return image


class MenuBar:
    """選單列圖示。動作由呼叫的人提供（開啟視窗、結束）。"""

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
        self._item: Any = None
        self._target: Any = None
        self._shown: tuple[str, str, bool] | None = None
        self._lock = threading.Lock()

    def labels(self) -> list[str]:
        """選單的文字（目前的語言）；空字串是分隔線。"""
        with use_locale(self.controller.locale):
            return [t("tray.open"), t("tray.pause"), "", t("tray.quit")]

    def tooltip(self) -> str:
        with use_locale(self.controller.locale):
            return t("tray.tooltip", status=t("window.phase." + self.controller.phase))

    def act(self, action: str) -> None:
        """執行選單動作（不在主執行緒）。"""
        if action == "open":
            self.on_open()
        elif action == "pause":
            self.controller.set_paused(not self.controller.paused)
        elif action == "quit":
            self.on_quit()

    def start(self) -> threading.Event:
        """在主執行緒建立圖示；回傳圖示出現時設定的 Event。"""
        _active[:] = [self]
        _on_main(self._create, "建立選單列圖示")
        return self.ready

    def run_blocking(self) -> None:
        """只有通知區、沒有視窗的模式是 Windows 缺 WebView2 時的退路；macOS 一定有 WKWebView。"""
        raise NotImplementedError("macOS always has a window")

    def _create(self) -> None:
        appkit = _appkit()
        appkit.NSApplication.sharedApplication()
        bar = appkit.NSStatusBar.systemStatusBar()
        self._target = _target()
        self._item = bar.statusItemWithLength_(appkit.NSVariableStatusItemLength)
        self._apply()
        self.ready.set()

    def _menu(self) -> Any:
        appkit = _appkit()
        menu = appkit.NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        selectors = ("openWindow:", "togglePause:", None, "quit:")
        for label, selector in zip(self.labels(), selectors, strict=True):
            if selector is None:
                menu.addItem_(appkit.NSMenuItem.separatorItem())
                continue
            item = appkit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, selector, ""
            )
            item.setTarget_(self._target)
            if selector == "togglePause:":
                item.setState_(1 if self.controller.paused else 0)  # NSControlStateValueOn／Off
            menu.addItem_(item)
        return menu

    def _apply(self) -> None:
        """（主執行緒）圖示、說明與選單換成目前的狀態與語言。"""
        item = self._item
        if item is None:
            return
        key = (self.controller.phase, self.controller.locale, self.controller.paused)
        button = item.button()
        button.setImage_(_image(key[0]))
        button.setToolTip_(self.tooltip())
        item.setMenu_(self._menu())
        self._shown = key

    def update(self) -> None:
        """狀態、語言或暫停改變時更新圖示與選單（任何執行緒都可以呼叫）。"""
        key = (self.controller.phase, self.controller.locale, self.controller.paused)
        with self._lock:
            if self._item is None or self._shown == key:
                return
        _on_main(self._apply, "更新選單列圖示")

    def notify(self, title: str, message: str) -> None:
        notify(title, message)

    def stop(self) -> None:
        item, self._item = self._item, None
        if _active and _active[0] is self:
            _active.clear()
        if item is None:
            return

        def remove() -> None:
            _appkit().NSStatusBar.systemStatusBar().removeStatusItem_(item)

        _on_main(remove, "移除選單列圖示")


# ---------------------------------------------------------------- App 層級的事件


def set_dock_visible(visible: bool, platform: str | None = None) -> None:
    """視窗收起來時不佔 Dock 與選單列的 App 選單；叫出視窗時恢復並放到最前面。"""
    if not _darwin(platform):
        return

    def apply() -> None:
        appkit = _appkit()
        app = appkit.NSApplication.sharedApplication()
        if visible:
            app.setActivationPolicy_(appkit.NSApplicationActivationPolicyRegular)
            app.activateIgnoringOtherApps_(True)
        else:
            app.setActivationPolicy_(appkit.NSApplicationActivationPolicyAccessory)

    _on_main(apply, "切換 Dock 圖示")


def on_reopen(callback: Callable[[], object], platform: str | None = None) -> None:
    """App 已經在執行時再從 Finder 打開、或點 Dock 圖示：在另一個執行緒呼叫 ``callback``。

    pywebview 的 App 委派沒有處理這個事件（視窗收起來後就叫不出來），所以在它的類別上補一個
    ``applicationShouldHandleReopen:hasVisibleWindows:``，再重新設定委派讓 AppKit 看到。
    要在 pywebview 的迴圈開始之後呼叫（委派那時才設定）。
    """
    if not _darwin(platform):
        return

    def install() -> None:
        objc = importlib.import_module("objc")
        app = _appkit().NSApplication.sharedApplication()
        delegate = app.delegate()
        if delegate is None:
            logger.warning("找不到 App 的委派：從 Finder 再打開時叫不出視窗")
            return

        def reopen(self: object, sender: object, has_visible: bool) -> bool:
            threading.Thread(target=callback, name="rpa-reopen", daemon=True).start()
            return True

        method = objc.selector(reopen, selector=_REOPEN, signature=b"Z@:@Z")
        objc.classAddMethods(type(delegate), [method])
        app.setDelegate_(delegate)

    _on_main(install, "設定再次打開時叫出視窗")


def on_power_off(callback: Callable[[], object], platform: str | None = None) -> None:
    """登出、重新開機或關機前在主執行緒呼叫 ``callback``（之後 AppKit 才要求 App 結束）。"""
    if not _darwin(platform):
        return

    def install() -> None:
        appkit = _appkit()
        center = appkit.NSWorkspace.sharedWorkspace().notificationCenter()

        def handler(notification: object) -> None:
            callback()

        observer = center.addObserverForName_object_queue_usingBlock_(
            appkit.NSWorkspaceWillPowerOffNotification,
            None,
            _foundation().NSOperationQueue.mainQueue(),
            handler,
        )
        _retained.append(observer)

    _on_main(install, "註冊登出與關機的通知")


def terminating(platform: str | None = None) -> bool:
    """AppKit 正在問要不要結束整個 App（主執行緒在 ``applicationShouldTerminate_`` 裡）。"""
    if not _darwin(platform):
        return False
    main = threading.main_thread().ident
    frames = sys._current_frames()  # pyright: ignore[reportPrivateUsage]
    frame = frames.get(main) if main is not None else None
    while frame is not None:
        if frame.f_code.co_name == _TERMINATE:
            return True
        frame = frame.f_back
    return False


# ---------------------------------------------------------------- 提示與結束


def _applescript(text: str) -> str:
    """AppleScript 的字串：只跳脫反斜線、引號與換行（中文照原樣，不能變成 \\u 跳脫）。"""
    return json.dumps(text, ensure_ascii=False)


def _osascript(script: str, timeout: float) -> None:
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        logger.debug("osascript 失敗", exc_info=True)


def notify(title: str, message: str, platform: str | None = None) -> None:
    """系統通知（不等它顯示完）。"""
    if not _darwin(platform):
        logger.info("%s：%s", title, message)
        return
    script = f"display notification {_applescript(message)} with title {_applescript(title)}"
    threading.Thread(target=_osascript, args=(script, 30), daemon=True).start()


def alert(title: str, text: str, platform: str | None = None) -> None:
    """沒有視窗可以顯示時的提示（等使用者按「好」）。"""
    logger.warning("%s：%s", title, text)
    if _darwin(platform):
        _osascript(f"display alert {_applescript(title)} message {_applescript(text)}", 600)


def lingering_threads() -> list[str]:
    """還在跑、會擋住程序結束的執行緒（pywebview 的事件與注入腳本的執行緒都不是 daemon）。"""
    return sorted(
        thread.name
        for thread in threading.enumerate()
        if thread.is_alive() and not thread.daemon and thread is not threading.main_thread()
    )


def exit_process(code: int) -> int:
    """視窗關了、收拾完之後直接結束程序，不等 pywebview 留下、可能永遠等不到的執行緒。"""
    lingering = lingering_threads()
    if lingering:
        logger.info("結束時還在跑的執行緒：%s", ", ".join(lingering))
    logging.shutdown()
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    os._exit(code)
