"""模擬內部系統的本機測試網站，沿用 MVP 原型 python-demo/target 的頁面與 API。

- ``/``：建立範例紀錄（標題、數量）；``/?view=query``：依紀錄編號查詢
- ``POST /api/records``、``GET /api/records/<編號>``：資料只存在記憶體，程序結束就消失
- 只綁定 127.0.0.1；不連線任何外部系統

測試用 ``running()`` 在隨機埠號啟動；手動試用：``uv run python -m testsite --port 8765``。
"""

import json
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final, cast
from urllib.parse import unquote, urlsplit

__all__ = ["MAX_QUANTITY", "PAGE", "create_server", "running"]

PAGE: Final = Path(__file__).with_name("index.html")
MAX_QUANTITY: Final = 30
_MAX_BODY: Final = 8192


def create_server(port: int = 0) -> ThreadingHTTPServer:
    """建立測試網站；port 為 0 時由系統挑一個空的埠號（server.server_port）。"""
    records: dict[str, dict[str, object]] = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """不輸出存取紀錄。"""

        def _reply(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict[str, object]) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self._reply(status, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                self._reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
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
            if self.path != "/api/records":
                self._json(404, {"error": "找不到介面"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= _MAX_BODY:
                    raise ValueError("資料大小不符")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise TypeError("資料格式不符")
                fields = cast("dict[str, object]", data)
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

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


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
