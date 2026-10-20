"""`rpa serve` 的埠號：被占用時自動換一個、已經在執行的 Portal 不再開第二個、看得懂的錯誤；
以及啟動時提醒還沒下載的瀏覽器。

只測綁定埠號的部分，不真的啟動伺服器（那部分在 apps/server 的端到端測試）。
"""

import json
import socket
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import click
import pytest
import uvicorn
from click.testing import CliRunner

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_cli.serve import (
    PORTAL_TITLE,
    browser_warning,
    open_listener,
    portal_url,
    start_testsite,
)
from rpa_core.i18n import use_locale

HOST = "127.0.0.1"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


@contextmanager
def occupied() -> Generator[int, None, None]:
    """另一個程式占用的埠號（正在監聽，但不是 Portal）。"""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind((HOST, 0))
    holder.listen()
    try:
        yield holder.getsockname()[1]
    finally:
        holder.close()


@contextmanager
def fake_portal() -> Generator[int, None, None]:
    """一個看起來像管理 Portal 的伺服器（/api/openapi.json 的標題相同）。"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """不輸出存取紀錄。"""

        def do_GET(self) -> None:
            body = json.dumps({"info": {"title": PORTAL_TITLE}}).encode()
            self.send_response(200 if self.path == "/api/openapi.json" else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((HOST, 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()


def test_free_port_is_used_as_given() -> None:
    with occupied() as port:
        pass  # 取得一個剛釋放的埠號
    sock, chosen, skipped = open_listener(HOST, port)
    sock.close()
    assert (chosen, skipped) == (port, None)


def test_default_port_falls_back_to_the_next_free_one() -> None:
    with occupied() as busy:
        sock, chosen, skipped = open_listener(HOST, None, first=busy, count=5)
        sock.close()
    assert skipped == busy
    assert busy < chosen < busy + 5


def test_explicit_busy_port_explains_what_to_do() -> None:
    with occupied() as busy, pytest.raises(click.ClickException) as raised:
        open_listener(HOST, busy)
    message = raised.value.message
    assert f"埠號 {busy} 已被其他程式使用" in message
    assert f"--port {busy + 10}" in message
    assert f"lsof -nP -iTCP:{busy} -sTCP:LISTEN" in message


def test_running_portal_is_not_started_twice() -> None:
    with fake_portal() as port:
        for requested, first in ((port, 8080), (None, port)):
            with pytest.raises(click.ClickException) as raised:
                open_listener(HOST, requested, first=first, count=3)
            assert raised.value.message.startswith(
                f"管理 Portal 已經在 http://127.0.0.1:{port}/ 執行中"
            )


def test_address_that_is_not_local_is_reported() -> None:
    # 203.0.113.0/24 是文件專用位址，不會是本機的網路介面
    with pytest.raises(click.ClickException) as raised:
        open_listener("203.0.113.7", 8080)
    assert raised.value.message.startswith("無法監聽 203.0.113.7:8080：")


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("127.0.0.1", "http://127.0.0.1:8080/"),
        ("0.0.0.0", "http://127.0.0.1:8080/"),
        ("::", "http://[::1]:8080/"),
        ("localhost", "http://localhost:8080/"),
    ],
)
def test_portal_url(host: str, url: str) -> None:
    assert portal_url(host, 8080) == url


def test_cli_reports_busy_port_without_a_traceback() -> None:
    with occupied() as busy:
        install_click_translations()
        result = CliRunner().invoke(build_cli(), ["serve", "--port", str(busy)])

    assert result.exit_code == 1
    assert f"埠號 {busy} 已被其他程式使用" in result.output
    assert "Traceback" not in result.output


def test_testsite_starts_once_and_is_reused() -> None:
    with occupied() as port:
        pass  # 取得一個剛釋放的埠號
    site, message = start_testsite(port)
    assert site is not None
    try:
        assert message == f"測試網站：http://127.0.0.1:{port}/"
        again, second = start_testsite(port)
        assert again is None
        assert second == f"測試網站已經在 http://127.0.0.1:{port}/ 執行，直接沿用。"
    finally:
        site.shutdown()
        site.server_close()


def test_testsite_open_to_other_computers(monkeypatch: pytest.MonkeyPatch) -> None:
    """--testsite-host 0.0.0.0：其他電腦用區網位址連得到；訊息附上沒有保護的提醒。"""
    monkeypatch.setattr("rpa_worker.environment.lan_address", lambda: "192.168.1.10")
    with occupied() as port:
        pass
    site, message = start_testsite(port, "0.0.0.0")
    assert site is not None
    try:
        assert site.server_address[0] == "0.0.0.0"
        first, second = message.splitlines()
        assert first == f"測試網站：http://192.168.1.10:{port}/"
        assert second.startswith(f"注意：測試網站對其他電腦開放（http://192.168.1.10:{port}/")
        assert "防火牆" in second
        # 綁定所有介面時，本機照樣認得出它
        again, reused = start_testsite(port, "0.0.0.0")
        assert again is None
        assert reused == f"測試網站已經在 http://192.168.1.10:{port}/ 執行，直接沿用。"
    finally:
        site.shutdown()
        site.server_close()


def test_testsite_port_used_by_another_program() -> None:
    with occupied() as busy:
        site, message = start_testsite(busy)
    assert site is None
    assert message.startswith(f"埠號 {busy} 被其他程式占用，沒有啟動測試網站")


def test_no_warning_when_browsers_are_downloaded() -> None:
    assert browser_warning([]) is None


def test_warning_says_which_browser_and_the_command() -> None:
    warning = browser_warning(["firefox"])
    assert warning == (
        "這台電腦還沒有下載 Firefox，用到的場景會執行失敗。"
        "在專案資料夾執行 uv run playwright install firefox 下載即可，不用重新啟動 Portal。"
    )
    both = browser_warning(["chromium", "firefox"])
    assert both is not None
    assert both.startswith("這台電腦還沒有下載 Chromium、Firefox，")
    assert "uv run playwright install chromium firefox" in both


@pytest.mark.parametrize("local_worker", [True, False])
def test_server_only_skips_browser_driver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_worker: bool
) -> None:
    calls: list[bool] = []

    def missing() -> list[str]:
        calls.append(True)
        return ["chromium"]

    def no_server(self: uvicorn.Server, sockets: list[socket.socket] | None = None) -> None:
        pass

    monkeypatch.setattr("rpa_runner.installed.missing_browsers", missing)
    monkeypatch.setattr(uvicorn.Server, "run", no_server)
    result = CliRunner().invoke(
        build_cli(),
        [
            "serve",
            "--port",
            "0",
            "--data",
            str(tmp_path),
            "--no-testsite",
            "--local-worker" if local_worker else "--no-local-worker",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == ([True] if local_worker else [])
    assert ("playwright install" in result.output) == local_worker
