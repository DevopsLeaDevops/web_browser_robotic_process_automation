"""模擬內部系統的本機測試網站，沿用 MVP 原型 python-demo/target 的頁面與 API。

- ``/``：建立範例紀錄（標題、數量）；``/?view=query``：依紀錄編號查詢
- ``POST /api/records``、``GET /api/records/<編號>``：資料只存在記憶體，程序結束就消失
- 登入（M4 的角色與登入狀態）：``/login`` 登入頁、``/account`` 我的帳號（沒登入時轉到登入頁）。
  兩個示範帳號 user（一般使用者）與 manager（主管）看到的待辦不同；``POST /api/login``、
  ``POST /api/logout``；``POST /api/sessions/expire`` 讓所有人的登入失效（測試 needs_login 用）
- iframe（M7a）：``/frames`` 的表單在 iframe 裡（``/frames/form``），表單裡還有一個 iframe
  （``/frames/note``，送出前要勾選「我已確認」）；只在瀏覽器裡運作，不寫入資料
- ``GET /api/about``：回傳 ``{"name": "rpa-testsite"}``，讓 ``rpa serve`` 認出已經在執行的測試網站
- 預設只綁定 127.0.0.1；``rpa serve --testsite-host 0.0.0.0`` 可以讓其他電腦（錄製端、Worker）
  連到同一個測試網站，資料與登入共用。不連線任何外部系統

``rpa serve`` 會在 8765 一起啟動；測試用 ``running()`` 在隨機埠號啟動；
單獨啟動：``uv run python -m testsite --port 8765``。``rpa worker`` 與打包的 RPA Worker
用 ``start_in_background()``：8765 上已經是測試網站就沿用。
"""

import errno
import html
import json
import os
import secrets
import threading
import urllib.request
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from typing import Final, Literal, cast
from urllib.parse import quote, unquote, urlsplit

__all__ = [
    "ACCOUNTS",
    "ADDRESS_IN_USE",
    "DEFAULT_PORT",
    "LOOPBACK",
    "MAX_QUANTITY",
    "NAME",
    "PAGE",
    "SESSION_COOKIE",
    "WILDCARD_HOSTS",
    "StartState",
    "create_server",
    "is_testsite",
    "running",
    "start_in_background",
]

DEFAULT_PORT: Final = 8765
"""範例場景的 browser.baseUrl 指向 http://127.0.0.1:8765。"""
LOOPBACK: Final = "127.0.0.1"
"""預設只讓這台電腦連。"""
WILDCARD_HOSTS: Final = frozenset({"0.0.0.0", ""})
"""綁定所有介面（其他電腦也連得到）。"""
NAME: Final = "rpa-testsite"
PAGE: Final = Path(__file__).with_name("index.html")
LOGIN_PAGE: Final = Path(__file__).with_name("login.html")
FRAME_PAGES: Final = {
    "/frames": Path(__file__).with_name("frames.html"),
    "/frames/form": Path(__file__).with_name("frames-form.html"),
    "/frames/note": Path(__file__).with_name("frames-note.html"),
}
"""iframe 範例頁（M7a）。"""
MAX_QUANTITY: Final = 30
SESSION_COOKIE: Final = "rpa_testsite_session"
_MAX_BODY: Final = 8192

ADDRESS_IN_USE: Final = frozenset(
    code
    for code in (
        errno.EADDRINUSE,
        getattr(errno, "WSAEADDRINUSE", None),
        # Windows 保留給其他服務的埠號（例如 Hyper-V）綁定時回報存取被拒
        getattr(errno, "WSAEACCES", None),
    )
    if code is not None
)
"""綁定埠號失敗、代表「已經有人在用」的錯誤碼。"""

type StartState = Literal["started", "running", "busy", "failed"]


@dataclass(frozen=True, slots=True)
class Account:
    """示範帳號；密碼是公開的示範值，只存在這個本機測試網站。"""

    password: str
    name: str
    role: str
    todos: tuple[str, ...]


ACCOUNTS: Final = {
    "user": Account("user-pass", "王小明", "一般使用者", ("填寫出差申請", "確認個人資料")),
    "manager": Account(
        "manager-pass",
        "林主管",
        "主管",
        ("核准出差申請", "核准採購單", "檢視部門報表", "確認個人資料"),
    ),
}
"""帳號 → 示範資料。主管的待辦比一般使用者多，用來確認兩個角色的登入狀態沒有混用。"""

ACCOUNT_PAGE: Final = Path(__file__).with_name("account.html")


