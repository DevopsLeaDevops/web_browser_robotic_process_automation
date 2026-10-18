"""錄製端的本機閘道（rpa_worker.gateway，M10.2）：對一個假的管理 Portal 測試。"""

import http.client
import json
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import quote

import pytest

from rpa_worker.gateway import COOKIE, Gateway, LocalResponse

TOKEN = "device-token"


@dataclass
class Upstream:
    """假的管理 Portal：記下收到的請求。"""

    requests: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    status: int = 200
    location: str | None = None

    def serve(self) -> ThreadingHTTPServer:
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return None

            def handle_any(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                upstream.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": body,
                    }
                )
                data = json.dumps({"ok": True, "path": self.path}).encode()
                self.send_response(upstream.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                if upstream.location:
                    self.send_header("Location", upstream.location)
                self.send_header("Set-Cookie", "rpa_lang=en; Path=/")
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = handle_any  # noqa: N815

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


@pytest.fixture
def upstream() -> Iterator[tuple[Upstream, str]]:
    fake = Upstream()
    server = fake.serve()
    try:
        yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def gateway(upstream: tuple[Upstream, str]) -> Iterator[Gateway]:
    calls: list[str] = []

    def local(method: str, path: str, query: Mapping[str, list[str]], body: bytes) -> LocalResponse:
        calls.append(path)
        return LocalResponse(body=f"local {method} {path}".encode(), content_type="text/plain")

    unauthorized: list[bool] = []
    item = Gateway(
        upstream[1],
        lambda: TOKEN,
        local=local,
        on_unauthorized=lambda: unauthorized.append(True),
    )
    item.start()
    item.unauthorized = unauthorized  # type: ignore[attr-defined]
    try:
        yield item
    finally:
        item.close()


def request(
    gateway: Gateway,
    method: str,
    path: str,
    *,
    cookie: bool = True,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", gateway.port, timeout=10)
    values = dict(headers or {})
    if cookie:
        values["Cookie"] = f"{COOKIE}={gateway.secret}; rpa_lang=zh-Hant"
    connection.request(method, path, body=body, headers=values)
    response = connection.getresponse()
    data = response.read()
    result = response.status, {key.lower(): value for key, value in response.getheaders()}, data
    connection.close()
    return result


def test_login_sets_the_cookie(gateway: Gateway) -> None:
    path = gateway.login_url("/devices").removeprefix(gateway.origin)
    status, headers, _ = request(gateway, "GET", path, cookie=False)
    assert status == 303
    assert headers["location"] == "/devices"
    assert f"{COOKIE}={gateway.secret}" in headers["set-cookie"]
    assert "HttpOnly" in headers["set-cookie"]
    status, _, _ = request(gateway, "GET", "/__gateway/login?key=wrong", cookie=False)
    assert status == 403


def test_requests_without_the_cookie_are_refused(
    gateway: Gateway, upstream: tuple[Upstream, str]
) -> None:
    status, _, _ = request(gateway, "GET", "/scenes", cookie=False)
    assert status == 403
    status, _, _ = request(gateway, "GET", "/scenes", headers={"Host": "evil.example:80"})
    assert status == 403  # DNS rebinding
    assert upstream[0].requests == []


def test_forwards_with_the_token(gateway: Gateway, upstream: tuple[Upstream, str]) -> None:
    status, headers, data = request(
        gateway,
        "POST",
        "/api/scenes?x=1",
        headers={"Origin": gateway.origin, "Content-Type": "application/json"},
        body=b'{"a": 1}',
    )
    assert status == 200
    assert json.loads(data)["path"] == "/api/scenes?x=1"
    assert headers["set-cookie"].startswith("rpa_lang=en")
    sent = upstream[0].requests[-1]
    raw = cast("dict[str, str]", sent["headers"])
    sent_headers = {key.lower(): value for key, value in raw.items()}
    assert sent_headers["authorization"] == f"Bearer {TOKEN}"
    assert sent_headers["origin"] == upstream[1]  # 換成管理 Portal 的來源
    assert sent_headers["cookie"] == "rpa_lang=zh-Hant"  # 閘道自己的 Cookie 不轉送
    assert sent["body"] == b'{"a": 1}'


def test_foreign_origin_is_refused(gateway: Gateway, upstream: tuple[Upstream, str]) -> None:
    status, _, _ = request(
        gateway, "POST", "/api/scenes", headers={"Origin": "http://evil.example"}, body=b"{}"
    )
    assert status == 403
    assert upstream[0].requests == []


def test_location_is_rewritten(gateway: Gateway, upstream: tuple[Upstream, str]) -> None:
    upstream[0].status = 303
    upstream[0].location = upstream[1] + "/devices"
    status, headers, _ = request(gateway, "GET", "/workers")
    assert status == 303
    assert headers["location"] == gateway.origin + "/devices"


def test_unauthorized_is_reported(gateway: Gateway, upstream: tuple[Upstream, str]) -> None:
    upstream[0].status = 401
    status, _, _ = request(gateway, "GET", "/scenes")
    assert status == 401
    assert gateway.unauthorized == [True]  # type: ignore[attr-defined]


def test_local_pages(gateway: Gateway, upstream: tuple[Upstream, str]) -> None:
    status, _, data = request(gateway, "GET", "/__desktop/pair?x=1")
    assert status == 200
    assert data == b"local GET pair"
    assert upstream[0].requests == []


def test_offline_page() -> None:
    gateway = Gateway("http://127.0.0.1:9", lambda: TOKEN, offline_page=lambda reason: "OFFLINE")
    gateway.start()
    try:
        status, _, data = request(gateway, "GET", "/scenes")
    finally:
        gateway.close()
    assert status == 502
    assert data == b"OFFLINE"


def test_rejects_bad_server() -> None:
    with pytest.raises(ValueError, match="server URL"):
        Gateway("ftp://x", lambda: TOKEN)


def test_channels_of_the_app_are_not_forwarded(
    gateway: Gateway, upstream: tuple[Upstream, str]
) -> None:
    """網頁不能拿閘道的權杖確認、偽造錄製端的指令與輸出。"""
    for path in ("/client-api/v1/control", "/worker-api/v1/hello"):
        status, _, _ = request(gateway, "POST", path, body=b"{}")
        assert status == 403
    assert upstream[0].requests == []


def test_host_matches_the_rewritten_origin(upstream: tuple[Upstream, str]) -> None:
    """伺服器網址有大寫時，Host 與 Origin 寫法一致（管理 Portal 比對兩者）。"""
    port = upstream[1].rsplit(":", 1)[1]
    server = f"http://LocalHost:{port}"
    item = Gateway(server, lambda: TOKEN)
    item.start()
    try:
        status, _, _ = request(item, "POST", "/api/x", headers={"Origin": item.origin}, body=b"{}")
    finally:
        item.close()
    assert status == 200
    raw = cast("dict[str, str]", upstream[0].requests[-1]["headers"])
    sent = {key.lower(): value for key, value in raw.items()}
    assert sent["origin"] == server
    assert sent["host"] == f"LocalHost:{port}"


def test_login_rejects_odd_targets_and_keys(gateway: Gateway) -> None:
    key = quote(gateway.secret)
    status, headers, _ = request(
        gateway, "GET", f"/__gateway/login?key={key}&next=/%5Cevil.example", cookie=False
    )
    assert status == 303
    assert headers["location"] == "/"
    status, _, _ = request(gateway, "GET", "/__gateway/login?key=%E5%AF%86", cookie=False)
    assert status == 403  # 非 ASCII 的密語：拒絕，不是 500
