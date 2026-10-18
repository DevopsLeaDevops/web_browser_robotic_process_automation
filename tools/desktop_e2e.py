"""打包版 RPA Worker 的端到端測試（M10.1）：用邀請配對、以「遠端 worker」執行範例場景。

CI 的桌面端建置在 Windows 建好 RPA Worker、跑完自我測試之後執行（自我測試已經把 Chromium
下載到 ``PLAYWRIGHT_BROWSERS_PATH``，這裡沿用）::

    uv run python tools/desktop_e2e.py <App 執行檔> [--report e2e.json]

1. 從原始碼啟動管理 Portal：暫存資料夾、對外埠只聽 127.0.0.1、這台不執行（--no-local-worker）、
   不啟動測試網站（打包版自己在 127.0.0.1:8765 啟動）。
2. 用管理 API 新增裝置、產生邀請。
3. **打包版**以 ``--no-window --invite`` 配對並啟動：和視窗版同一個 controller（配對、權杖存進
   Windows 認證管理員、下載瀏覽器、接任務），訊息寫到 ``--log``（視窗程式沒有標準輸出）。
4. 等裝置上線，確認回報的是建置資訊的版本與程式指紋（和 Portal 相同）；建置資訊從同資料夾的
   ``rpa-child --version`` 讀（主控台程式）。記下權杖存在哪裡（認證管理員或退回的檔案）。
5. 以「遠端 worker」無頭執行 BA-001，再用它的出參執行 BA-002：兩個都要通過、都由這台裝置執行，
   報告回到 Portal。
6. 結束兩個程序（打包版先用資料夾的 ``stop.request`` 請它自己結束：視窗程式收不到 Ctrl+C），
   印出 JSON 摘要（``--report`` 另外寫檔，格式和自我測試相同，
   可以用 ``tools/ci_annotations.py self-test`` 轉成 annotations）。全部通過才回傳 0。
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Final, cast

ROOT: Final = Path(__file__).resolve().parent.parent
DEVICE: Final = "ci-worker"
_TAIL: Final = 3000

JsonObject = dict[str, object]


class StepFailedError(Exception):
    pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Api:
    """管理 Portal 的 /api（本機，不走代理）。"""

    def __init__(self, base: str) -> None:
        self.base = base
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, payload: object = None) -> JsonObject:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                body: object = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise StepFailedError(f"{method} {path} → {error.code}: {detail[:500]}") from None
        return cast("JsonObject", body) if isinstance(body, dict) else {}


def _wait(what: str, check: Callable[[], JsonObject | None], timeout: float) -> JsonObject:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
        except (OSError, StepFailedError) as error:
            last, value = error, None
        if value is not None:
            return value
        time.sleep(1)
    raise StepFailedError(f"{what}：{timeout:.0f} 秒內沒有完成" + (f"（{last}）" if last else ""))


def _tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-_TAIL:]
    except OSError:
        return ""


def _stop(process: subprocess.Popen[bytes] | None, request: Path | None = None) -> None:
    """結束程序。給了 ``request`` 時先寫入這個檔案請它自己結束（取消任務並回報），
    等不到才強制結束。"""
    if process is None or process.poll() is not None:
        return
    if request is not None:
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text("e2e", encoding="utf-8")
        try:
            process.wait(timeout=60)
            return
        except subprocess.TimeoutExpired:
            pass
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=30)


def _validate(api: Api, scene: str, inputs: JsonObject) -> JsonObject:
    """以「遠端 worker」無頭驗證一個範例場景，等它結束。"""
    payload = {"inputs": inputs, "headless": True, "engine": "chromium", "target": "remote"}
    created = api.call("POST", f"/api/scenes/{scene}/revisions/1/validate", payload)
    run_id = str(created.get("id"))

    def finished() -> JsonObject | None:
        run = api.call("GET", f"/api/runs/{run_id}")
        return run if run.get("finished") else None

    run = _wait(f"{scene} 的執行 {run_id}", finished, 300)
    if run.get("status") != "passed" or run.get("workerId") != DEVICE:
        raise StepFailedError(
            f"{scene}：狀態 {run.get('status')}、執行的裝置 {run.get('workerId')}、"
            f"錯誤 {run.get('error')}"
        )
    files = cast("list[object]", run.get("files") or [])
    if "report.html" not in files:
        raise StepFailedError(f"{scene}：報告沒有回到 Portal（檔案 {files[:10]}）")
    return run


def run(app: Path, folder: Path) -> JsonObject:
    steps: list[JsonObject] = []
    portal_port, external_port = _free_port(), _free_port()
    base = f"http://127.0.0.1:{portal_port}"
    portal_log, app_log = folder / "portal.log", folder / "worker.log"
    app_output = folder / "worker.out"  # 視窗程式沒有標準輸出；正常是空的
    portal: subprocess.Popen[bytes] | None = None
    worker: subprocess.Popen[bytes] | None = None
    handles: list[IO[bytes]] = []

    def step(name: str, action: Callable[[], str]) -> bool:
        started = time.monotonic()
        try:
            detail = action()
        except Exception as error:
            steps.append(
                {
                    "step": name,
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                    "seconds": round(time.monotonic() - started, 1),
                    "output": (
                        f"--- portal ---\n{_tail(portal_log)}\n--- worker ---\n{_tail(app_log)}"
                    ),
                }
            )
            return False
        seconds = round(time.monotonic() - started, 1)
        steps.append({"step": name, "ok": True, "detail": detail, "seconds": seconds})
        return True

    api = Api(base)
    child = app.with_name("rpa-child" + app.suffix)  # 主控台程式，同一份建置
    printed = subprocess.run([str(child), "--version"], capture_output=True, check=True).stdout
    version = cast("JsonObject", json.loads(printed))
    state: JsonObject = {}

    def start_portal() -> str:
        nonlocal portal
        handle = portal_log.open("wb")
        handles.append(handle)
        command = [
            sys.executable, "-m", "rpa_cli", "serve",
            "--data", str(folder / "data"),
            "--port", str(portal_port),
            "--worker-port", str(external_port),
            "--worker-host", "127.0.0.1",
            "--no-local-worker",
            "--no-testsite",
        ]  # fmt: skip
        portal = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        _wait("管理 Portal 啟動", lambda: api.call("GET", "/api/workers"), 120)
        return base

    def invite() -> str:
        api.call("POST", "/api/workers", {"id": DEVICE, "name": "CI Worker"})
        reply = cast("JsonObject", api.call("POST", f"/api/workers/{DEVICE}/invite")["invite"])
        expected = f"http://127.0.0.1:{external_port}"
        if reply.get("server") != expected:
            raise StepFailedError(f"邀請的伺服器是 {reply.get('server')}，應該是 {expected}")
        state["line"] = str(reply["line"])
        return str(reply["server"])

    def start_worker() -> str:
        nonlocal worker
        handle = app_output.open("wb")
        handles.append(handle)
        env = {**os.environ, "RPA_WORKER_HOME": str(folder / "worker-home")}
        worker = subprocess.Popen(
            [str(app), "--no-window", "--invite", str(state["line"]), "--log", str(app_log)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )

        def online() -> JsonObject | None:
            if worker is not None and worker.poll() is not None:
                raise StepFailedError(f"打包版結束了（結束碼 {worker.returncode}）")
            record = api.call("GET", f"/api/workers/{DEVICE}")
            return record if record.get("status") == "online" else None

        record = _wait("裝置上線", online, 300)
        if record.get("version") != version.get("version"):
            raise StepFailedError(
                f"回報的版本 {record.get('version')}，建置資訊是 {version.get('version')}"
            )
        if record.get("fingerprint") != version.get("fingerprint") or not record.get("sameVersion"):
            mine, built = record.get("fingerprint"), version.get("fingerprint")
            same = record.get("sameVersion")
            raise StepFailedError(
                f"回報的程式指紋 {mine}，建置資訊是 {built}，和 Portal 相同：{same}"
            )
        pairing = folder / "worker-home" / "pairing.json"
        if not pairing.is_file():
            raise StepFailedError("配對結果沒有存在 RPA_WORKER_HOME")
        saved = cast("JsonObject", json.loads(pairing.read_text(encoding="utf-8")))
        if sys.platform == "win32" and "token" in saved:
            # 打包時漏了 keyring 的 Windows 後端（或 pywin32-ctypes）時會退回存在檔案：要擋下來
            raise StepFailedError(
                "權杖沒有存進 Windows 認證管理員（退回存在配對檔），見 worker.log"
            )
        storage = "退回配對檔" if "token" in saved else "認證管理員"
        return f"{record.get('os')}；瀏覽器 {record.get('browsers')}；權杖存在{storage}"

    def ba_001() -> str:
        result = _validate(api, "ba-001", {})
        output = cast("JsonObject", result.get("output") or {})
        state["recordId"] = str(output.get("recordId"))
        return f"{result.get('id')} → recordId {state['recordId']}"

    def ba_002() -> str:
        result = _validate(api, "ba-002", {"recordId": state["recordId"]})
        return str(result.get("id"))

    try:
        for name, action in (
            ("portal", start_portal),
            ("invite", invite),
            ("pair", start_worker),
            ("ba-001", ba_001),
            ("ba-002", ba_002),
        ):
            if not step(name, action):
                break
    finally:
        _stop(worker, folder / "worker-home" / "stop.request")
        _stop(portal)
        for handle in handles:
            handle.close()
    ok = len(steps) == 5 and all(item["ok"] for item in steps)
    return {"ok": ok, "build": version, "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="打包版 RPA Worker 的端到端測試")
    parser.add_argument("app", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    # Windows 上剛結束的程序可能還鎖著檔案：清不掉暫存資料夾不影響結果
    with tempfile.TemporaryDirectory(prefix="rpa-e2e-", ignore_cleanup_errors=True) as folder:
        summary = run(args.app.resolve(), Path(folder))
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
