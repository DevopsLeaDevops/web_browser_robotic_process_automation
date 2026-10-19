"""錄製端的本機閘道（M10.2，ADR 0014）：瀏覽器（或 App 的視窗）只連這裡，閘道加上權杖
轉給管理 Portal。

- 只聽 127.0.0.1 的隨機埠。權杖只在閘道裡：網頁拿不到，也不靠管理 Portal 的 Cookie。
- **只給這個 App 用**：每次啟動產生一個密語，第一次打開 :meth:`Gateway.login_url` 時設成
  Cookie（HttpOnly、SameSite=Strict）；沒有這個 Cookie 的請求一律 403，同一台電腦上的其他程式
  與網頁用不了。也檢查 Host（擋 DNS rebinding）。
- 轉送時：加上 ``Authorization: Bearer <錄製端權杖>``，拿掉閘道自己的 Cookie；``Origin`` 是閘道
  自己時換成管理 Portal 的（管理 Portal 擋跨站的寫入請求），是別的網站就拒絕。回應的
  ``Location`` 指到管理 Portal 時換回閘道。
- **App 自己的頁面**（配對、下載瀏覽器、設定）在**另一個埠**的 ``/__desktop/``，由 ``local``
  處理（:meth:`Gateway.desktop_url`）：和管理 Portal 的頁面不同來源，Portal 的頁面（或塞進去的
  腳本）讀不到 App 的狀態，也叫不動 App 的動作——寫入的請求一定要帶 App 自己的 ``Origin``。
  兩邊各有自己的密語與 Cookie。
- 連不上管理 Portal 時回 502 與 ``offline_page``；管理 Portal 回 401（權杖失效）時呼叫
  ``on_unauthorized``，打開頁面的請求改回 ``notice_page("unauthorized")``（API 的請求照樣回 401）。
- 還沒配對（``server`` 是 None）時 Portal 那邊只回 ``notice_page("unpaired")``。說明頁不放
  App 頁面的網址：那個網址帶著密語，Portal 那邊的腳本讀得到的地方都不能有。
- 不轉送 ``/client-api/`` 與 ``/worker-api/``：那是錄製端程式自己用的通道，網頁不該拿閘道的
  權杖去確認或偽造指令與輸出。
- 轉送的 ``Host`` 和換過的 ``Origin`` 用同一個寫法（管理 Portal 比對兩者）：伺服器網址有大寫或
  寫了預設埠號時才不會被當成跨站。
- 以後改 HTTPS 時在這裡釘選憑證即可，WebView 不必處理自簽憑證。

只用標準函式庫（``http.server``、``http.client``）。
"""

import contextlib
import hmac
import http.client
import logging
import secrets
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final, Literal
from urllib.parse import SplitResult, parse_qs, quote, urlsplit

__all__ = ["COOKIE", "DESKTOP_COOKIE", "DESKTOP_PREFIX", "Gateway", "LocalResponse", "Side"]

logger = logging.getLogger("rpa_worker.gateway")

COOKIE: Final = "rpa_gateway"
DESKTOP_COOKIE: Final = "rpa_desktop"
"""App 自己的頁面那個埠的 Cookie（同一台主機的 Cookie 不分埠，名稱要不同）。"""
DESKTOP_PREFIX: Final = "/__desktop/"
LOGIN_PATH: Final = "/__gateway/login"
BLOCKED_PREFIXES: Final = ("/client-api/", "/worker-api/")
MAX_BODY_BYTES: Final = 100 * 1024 * 1024
UPSTREAM_TIMEOUT: Final = 600.0
"""逐步調試的一步、上傳匯入檔都可能很久。"""
_HOP: Final = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


@dataclass(frozen=True, slots=True)
class LocalResponse:
    """App 自己的頁面的回應。"""

    status: int = 200
    body: bytes = b""
    content_type: str = "text/html; charset=utf-8"
    headers: Mapping[str, str] = field(default_factory=dict[str, str])


LocalHandler = Callable[[str, str, Mapping[str, list[str]], bytes], LocalResponse]
"""(方法, ``/__desktop/`` 之後的路徑, 查詢參數, 內容) → 回應。"""
Side = Literal["portal", "desktop"]
"""轉送到管理 Portal 的埠，或 App 自己的頁面的埠。"""


