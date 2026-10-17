"""裝置邀請與配對（M10.1）：邀請的格式、伺服器網址、Client API 的配對請求、存下的配對結果。

管理 Portal 那一邊（代碼一次性、過期、App 種類、對外埠）在 apps/server 的測試。
"""

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from rpa_worker.pairing import (
    CLIENT_API_PREFIX,
    Invite,
    InviteError,
    PairResult,
    load_pairing,
    normalize_server,
    pair,
    parse_invite,
    save_pairing,
)
from rpa_worker.remote import WorkerApiError

CODE = "Ab_cd-0123456789xyzXYZ"


def test_invite_line_round_trips() -> None:
    invite = Invite("http://192.168.1.10:8081", CODE, "worker")
    line = invite.line()

    assert line == f"rpa://pair?server=http%3A%2F%2F192.168.1.10%3A8081&app=worker&code={CODE}"
    assert parse_invite(line) == invite
    assert parse_invite(f'  "{line}"\n') == invite  # 從命令列或聊天軟體複製時常帶引號與空白


def test_invite_server_wins_over_the_given_one() -> None:
    """邀請裡的位址是管理 Portal 看到的對外埠；另外給的只在只有代碼時使用。"""
    line = Invite("http://10.0.0.2:8081", CODE, "worker").line()
    assert parse_invite(line, "http://other:1").server == "http://10.0.0.2:8081"
    assert parse_invite(CODE, "10.0.0.3:8081") == Invite("http://10.0.0.3:8081", CODE)


@pytest.mark.parametrize(
    ("text", "server", "reason"),
    [
        ("", None, "empty"),
        ("   ", None, "empty"),
        ("hello world", None, "format"),
        ("short", "http://x:1", "format"),
        (CODE, None, "server"),
        (CODE, " ", "server"),
        (f"rpa://other?server=http://x:1&code={CODE}", None, "format"),
        ("rpa://pair?server=http://x:1&code=bad code", None, "format"),
        (f"rpa://pair?code={CODE}", None, "server"),
        (f"rpa://pair?server=http://x:1&app=desktop&code={CODE}", None, "app"),
        (f"rpa://pair?server=ftp://x:1&code={CODE}", None, "server"),
        (f"rpa://pair?server=http://x:1/path&code={CODE}", None, "server"),
    ],
)
def test_invite_problems_have_reasons(text: str, server: str | None, reason: str) -> None:
    with pytest.raises(InviteError) as caught:
        parse_invite(text, server)
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("192.168.1.10:8081", "http://192.168.1.10:8081"),
        ("http://pc.local:8081/", "http://pc.local:8081"),
        ("https://rpa.example:443", "https://rpa.example:443"),
        ("http://[fe80::1]:8081", "http://[fe80::1]:8081"),
    ],
)
def test_server_urls_are_normalized(given: str, expected: str) -> None:
    assert normalize_server(given) == expected


class _Portal(BaseHTTPRequestHandler):
    """假的對外埠：記下收到的請求，回傳 handler 類別上設定的回應。"""

    requests: ClassVar[list[tuple[str, dict[str, str], object]]] = []
    status: ClassVar[int] = 200
    reply: ClassVar[object] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload: object = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append((self.path, dict(self.headers.items()), payload))
        data = json.dumps(type(self).reply).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def portal() -> Iterator[str]:
    _Portal.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_pair_sends_the_code_without_a_token(portal: str) -> None:
    _Portal.status = 200
    _Portal.reply = {
        "device": "win-01",
        "name": "Windows",
        "app": "worker",
        "token": "secret",
        "server": {"protocol": 1, "fingerprint": "abc", "version": "0.1.0"},
    }

    result = pair(Invite(portal, CODE, "worker"), "worker", {"name": "WIN"})

    assert result == PairResult(
        server=portal,
        device="win-01",
        name="Windows",
        app="worker",
        token="secret",
        protocol=1,
        fingerprint="abc",
        version="0.1.0",
    )
    [(path, headers, payload)] = _Portal.requests
    assert path == f"{CLIENT_API_PREFIX}/pair"
    assert "Authorization" not in headers
    assert payload == {"code": CODE, "app": "worker", "info": {"name": "WIN"}}


def test_pair_refusal_keeps_the_server_message(portal: str) -> None:
    _Portal.status = 409
    _Portal.reply = {"error": {"code": "invite_wrong_app", "message": "這份邀請是給別的 App 的"}}

    with pytest.raises(WorkerApiError) as caught:
        pair(Invite(portal, CODE), "recorder")

    assert caught.value.status == 409
    assert caught.value.code == "invite_wrong_app"
    assert caught.value.message == "這份邀請是給別的 App 的"


def test_saved_pairing_is_private_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "work" / "pairing.json"
    result = PairResult("http://x:8081", "win-01", "W", "worker", "tok", 1, None, None)

    save_pairing(path, result)

    assert load_pairing(path) == ("http://x:8081", "tok")
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    path.write_text("[]", encoding="utf-8")
    assert load_pairing(path) is None
    assert load_pairing(tmp_path / "missing.json") is None
