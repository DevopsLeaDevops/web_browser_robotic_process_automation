"""打包版 RPA 錄製端的端到端測試（M10.2）：用邀請配對、經由本機閘道在錄製端逐步調試。

CI 的桌面端建置在 macOS 建好 RPA 錄製端、跑完自我測試之後執行（自我測試已經把 Chromium
下載到 ``PLAYWRIGHT_BROWSERS_PATH``，這裡沿用）::

    uv run python tools/recorder_e2e.py <App 裡的 rpa-recorder> [--report e2e.json]

1. 從原始碼啟動管理 Portal：暫存資料夾、對外埠只聽 127.0.0.1、這台不執行（--no-local-worker）、
   不啟動測試網站（打包版自己在 127.0.0.1:8765 啟動）。
2. 用管理 API 新增「RPA 錄製端」裝置、產生邀請。
3. **打包版**以 ``--no-window --invite`` 配對並啟動：和視窗版同一個 controller 與本機閘道（配對、
   權杖存進鑰匙圈、下載瀏覽器、執行管理 Portal 交來的子程序），只是不開 App 的視窗；經由閘道打開
   管理 Portal 的網址寫到 ``--url-file``。
4. 等裝置上線：回報的版本與程式指紋要和建置資訊（同資料夾 ``rpa-child --version``）相同、
   能顯示視窗、有 Chromium；權杖要存在鑰匙圈（退回存在檔案代表打包漏了 keyring 的後端）。
5. 經由閘道打開管理 Portal：頁首有「透過錄製端」；沒有閘道的 Cookie 時 403；直接打對外埠時 401。
6. 經由閘道開始 BA-001 的逐步調試，**無頭與有頭各一次**（有頭：瀏覽器視窗開在這台，
   ``--no-window`` 少的只是 App 的視窗）：工作階段在錄製端、執行第一步通過、截圖傳回管理 Portal
   再經由閘道拿得到；結束後錄製端的暫存資料夾清空。
   調試中檢查程序：無頭時只有 headless shell（或帶 ``--headless``），有頭時有一般的 Chromium。
7. 在資料夾寫 ``stop.request`` 請打包版結束（結束碼 0），網址檔刪掉。
8. 不給邀請再啟動一次（用鑰匙圈裡存下的配對），上線後送 SIGTERM，結束碼 0；最後結束管理 Portal。

印出 JSON 摘要（``--report`` 另外寫檔，格式和自我測試相同，可以用
``tools/ci_annotations.py self-test`` 轉成 annotations）。全部通過才回傳 0。
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Final, cast
from urllib.parse import parse_qs, urlsplit

from desktop_e2e import (
    ROOT,
    Api,
    JsonObject,
    StepFailedError,
    free_port,
    stop_process,
    tail,
    wait_until,
)

DEVICE: Final = "ci-recorder"
COOKIE: Final = "rpa_gateway"  # rpa_worker.gateway.COOKIE（這裡不匯入：只用標準函式庫）


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class Gateway:
    """經由打包版的本機閘道打開管理 Portal（像 App 的視窗一樣帶著閘道的 Cookie）。"""

    def __init__(self, login: str) -> None:
        parts = urlsplit(login)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.login = login
        self.secret = parse_qs(parts.query)["key"][0]
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(
        self, method: str, path: str, payload: object = None, *, cookie: bool = True
    ) -> tuple[int, bytes]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if cookie:
            headers["Cookie"] = f"{COOKIE}={self.secret}"
        url = path if path.startswith("http") else self.origin + path
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def json(self, method: str, path: str, payload: object = None) -> JsonObject:
        status, body = self.request(method, path, payload)
        if status >= 400:
            text = body.decode("utf-8", "replace")
            raise StepFailedError(f"{method} {path}（經由閘道）→ {status}: {text[:500]}")
        value: object = json.loads(body or b"{}")
        return cast("JsonObject", value) if isinstance(value, dict) else {}


def browser_processes() -> list[str]:
    """Playwright 下載的瀏覽器的主程序（不含 ``--type=`` 的子程序與 crashpad）的命令列。"""
    folder = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not folder:
        return []
    listed = subprocess.run(
        ["ps", "-axww", "-o", "command="], capture_output=True, text=True, check=False
    ).stdout
    return [
        line
        for line in listed.splitlines()
        if folder in line and "--type=" not in line and "crashpad" not in line.lower()
    ]


def check_browser(headless: bool) -> str:
    """調試中真的開了有頭（或無頭）的瀏覽器：無頭用 headless shell 或 ``--headless``，有頭沒有。"""
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return "（沒有 PLAYWRIGHT_BROWSERS_PATH，不檢查程序）"
    lines = browser_processes()
    if not lines:
        raise StepFailedError("調試中找不到 Playwright 的瀏覽器程序")
    headed = [line for line in lines if "headless" not in line.lower()]
    sample = (headed or lines)[0][:300]
    if headless and headed:
        raise StepFailedError(f"要的是無頭，卻有有頭的瀏覽器：{sample}")
    if not headless and not headed:
        raise StepFailedError(f"要的是有頭，瀏覽器卻是無頭的：{sample}")
    return Path(sample.split(" --", 1)[0]).name


def run(app: Path, folder: Path) -> JsonObject:
    steps: list[JsonObject] = []
    portal_port, external_port = free_port(), free_port()
    base = f"http://127.0.0.1:{portal_port}"
    external = f"http://127.0.0.1:{external_port}"
    portal_log, app_log = folder / "portal.log", folder / "recorder.log"
    app_output = folder / "recorder.out"  # 視窗程式沒有標準輸出；正常是空的
    url_file = folder / "portal-url.txt"
    home = folder / "recorder-home"
    env = {**os.environ, "RPA_RECORDER_HOME": str(home)}
    portal: subprocess.Popen[bytes] | None = None
    recorder: subprocess.Popen[bytes] | None = None
    handles: list[IO[bytes]] = []
    api = Api(base)
    state: dict[str, object] = {}
    built: JsonObject = {}

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
                    "output": "\n".join(
                        f"--- {log.name} ---\n{tail(log)}"
                        for log in (portal_log, app_log)
                        if log.exists()
                    ),
                }
            )
            return False
        seconds = round(time.monotonic() - started, 1)
        steps.append({"step": name, "ok": True, "detail": detail, "seconds": seconds})
        return True

    def build_info() -> JsonObject:
        """建置資訊：同資料夾的 rpa-child --version（主控台程式，同一份建置）。"""
        if not built:
            child = app.with_name("rpa-child")
            printed = subprocess.run([str(child), "--version"], capture_output=True, check=True)
            built.update(cast("JsonObject", json.loads(printed.stdout)))
        return built

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
        wait_until("管理 Portal 啟動", lambda: api.call("GET", "/api/recorders"), 120)
        return base

    def invite() -> str:
        api.call("POST", "/api/recorders", {"id": DEVICE, "name": "CI Recorder"})
        reply = cast("JsonObject", api.call("POST", f"/api/recorders/{DEVICE}/invite")["invite"])
        if reply.get("server") != external:
            raise StepFailedError(f"邀請的伺服器是 {reply.get('server')}，應該是 {external}")
        state["line"] = str(reply["line"])
        return str(reply["server"])

    def launch(invite: bool) -> JsonObject:
        """以 --no-window 啟動打包版（第一次用邀請配對，之後用存下的配對），等它上線。"""
        nonlocal recorder
        handle = app_output.open("ab")
        handles.append(handle)
        command = [str(app), "--no-window", "--url-file", str(url_file), "--log", str(app_log)]
        if invite:
            command += ["--invite", str(state["line"])]
        recorder = subprocess.Popen(
            command, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT
        )

        def online() -> JsonObject | None:
            if recorder is not None and recorder.poll() is not None:
                raise StepFailedError(f"打包版結束了（結束碼 {recorder.returncode}）")
            record = api.call("GET", f"/api/recorders/{DEVICE}")
            return record if record.get("status") == "online" else None

        return wait_until("錄製端上線", online, 300)

    def start_recorder() -> str:
        record = launch(invite=True)
        version = build_info()
        if record.get("version") != version.get("version"):
            raise StepFailedError(
                f"回報的版本 {record.get('version')}，建置資訊是 {version.get('version')}"
            )
        if record.get("fingerprint") != version.get("fingerprint") or not record.get("sameVersion"):
            mine, expected = record.get("fingerprint"), version.get("fingerprint")
            same = record.get("sameVersion")
            raise StepFailedError(
                f"回報的程式指紋 {mine}，建置資訊是 {expected}，和 Portal 相同：{same}"
            )
        if record.get("display") is not True:
            raise StepFailedError("--no-window 的錄製端回報不能顯示視窗：有頭模式會被擋下")
        browsers = cast("list[object]", record.get("browsers") or [])
        if "chromium" not in browsers:
            raise StepFailedError(f"回報的瀏覽器沒有 Chromium：{browsers}")
        saved = cast("JsonObject", json.loads((home / "pairing.json").read_text(encoding="utf-8")))
        if "token" in saved:
            # 打包時漏了 keyring 的 macOS 後端時會退回存在檔案：要擋下來
            raise StepFailedError("權杖沒有存進鑰匙圈（退回存在配對檔），見 recorder.log")
        if not url_file.is_file():
            raise StepFailedError("--url-file 沒有寫出經由閘道打開管理 Portal 的網址")
        if url_file.stat().st_mode & 0o077:
            raise StepFailedError("網址檔帶著閘道的密語，應該只有本人能讀")
        state["gateway"] = Gateway(url_file.read_text(encoding="utf-8").strip())
        return f"{record.get('os')}；瀏覽器 {browsers}；權杖存在鑰匙圈"

    def through_gateway() -> str:
        gateway = cast("Gateway", state["gateway"])
        status, _ = gateway.request("GET", "/devices", cookie=False)
        if status != 403:
            raise StepFailedError(f"沒有閘道的 Cookie 時應該 403，結果 {status}")
        status, _ = gateway.request("GET", gateway.login, cookie=False)
        if status not in (302, 303):
            raise StepFailedError(f"閘道的登入網址應該轉到管理 Portal，結果 {status}")
        status, page = gateway.request("GET", "/devices")
        if status != 200 or b'id="via-recorder"' not in page:
            raise StepFailedError(f"經由閘道打開的頁面沒有「透過錄製端」（{status}）")
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            direct.open(external + "/scenes", timeout=30)
            raise StepFailedError("沒有權杖直接打開對外埠的管理頁面應該是 401")
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise StepFailedError(f"沒有權杖時對外埠回 {error.code}，應該是 401") from None
        return f"{gateway.origin} → {external}"

    def debug(headless: bool) -> str:
        gateway = cast("Gateway", state["gateway"])
        payload = {"engine": "chromium", "headless": headless, "restart": True}
        session = gateway.json("POST", "/api/scenes/ba-001/debug", payload)
        session_id = str(session.get("id"))
        if session.get("deviceId") != DEVICE:
            raise StepFailedError(f"調試沒有交給錄製端（deviceId {session.get('deviceId')}）")
        if session.get("headless") is not headless:
            given = session.get("headless")
            raise StepFailedError(f"要的是 headless={headless}，工作階段是 {given}")

        def settled() -> JsonObject | None:
            current = gateway.json("GET", f"/api/debug/{session_id}")
            return current if current.get("status") in ("ready", "failed") else None

        ready = wait_until("調試的瀏覽器啟動", settled, 180)
        if ready.get("status") != "ready":
            raise StepFailedError(f"調試沒有啟動：{ready.get('message')}")
        record = api.call("GET", f"/api/recorders/{DEVICE}")
        if record.get("status") != "busy":
            raise StepFailedError(f"調試中錄製端的狀態是 {record.get('status')}，應該是使用中")
        seen = check_browser(headless)
        result = gateway.json("POST", f"/api/debug/{session_id}/steps/0")
        first = cast("list[JsonObject]", result.get("steps") or [{}])[0]
        if first.get("status") != "passed":
            raise StepFailedError(f"第一步沒有通過：{first.get('status')} {first.get('error')}")
        status, image = gateway.request("GET", str(result.get("screenshotUrl")))
        if status != 200 or not image.startswith(b"\x89PNG"):
            raise StepFailedError(f"錄製端的截圖沒有經由閘道傳回來（{status}）")
        gateway.json("DELETE", f"/api/debug/{session_id}")

        def cleaned() -> JsonObject | None:
            idle = api.call("GET", f"/api/recorders/{DEVICE}").get("status") == "online"
            left = list((home / "sessions").glob("rpa-*")) if (home / "sessions").exists() else []
            return {} if idle and not left else None

        wait_until("錄製端的子程序結束、暫存資料夾刪掉", cleaned, 60)
        mode = "無頭" if headless else "有頭（瀏覽器視窗開在這台）"
        return f"{mode}：第一步通過，截圖 {len(image)} bytes；瀏覽器 {seen}"

    def restart() -> str:
        """再啟動一次（不給邀請：用鑰匙圈裡存下的配對），用 SIGTERM 結束（Ctrl+C 同理）。"""
        launch(invite=False)
        assert recorder is not None
        recorder.send_signal(signal.SIGTERM)
        try:
            code = recorder.wait(timeout=60)
        except subprocess.TimeoutExpired:
            raise StepFailedError("送了 SIGTERM，打包版 60 秒內沒有結束") from None
        if code != 0:
            raise StepFailedError(f"SIGTERM 之後的結束碼是 {code}（應該是 0）")
        if url_file.exists():
            raise StepFailedError("結束後網址檔還在")
        return "用存下的配對（鑰匙圈）直接上線；SIGTERM 後正常結束"

    def stop() -> str:
        if recorder is None:
            raise StepFailedError("打包版沒有在執行")
        (home / "stop.request").write_text("e2e", encoding="utf-8")
        try:
            code = recorder.wait(timeout=60)
        except subprocess.TimeoutExpired:
            raise StepFailedError("寫了 stop.request，打包版 60 秒內沒有結束") from None
        if code != 0:
            raise StepFailedError(f"打包版的結束碼是 {code}（應該是 0）")
        if url_file.exists():
            raise StepFailedError("結束後網址檔還在")
        return "收到 stop.request 後正常結束，網址檔已刪除"

    plan: list[tuple[str, Callable[[], str]]] = [
        ("portal", start_portal),
        ("invite", invite),
        ("pair", start_recorder),
        ("gateway", through_gateway),
        ("debug-headless", lambda: debug(True)),
        ("debug-headed", lambda: debug(False)),
        ("stop", stop),
        ("restart", restart),
    ]
    try:
        for name, action in plan:
            if not step(name, action):
                break
    finally:
        stop_process(recorder, home / "stop.request")
        stop_process(portal)
        for handle in handles:
            handle.close()
    ok = len(steps) == len(plan) and all(item["ok"] for item in steps)
    return {"ok": ok, "build": built, "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="打包版 RPA 錄製端的端到端測試")
    parser.add_argument("app", type=Path, help="App 裡的 Contents/MacOS/rpa-recorder")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="rpa-recorder-e2e-") as folder:
        summary = run(args.app.resolve(), Path(folder))
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
