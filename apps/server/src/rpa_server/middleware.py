"""ASGI 中介層：每個請求的語言，以及擋掉跨站的寫入請求。

用純 ASGI 寫，不用 BaseHTTPMiddleware：語言存在 ContextVar，要在同一個 task 裡設定，
路由（包含在執行緒池跑的同步路由）與錯誤處理才讀得到。
"""

from http.cookies import CookieError, SimpleCookie
from typing import Final, cast
from urllib.parse import parse_qs, urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from rpa_core.i18n import Locale, parse_locale, use_locale

__all__ = [
    "CLIENT_API",
    "EXTERNAL_PATHS",
    "LANG_COOKIE",
    "WORKER_API",
    "LocaleMiddleware",
    "PortGateMiddleware",
    "SameOriginMiddleware",
]

LANG_COOKIE: Final = "rpa_lang"
_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})


def _header(scope: Scope, name: bytes) -> str | None:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def request_locale(scope: Scope, default: Locale) -> Locale:
    """語言：網址的 ?lang= 優先，其次是 Cookie，最後是伺服器預設（不跟隨瀏覽器語言，ADR 0007）。"""
    query: bytes = scope.get("query_string", b"")
    for value in parse_qs(query.decode("latin-1")).get("lang", []):
        if (locale := parse_locale(value)) is not None:
            return locale
    cookie = _header(scope, b"cookie")
    if cookie:
        jar = SimpleCookie()
        try:
            jar.load(cookie)
        except CookieError:
            return default
        morsel = jar.get(LANG_COOKIE)
        if morsel is not None and (locale := parse_locale(morsel.value)) is not None:
            return locale
    return default


class LocaleMiddleware:
    def __init__(self, app: ASGIApp, default: Locale) -> None:
        self.app = app
        self.default: Locale = default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with use_locale(request_locale(scope, self.default)):
            await self.app(scope, receive, send)


class SameOriginMiddleware:
    """寫入請求（POST、PATCH…）帶了 Origin 標頭時，必須和網址同源。

    管理介面沒有登入（M8 才有），這可以避免使用者瀏覽的其他網站在背景呼叫本機的 API。
    命令列工具（curl 等）不送 Origin，不受影響。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method", "GET") not in _SAFE_METHODS:
            origin = _header(scope, b"origin")
            host = _header(scope, b"host")
            if origin is not None and (host is None or urlsplit(origin).netloc != host):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    }
                )
                await send({"type": "http.response.body", "body": b"cross-origin request blocked"})
                return
        await self.app(scope, receive, send)


WORKER_API: Final = "/worker-api/"
CLIENT_API: Final = "/client-api/"
EXTERNAL_PATHS: Final = (WORKER_API, CLIENT_API)
"""只在對外埠提供的路徑：Worker API（M9a）與桌面 App 的 Client API（M10）。"""


class PortGateMiddleware:
    """對外埠與管理頁面分開在兩個埠（M9a，ADR 0012；M10 ADR 0014 改稱「對外埠」）。

    - 從對外埠（``worker_port``）進來的請求只能用 ``/worker-api/`` 與 ``/client-api/``，
      其他一律 404：對外埠可以開放給區網，但管理頁面沒有登入（M8），不能跟著開放。
    - 從其他埠進來的請求不能用這兩組路徑（沒有開對外埠時也一樣）。
    """

    def __init__(self, app: ASGIApp, worker_port: int | None) -> None:
        self.app = app
        self.worker_port = worker_port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        server = cast("tuple[str, int | None] | None", scope.get("server"))
        port = server[1] if server is not None else None
        on_worker_port = self.worker_port is not None and port == self.worker_port
        is_external_path = str(scope.get("path", "")).startswith(EXTERNAL_PATHS)
        if on_worker_port != is_external_path:
            body = b'{"error": {"code": "not_found", "message": "Not Found"}}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
