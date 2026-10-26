"""WorkerClient.download：裝置從管理 Portal 下載更新檔（ADR 0018），對假的 HTTP 伺服器測試。"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from rpa_worker.protocol import API_PREFIX
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient

DATA = bytes(range(256)) * 4096  # 1 MiB


class _Portal(BaseHTTPRequestHandler):
    tokens: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:
        self.tokens.append(self.headers.get("Authorization"))
        if self.path == f"{API_PREFIX}/update/file":
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(DATA)))
            self.end_headers()
            self.wfile.write(DATA)
            return
        body = json.dumps(
            {"error": {"code": "update_unavailable", "message": "沒有更新檔"}}
        ).encode()
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def portal() -> Iterator[str]:
    _Portal.tokens = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_download_streams_to_a_file(portal: str, tmp_path: Path) -> None:
    target = tmp_path / "update.zip"
    size = WorkerClient(portal, "tok").download("/update/file", target, limit=len(DATA))
    assert size == len(DATA)
    assert target.read_bytes() == DATA
    assert _Portal.tokens == ["Bearer tok"]


def test_download_errors_leave_no_file(portal: str, tmp_path: Path) -> None:
    target = tmp_path / "update.zip"
    client = WorkerClient(portal, "tok")
    with pytest.raises(ConnectionLostError, match="larger than"):
        client.download("/update/file", target, limit=len(DATA) - 1)
    assert not target.exists()
    with pytest.raises(WorkerApiError) as raised:
        client.download("/other", target, limit=len(DATA))
    assert (raised.value.status, raised.value.code) == (404, "update_unavailable")
    assert not target.exists()
    with pytest.raises(ConnectionLostError):
        WorkerClient("http://127.0.0.1:9", "tok").download("/update/file", target, limit=10)
    assert not target.exists()
