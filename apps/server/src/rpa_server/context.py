"""這個請求是不是透過錄製端進來的（M10.2，ADR 0014）。

對外埠上的 Portal 頁面與 API 只接受錄製端的裝置權杖
（:class:`rpa_server.middleware.PortGateMiddleware`）；驗過權杖後把錄製端記在 ContextVar，
同一個請求裡的頁面、API 與服務都看得到（同步路由在執行緒池執行時也會帶著）。

- 錄製、逐步調試、人工登入的子程序交給這台錄製端執行（瀏覽器開在操作的人面前）。
- 頁面上的「本機」改稱「伺服器」，頁首顯示透過哪台錄製端操作。

背景執行緒（佇列、租約、子程序的輸出）不在任何請求裡，看到的永遠是 None。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

__all__ = ["Via", "use_recorder", "via_recorder"]


@dataclass(frozen=True, slots=True)
class Via:
    """透過哪台錄製端：代號與名稱。"""

    id: str
    name: str


_CURRENT: ContextVar[Via | None] = ContextVar("rpa_recorder", default=None)


def via_recorder() -> Via | None:
    """目前的請求透過哪台錄製端；從伺服器本機（8080）進來或不在請求裡時是 None。"""
    return _CURRENT.get()


@contextmanager
def use_recorder(via: Via | None) -> Iterator[None]:
    token = _CURRENT.set(via)
    try:
        yield
    finally:
        _CURRENT.reset(token)
