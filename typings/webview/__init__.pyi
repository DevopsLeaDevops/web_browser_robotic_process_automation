# pyright（strict）用的最小 stub，只寫倉庫實際用到的部分（rpa_desktop，M10.1）。
# pywebview 只在 Windows 安裝，Linux 的 CI 與開發環境沒有；介面以 pywebview 5／6 的文件為準，
# 用到新的函式時在這裡補上。typings/ 是 pyright 的 stubPath 預設位置，優先於套件自己的型別。
from collections.abc import Callable
from typing import Any

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
) -> None: ...

windows: list[Window]
