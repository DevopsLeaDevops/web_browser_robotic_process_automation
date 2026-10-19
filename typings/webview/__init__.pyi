# pyright（strict）用的最小 stub，只寫倉庫實際用到的部分（rpa_desktop，M10.1、M10.2）。
# pywebview 只在 Windows 與 macOS 安裝，Linux 的 CI 與開發環境沒有；介面以 pywebview 5／6 的
# 文件為準，用到新的函式時在這裡補上。typings/ 是 pyright 的 stubPath 預設位置，
# 優先於套件自己的型別。
from collections.abc import Callable, MutableMapping
from typing import Any

from webview.menu import Menu

class Event:
    def __iadd__(self, handler: Callable[..., Any]) -> Event: ...
    def __isub__(self, handler: Callable[..., Any]) -> Event: ...

class WindowEvents:
    closing: Event
    closed: Event
    loaded: Event
    shown: Event

class Window:
    events: WindowEvents
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def restore(self) -> None: ...
    def destroy(self) -> None: ...
    def load_html(self, content: str) -> None: ...
    def load_url(self, url: str) -> None: ...
    def get_current_url(self) -> str | None: ...
    def create_confirmation_dialog(self, title: str, message: str) -> bool: ...
    def evaluate_js(self, script: str) -> Any: ...
    def set_title(self, title: str) -> None: ...

def create_window(
    title: str,
    url: str | None = None,
    html: str | None = None,
    js_api: object | None = None,
    width: int = 800,
    height: int = 600,
    x: int | None = None,
    y: int | None = None,
    resizable: bool = True,
    fullscreen: bool = False,
    min_size: tuple[int, int] = (200, 100),
    hidden: bool = False,
    on_top: bool = False,
    confirm_close: bool = False,
    background_color: str = "#FFFFFF",
    text_select: bool = False,
    zoomable: bool = False,
) -> Window: ...
def start(
    func: Callable[..., Any] | None = None,
    args: Any = None,
    gui: str | None = None,
    debug: bool = False,
    private_mode: bool = True,
    storage_path: str | None = None,
    menu: list[Menu] = ...,
) -> None: ...

windows: list[Window]
settings: MutableMapping[str, Any]
