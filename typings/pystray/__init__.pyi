# pyright（strict）用的最小 stub，只寫倉庫實際用到的部分（rpa_desktop，M10.1）。
# pystray 只在 Windows 安裝，Linux 的 CI 與開發環境沒有，
# 套件本身也沒有型別；介面以 pystray 0.19 的文件為準，
# 用到新的函式時在這裡補上。typings/ 是 pyright 的 stubPath 預設位置，優先於套件自己的型別。
from collections.abc import Callable
from typing import Any, ClassVar

from PIL.Image import Image

class MenuItem:
    def __init__(
        self,
        text: str | Callable[[MenuItem], str],
        action: Callable[..., Any] | Menu | None,
        checked: Callable[[MenuItem], bool] | None = None,
        radio: bool = False,
        default: bool = False,
        visible: bool | Callable[[MenuItem], bool] = True,
        enabled: bool | Callable[[MenuItem], bool] = True,
    ) -> None: ...

class Menu:
    SEPARATOR: ClassVar[MenuItem]
    def __init__(self, *items: MenuItem) -> None: ...

class Icon:
    icon: Image | None
    title: str
    menu: Menu | None
    visible: bool
    HAS_NOTIFICATION: ClassVar[bool]
    def __init__(
        self,
        name: str,
        icon: Image | None = None,
        title: str | None = None,
        menu: Menu | None = None,
    ) -> None: ...
    def run(self, setup: Callable[[Icon], None] | None = None) -> None: ...
    def stop(self) -> None: ...
    def notify(self, message: str, title: str | None = None) -> None: ...
    def update_menu(self) -> None: ...
