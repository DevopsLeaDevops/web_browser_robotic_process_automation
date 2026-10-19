"""用獨立暫存資料與隨機埠，驗證 .venv-server 的 HTTP 啟動、配對及重新啟動。"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(
    port: int, path: str, payload: dict[str, object] | None = None, *, status: int = 200
) -> dict[str, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        response = OPENER.open(req, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        actual = response.code
        body = response.read()
    if actual != status:
        raise RuntimeError(f"{path}: HTTP {actual}，預期 {status}")
    value: object = json.loads(body)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: 預期 JSON 物件")
    return cast("dict[str, object]", value)


def smoke() -> None:
    # 同時保留兩個 socket，確保選到不同的埠；真正的 serve 仍需自行 bind。
    with socket.socket() as admin_socket, socket.socket() as worker_socket:
        admin_socket.bind(("127.0.0.1", 0))
        worker_socket.bind(("127.0.0.1", 0))
        admin = int(admin_socket.getsockname()[1])
        worker = int(worker_socket.getsockname()[1])
    with TemporaryDirectory(prefix="rpa-server-smoke-") as directory:
        data = Path(directory)
        log_path = data / "server.log"
        # 不繼承真實資料庫與 RPA 設定；本機 HTTP 也直接連線。
        env = {key: value for key, value in os.environ.items() if not key.startswith("RPA_")}
        env["RPA_LANG"] = "en"
        command = [
            str(ROOT / ".venv-server/bin/rpa"),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(admin),
            "--worker-host",
            "127.0.0.1",
            "--worker-port",
            str(worker),
            "--data",
            str(data),
            "--no-local-worker",
            "--no-testsite",
        ]
        for restart in (False, True):
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 40
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("伺服器提前結束")
                        try:
                            request(admin, "/api/openapi.json")
                            break
                        except OSError:
                            if time.monotonic() > deadline:
                                raise RuntimeError("伺服器啟動逾時") from None
                            time.sleep(0.2)
                    request(worker, "/api/workers", status=401)
                    request(admin, "/worker-api/v1/hello", {}, status=404)
                    request(worker, "/worker-api/v1/hello", {}, status=401)
                    if restart:
                        request(admin, "/api/workers/linux-smoke")
                    else:
                        request(
                            admin,
                            "/api/workers",
                            {"id": "linux-smoke", "name": "Smoke"},
                            status=201,
                        )
                        invitation = request(admin, "/api/workers/linux-smoke/invite", {})
                        invite = cast("dict[str, object]", invitation["invite"])
                        paired = request(
                            worker, "/client-api/v1/pair", {"app": "worker", "code": invite["code"]}
                        )
                        if paired["device"] != "linux-smoke":
                            raise RuntimeError("裝置配對失敗")
                except Exception:
                    print(log_path.read_text(encoding="utf-8"), file=sys.stderr)
                    raise
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                # uvicorn 完成 lifespan 清理後會重新送出 SIGTERM，POSIX 回傳 -15 仍屬正常。
                output = log_path.read_text(encoding="utf-8")
                if (
                    process.returncode not in (0, -signal.SIGTERM)
                    or "Application shutdown complete" not in output
                ):
                    print(output, file=sys.stderr)
                    raise RuntimeError(f"伺服器未正常關閉：{process.returncode}")
        if not (data / "rpa.db").is_file():
            raise RuntimeError("沒有產生 SQLite 資料庫")
        print("Linux 伺服器冒煙通過：HTTP、埠隔離、裝置配對、重新啟動保留資料。")


if __name__ == "__main__":
    smoke()