class _Server(ThreadingHTTPServer):
    # Windows 的 SO_REUSEADDR 會搶走別人已經在用的埠號，只在其他系統開啟
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def create_server(port: int = 0, host: str = LOOPBACK) -> ThreadingHTTPServer:
    """建立測試網站；port 為 0 時由系統挑一個空的埠號（server.server_port）。

    host 預設只有本機；0.0.0.0 讓其他電腦也連得到（沒有任何保護，只在信任的網路使用）。
    """
    records: dict[str, dict[str, object]] = {}
    sessions: dict[str, str] = {}
    """登入憑證 → 帳號；只存在記憶體。"""
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """不輸出存取紀錄。"""

        def _reply(
            self,
            status: int,
            body: bytes,
            content_type: str,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _user(self) -> str | None:
            """目前登入的帳號（依 cookie）；沒登入或登入已失效時回傳 None。"""
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            morsel = cookie.get(SESSION_COOKIE)
            if morsel is None:
                return None
            with lock:
                return sessions.get(morsel.value)

        def _body(self) -> dict[str, object]:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= _MAX_BODY:
                raise ValueError("資料大小不符")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise TypeError("資料格式不符")
            return cast("dict[str, object]", data)

        def _account(self) -> None:
            username = self._user()
            if username is None:
                self._reply(
                    302, b"", "text/plain", {"Location": "/login?next=" + quote("/account")}
                )
                return
            account = ACCOUNTS[username]
            todos = "".join(f"<li>{html.escape(item)}</li>" for item in account.todos)
            page = Template(ACCOUNT_PAGE.read_text(encoding="utf-8")).substitute(
                name=html.escape(account.name),
                username=html.escape(username),
                role=html.escape(account.role),
                todos=todos,
                count=len(account.todos),
            )
            self._reply(200, page.encode(), "text/html; charset=utf-8")

        def _login(self) -> None:
            try:
                fields = self._body()
            except (ValueError, TypeError) as error:
                self._json(400, {"error": str(error)})
                return
            username, password = fields.get("username"), fields.get("password")
            account = ACCOUNTS.get(username) if isinstance(username, str) else None
            if account is None or password != account.password:
                self._json(401, {"error": "帳號或密碼不正確"})
                return
            token = secrets.token_urlsafe(24)
            with lock:
                sessions[token] = cast("str", username)
            cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax"
            body = json.dumps({"name": account.name, "role": account.role}, ensure_ascii=False)
            self._reply(
                200, body.encode(), "application/json; charset=utf-8", {"Set-Cookie": cookie}
            )

        def _json(self, status: int, data: dict[str, object]) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self._reply(status, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                self._reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/login":
                self._reply(200, LOGIN_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/account":
                self._account()
            elif path in FRAME_PAGES:
                self._reply(200, FRAME_PAGES[path].read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/about":
                self._json(200, {"name": NAME})
            elif path.startswith("/api/records/"):
                with lock:
                    record = records.get(unquote(path.removeprefix("/api/records/")))
                if record is None:
                    self._json(404, {"error": "查無紀錄"})
                else:
                    self._json(200, record)
            else:
                self._json(404, {"error": "找不到頁面"})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/login":
                self._login()
                return
            if path == "/api/logout":
                username = self._user()
                with lock:
                    for token in [key for key, value in sessions.items() if value == username]:
                        del sessions[token]
                self._json(200, {"loggedOut": username is not None})
                return
            if path == "/api/sessions/expire":
                with lock:
                    count = len(sessions)
                    sessions.clear()
                self._json(200, {"expired": count})
                return
            if path != "/api/records":
                self._json(404, {"error": "找不到介面"})
                return
            try:
                fields = self._body()
                title, quantity = fields.get("title"), fields.get("quantity")
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
                    raise ValueError("標題長度不符")
                if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
                    raise ValueError("數量需為 1–30 的整數")
            except (ValueError, TypeError) as error:
                self._json(400, {"error": str(error)})
                return
            record: dict[str, object] = {
                "recordId": "DEMO-" + uuid.uuid4().hex[:12].upper(),
                "title": title,
                "quantity": quantity,
                "status": "已建立",
            }
            with lock:
                records[str(record["recordId"])] = record
            self._json(201, record)

    return _Server((host, port), Handler)


@contextmanager
def running(port: int = 0) -> Generator[str, None, None]:
    """在背景執行緒啟動測試網站，產出網址（例如 ``http://127.0.0.1:54321``）；離開時關閉。"""
    server = create_server(port)
    thread = threading.Thread(target=server.serve_forever, name="testsite", daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def is_testsite(port: int, host: str = LOOPBACK) -> bool:
    """這個埠號上是不是已經在執行的測試網站（讀 /api/about）。綁定所有介面時從本機問。"""
    address = LOOPBACK if host in WILDCARD_HOSTS else host
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本機位址不走代理
    try:
        with opener.open(f"http://{address}:{port}/api/about", timeout=1) as response:
            data: object = json.load(response)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and cast("dict[str, object]", data).get("name") == NAME


def start_in_background(
    port: int = DEFAULT_PORT,
    host: str = LOOPBACK,
) -> tuple[ThreadingHTTPServer | None, StartState, str]:
    """在背景執行緒啟動測試網站，回傳 (伺服器，沒有啟動時為 None；狀態；失敗的原因)。

    狀態：``started`` 啟動了；``running`` 那個埠上已經是測試網站，沿用；
    ``busy`` 被別的程式占用；``failed`` 其他錯誤。
    """
    try:
        server = create_server(port, host)
    except OSError as error:
        if error.errno not in ADDRESS_IN_USE:
            return None, "failed", error.strerror or str(error)
        return None, ("running" if is_testsite(port, host) else "busy"), ""
    threading.Thread(target=server.serve_forever, name="testsite", daemon=True).start()
    return server, "started", ""
