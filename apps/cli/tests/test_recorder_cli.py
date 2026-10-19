"""`rpa recorder`（M10.2）：說明、配對、事件的文字；權杖被拒時結束。

不真的錄製：錄製端本身在 apps/worker 的測試，經由管理 Portal 的完整流程在 apps/server 的端到端測試。
"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_cli.recorder import describe_event, resolve_pairing
from rpa_core.i18n import use_locale
from rpa_worker.pairing import CLIENT_API_PREFIX, PAIRING_FILE, PairResult, save_pairing

CODE = "abcdefghijklmnopqrstuvwxyz012345"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        install_click_translations()
        yield


def invoke(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(build_cli(), list(args))
    return result.exit_code, result.output


def save(folder: Path, server: str, token: str = "saved-token") -> None:
    save_pairing(
        folder / PAIRING_FILE,
        PairResult(
            server=server,
            device="mac-01",
            name="Mac",
            app="recorder",
            token=token,
            protocol=1,
            fingerprint=None,
            version=None,
        ),
    )


def test_help_lists_the_options() -> None:
    code, output = invoke("recorder", "--help")
    assert code == 0
    for option in ("--invite", "--server", "--port", "--no-open", "--no-testsite", "--work-dir"):
        assert option in output
    code, output = invoke("--help")
    assert "recorder" in output


def test_pairing_is_required(tmp_path: Path) -> None:
    code, output = invoke("recorder", "--work-dir", str(tmp_path / "work"))
    assert code == 1
    assert "還沒有配對" in output
    assert "--invite" in output
    assert not (tmp_path / "work").exists()


def test_pairing_offline_is_explained(tmp_path: Path) -> None:
    line = f"rpa://pair?server=http://127.0.0.1:9&app=recorder&code={CODE}"
    code, output = invoke("recorder", "--invite", line, "--work-dir", str(tmp_path))
    assert code == 1
    assert "--worker-port" in output
    assert not (tmp_path / PAIRING_FILE).exists()


def test_saved_pairing_and_server_override(tmp_path: Path) -> None:
    save(tmp_path, "http://192.168.1.10:8081")
    assert resolve_pairing(None, None, tmp_path) == ("http://192.168.1.10:8081", "saved-token")
    assert resolve_pairing("10.0.0.5:8081", None, tmp_path) == (
        "http://10.0.0.5:8081",
        "saved-token",
    )


def test_events_are_described() -> None:
    online = describe_event(
        "online",
        {"device": "mac-01", "sameVersion": False, "fingerprint": "a", "serverFingerprint": "b"},
    )
    assert online is not None
    assert "mac-01" in online
    assert "git pull" in online
    assert describe_event("started", {"module": "rpa_runner.record"}) == "開始錄製。"
    assert describe_event("started", {"module": "playwright"}) == "開始錄製。"
    assert describe_event("finished", {"module": "rpa_runner.debug", "exit": 0}) == (
        "逐步調試結束（結束碼 0）。"
    )
    started = describe_event("started", {"module": "rpa_runner.other"})
    assert started is not None
    assert "rpa_runner.other" in started
    for event in ("offline", "rejected"):
        assert describe_event(event, {"server": "s", "reason": "x", "message": "m"})
    assert describe_event("unknown", {}) is None
    with use_locale("en"):
        assert describe_event("started", {"module": "rpa_runner.login"}) == "Started manual login."


@pytest.fixture
def refusing_server() -> Iterator[tuple[str, list[str]]]:
    """假的管理 Portal：Client API 一律回 401（例如錄製端在裝置頁被停用）。"""
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return None

        def do_POST(self) -> None:
            paths.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            error = {"code": "recorder_unauthorized", "message": "錄製端權杖不對"}
            data = json.dumps({"error": error}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", paths
    finally:
        server.shutdown()
        server.server_close()


def test_rejected_token_ends_the_command(
    tmp_path: Path, refusing_server: tuple[str, list[str]]
) -> None:
    server, paths = refusing_server
    save(tmp_path, server)
    code, output = invoke(
        "recorder", "--work-dir", str(tmp_path), "--no-open", "--no-testsite", "--name", "測試 Mac"
    )
    assert code == 1, output
    assert "錄製端「測試 Mac」啟動" in output
    assert "/__gateway/login?key=" in output
    assert "錄製端權杖不對" in output
    assert paths == [CLIENT_API_PREFIX + "/hello"]
