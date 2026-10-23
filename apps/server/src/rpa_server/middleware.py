"""ASGI 中介層：每個請求的語言，以及擋掉跨站的寫入請求。

用純 ASGI 寫，不用 BaseHTTPMiddleware：語言存在 ContextVar，要在同一個 task 裡設定，
路由（包含在執行緒池跑的同步路由）與錯誤處理才讀得到。
"""

from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie
from typing import Final, cast
from urllib.parse import parse_qs, urlsplit

import anyio
from starlette.types import ASGIApp, Receive, Scope, Send

from rpa_core.i18n import Locale, parse_locale, use_locale
from rpa_server.context import Via, use_recorder
from rpa_server.errors import ServiceError

__all__ = [
    "AGENT_API",
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
AGENT_API: Final = "/agent-api/"
EXTERNAL_PATHS: Final = (WORKER_API, CLIENT_API, AGENT_API)
"""只在對外埠提供的路徑：Worker API（M9a）、桌面 App 的 Client API（M10）、Agent API（M14）。"""


async def _reply(send: Send, status: int, code: str, message: str) -> None:
    body = f'{{"error": {{"code": "{code}", "message": "{message}"}}}}'.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _bearer(scope: Scope) -> str | None:
    value = _header(scope, b"authorization")
    if value is not None and value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return None


class PortGateMiddleware:
    """對外埠與管理頁面分開在兩個埠（M9a，ADR 0012；M10 ADR 0014 改稱「對外埠」）。

    - 從對外埠（``worker_port``）進來的 ``/worker-api/``、``/client-api/`` 與 ``/agent-api/``
      照常交給路由，權杖或 API 金鑰由路由自己檢查。
    - 對外埠上的其他路徑（Portal 頁面、``/api``、靜態檔）只接受錄製端的裝置權杖（M10.2，
      ``authenticate`` 驗證）：錄製端的本機閘道替每個請求加上 ``Authorization``。沒有或不對時 401；
      worker 的權杖也不行。驗過的請求記在 :mod:`rpa_server.context`（頁面與服務知道透過哪台）。
      沒給 ``authenticate`` 時一律 404（M10.1 的行為）。
    - 從其他埠進來的請求不能用這幾組路徑（沒有開對外埠時也一樣）。
    """

    def __init__(
        self,
        app: ASGIApp,
        worker_port: int | None,
        authenticate: Callable[[str | None], Via] | None = None,
    ) -> None:
        self.app = app
        self.worker_port = worker_port
        self.authenticate = authenticate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        server = cast("tuple[str, int | None] | None", scope.get("server"))
        port = server[1] if server is not None else None
        on_worker_port = self.worker_port is not None and port == self.worker_port
        is_external_path = str(scope.get("path", "")).startswith(EXTERNAL_PATHS)
        if on_worker_port and not is_external_path and self.authenticate is not None:
            try:
                via = await anyio.to_thread.run_sync(self.authenticate, _bearer(scope))
            except ServiceError as error:
                await _reply(send, error.status, error.code, "Unauthorized")
                return
            with use_recorder(via):
                await self.app(scope, receive, send)
            return
        if on_worker_port != is_external_path:
            await _reply(send, 404, "not_found", "Not Found")
            return
        await self.app(scope, receive, send)