def _default_offline(reason: str) -> str:
    return f"<!doctype html><meta charset=utf-8><title>RPA</title><p>{_escape(reason)}</p>"


def _opens_page(request: BaseHTTPRequestHandler) -> bool:
    """是不是打開一個頁面（不是頁面裡的腳本呼叫 API）。"""
    if request.command != "GET":
        return False
    mode = request.headers.get("Sec-Fetch-Mode")
    if mode is not None:
        return mode == "navigate"
    return "text/html" in (request.headers.get("Accept") or "")


def _same(given: str, expected: str) -> bool:
    """比對密語（固定時間；非 ASCII 的輸入不會讓 compare_digest 拋出例外）。"""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Gateway:
    """一個本機閘道：``start()`` 後在背景執行，``close()`` 結束。"""

    def __init__(
        self,
        server: str | None,
        token: Callable[[], str | None],
        *,
        port: int = 0,
        local: LocalHandler | None = None,
        on_unauthorized: Callable[[], object] | None = None,
        offline_page: Callable[[str], str] = _default_offline,
        notice_page: Callable[[str], str] | None = None,
    ) -> None:
        self.token = token
        self.local = local
        self.on_unauthorized = on_unauthorized
        self.offline_page = offline_page
        self.notice_page = notice_page
        self.secret = secrets.token_urlsafe(24)
        self.desktop_secret = secrets.token_urlsafe(24)
        self.server: str | None = None
        self._upstream: SplitResult | None = None
        self.set_server(server)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler("portal"))
        self._httpd.daemon_threads = True
        self._desktop: ThreadingHTTPServer | None = None
        if local is not None:
            self._desktop = ThreadingHTTPServer(("127.0.0.1", 0), self._handler("desktop"))
            self._desktop.daemon_threads = True
        self._threads: list[threading.Thread] = []

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def desktop_port(self) -> int | None:
        return int(self._desktop.server_address[1]) if self._desktop is not None else None

    @property
    def desktop_origin(self) -> str | None:
        port = self.desktop_port
        return f"http://127.0.0.1:{port}" if port is not None else None

    def login_url(self, next_path: str = "/") -> str:
        """打開管理 Portal 的網址：設好 Cookie 後轉到 ``next_path``。"""
        return f"{self.origin}{LOGIN_PATH}?key={quote(self.secret)}&next={quote(next_path)}"

    def desktop_url(self, path: str = "") -> str:
        """打開 App 自己的頁面的網址（另一個埠、另一個密語）。"""
        if self.desktop_origin is None:
            raise ValueError("this gateway has no desktop pages")
        target = quote(DESKTOP_PREFIX + path)
        return f"{self.desktop_origin}{LOGIN_PATH}?key={quote(self.desktop_secret)}&next={target}"

    def set_server(self, server: str | None) -> None:
        """換掉轉送的目標（配對好、重新配對到別的管理 Portal）；None 是還沒配對。"""
        if server is None:
            self.server, self._upstream = None, None
            return
        parts = urlsplit(server.rstrip("/"))
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"not a server URL: {server!r}")
        self.server, self._upstream = server.rstrip("/"), parts

    def _servers(self) -> list[ThreadingHTTPServer]:
        return [self._httpd] + ([self._desktop] if self._desktop is not None else [])

    def start(self) -> None:
        if self._threads:
            return
        for server in self._servers():
            thread = threading.Thread(target=server.serve_forever, name="rpa-gateway", daemon=True)
            thread.start()
            self._threads.append(thread)

    def close(self) -> None:
        for server in self._servers():
            if self._threads:
                server.shutdown()
            server.server_close()

    # ------------------------------------------------------------ 處理請求

    def _handler(self, side: Side) -> type[BaseHTTPRequestHandler]:
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "RPAGateway"

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("%s " + format, self.address_string(), *args)

            def do_GET(self) -> None:
                gateway.handle(self, side)

            do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_GET  # noqa: N815

        return Handler

    def _secret(self, side: Side) -> tuple[str, str]:
        """(Cookie 的名稱, 密語)。"""
        if side == "desktop":
            return DESKTOP_COOKIE, self.desktop_secret
        return COOKIE, self.secret

    def _authorized(self, request: BaseHTTPRequestHandler, side: Side) -> bool:
        raw = request.headers.get("Cookie")
        if not raw:
            return False
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            return False
        name, secret = self._secret(side)
        morsel = jar.get(name)
        return morsel is not None and _same(morsel.value, secret)

    def _hosts(self, side: Side) -> tuple[str, str]:
        port = self.desktop_port if side == "desktop" else self.port
        return f"127.0.0.1:{port}", f"localhost:{port}"

    def _host_ok(self, request: BaseHTTPRequestHandler, side: Side) -> bool:
        return (request.headers.get("Host") or "").lower() in self._hosts(side)

    def _origin_ok(self, origin: str | None, side: Side) -> bool:
        return origin is None or origin in tuple(f"http://{host}" for host in self._hosts(side))

    @staticmethod
    def _reply(
        request: BaseHTTPRequestHandler,
        status: int,
        body: bytes,
        content_type: str = "text/plain; charset=utf-8",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        request.send_response(status)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            request.send_header(key, value)
        request.send_header("Connection", "close")
        request.end_headers()
        if request.command != "HEAD":
            request.wfile.write(body)
        request.close_connection = True

    def _read_body(self, request: BaseHTTPRequestHandler) -> bytes | None:
        """請求的內容；太大時回傳 None。"""
        length = request.headers.get("Content-Length")
        if length is not None:
            size = int(length) if length.isdigit() else -1
            if size < 0 or size > MAX_BODY_BYTES:
                return None
            return request.rfile.read(size)
        if "chunked" in (request.headers.get("Transfer-Encoding") or "").lower():
            chunks: list[bytes] = []
            total = 0
            while True:
                line = request.rfile.readline(65537).strip()
                size = int(line.split(b";", 1)[0] or b"0", 16)
                if size == 0:
                    request.rfile.readline()
                    break
                total += size
                if total > MAX_BODY_BYTES:
                    return None
                chunks.append(request.rfile.read(size))
                request.rfile.readline()
            return b"".join(chunks)
        return b""

    def handle(self, request: BaseHTTPRequestHandler, side: Side = "portal") -> None:
        try:
            self._handle(request, side)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logger.exception("閘道處理 %s %s 失敗", request.command, request.path)
            with contextlib.suppress(OSError):
                self._reply(request, 500, b"gateway error")

    def _handle(self, request: BaseHTTPRequestHandler, side: Side) -> None:
        if not self._host_ok(request, side):
            self._reply(request, 403, b"forbidden host")
            return
        parts = urlsplit(request.path)
        if parts.path == LOGIN_PATH:
            self._login(request, side, parse_qs(parts.query))
            return
        if not self._authorized(request, side):
            self._reply(request, 403, b"forbidden: open this page from the RPA app")
            return
        origin = request.headers.get("Origin")
        if not self._origin_ok(origin, side):
            self._reply(request, 403, b"cross-origin request blocked")
            return
        if side == "desktop":
            self._desktop_page(request, parts.path, parts.query, origin)
            return
        if parts.path.startswith((*BLOCKED_PREFIXES, DESKTOP_PREFIX)):
            self._reply(request, 403, b"not available through the gateway")
            return
        body = self._read_body(request)
        if body is None:
            self._reply(request, 413, b"request too large")
            return
        upstream = self._upstream
        if upstream is None:  # 還沒配對
            self._notice(request, "unpaired", 409)
            return
        self._forward(request, upstream, body, origin is not None)

    def _login(
        self, request: BaseHTTPRequestHandler, side: Side, query: Mapping[str, list[str]]
    ) -> None:
        key = (query.get("key") or [""])[0]
        target = (query.get("next") or ["/"])[0]
        if not target.startswith("/") or target.startswith(("//", "/\\")):
            target = "/"
        name, secret = self._secret(side)
        if not _same(key, secret):
            self._reply(request, 403, b"forbidden")
            return
        cookie = f"{name}={secret}; Path=/; HttpOnly; SameSite=Strict"
        self._reply(request, 303, b"", headers={"Location": target, "Set-Cookie": cookie})

    def _desktop_page(
        self, request: BaseHTTPRequestHandler, path: str, query: str, origin: str | None
    ) -> None:
        """App 自己的頁面：寫入的請求一定要帶這個埠的 Origin（其他頁面送不出來）。"""
        if request.command not in ("GET", "HEAD") and origin is None:
            self._reply(request, 403, b"cross-origin request blocked")
            return
        if not path.startswith(DESKTOP_PREFIX) or self.local is None:
            if request.command in ("GET", "HEAD"):
                self._reply(request, 303, b"", headers={"Location": DESKTOP_PREFIX})
            else:
                self._reply(request, 404, b"not found")
            return
        body = self._read_body(request)
        if body is None:
            self._reply(request, 413, b"request too large")
            return
        result = self.local(
            request.command, path.removeprefix(DESKTOP_PREFIX), parse_qs(query), body
        )
        self._reply(request, result.status, result.body, result.content_type, result.headers)

    def _notice(self, request: BaseHTTPRequestHandler, kind: str, status: int) -> None:
        if self.notice_page is not None and _opens_page(request):
            page = self.notice_page(kind).encode("utf-8")
            self._reply(request, status, page, "text/html; charset=utf-8")
        else:
            self._reply(request, status, kind.encode("ascii"))

    def _forward(
        self, request: BaseHTTPRequestHandler, upstream: SplitResult, body: bytes, has_origin: bool
    ) -> None:
        server_origin = f"{upstream.scheme}://{upstream.netloc}"
        headers: dict[str, str] = {"Host": upstream.netloc}  # 和 Origin 一致
        for key, value in request.headers.items():
            lower = key.lower()
            if lower in _HOP or lower in ("authorization", "cookie", "origin"):
                continue
            headers[key] = value
        cookies = self._forward_cookies(request.headers.get_all("Cookie") or [])
        if cookies:
            headers["Cookie"] = cookies
        if has_origin:
            headers["Origin"] = server_origin
        token = self.token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body or request.command in ("POST", "PUT", "PATCH"):
            headers["Content-Length"] = str(len(body))
        connection_type = (
            http.client.HTTPSConnection
            if upstream.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(
            upstream.hostname or "", upstream.port, timeout=UPSTREAM_TIMEOUT
        )
        try:
            try:
                connection.request(
                    request.command, request.path, body=body or None, headers=headers
                )
                response = connection.getresponse()
            except (OSError, http.client.HTTPException) as error:
                page = self.offline_page(str(error)).encode("utf-8")
                self._reply(request, 502, page, "text/html; charset=utf-8")
                return
            if response.status == HTTPStatus.UNAUTHORIZED:
                if self.on_unauthorized is not None:
                    self.on_unauthorized()
                if self.notice_page is not None and _opens_page(request):
                    # 權杖失效：打開頁面時說明怎麼重新配對，不顯示錯誤的 JSON
                    self._notice(request, "unauthorized", 401)
                    return
            request.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lower = key.lower()
                if lower in _HOP and lower != "content-length":
                    continue
                if lower == "location" and (
                    value == server_origin or value.startswith(server_origin + "/")
                ):
                    value = self.origin + value[len(server_origin) :]
                request.send_header(key, value)
            request.send_header("Connection", "close")
            request.end_headers()
            request.close_connection = True
            if request.command == "HEAD":
                return
            while chunk := response.read(64 * 1024):
                request.wfile.write(chunk)
        finally:
            connection.close()

    @staticmethod
    def _forward_cookies(values: list[str]) -> str:
        """拿掉閘道自己的 Cookie，其他的（例如介面語言）照樣轉送。"""
        kept: list[str] = []
        for raw in values:
            for part in raw.split(";"):
                name = part.split("=", 1)[0].strip()
                if name and name not in (COOKIE, DESKTOP_COOKIE):
                    kept.append(part.strip())
        return "; ".join(kept)
