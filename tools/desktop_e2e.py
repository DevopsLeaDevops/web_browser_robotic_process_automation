"""打包版 RPA Worker 的端到端測試（M10.1）：用邀請配對、以「遠端 worker」執行範例場景。

CI 的桌面端建置在 Windows 建好 RPA Worker、跑完自我測試之後執行（自我測試已經把 Chromium
下載到 ``PLAYWRIGHT_BROWSERS_PATH``，這裡沿用）::

    uv run python tools/desktop_e2e.py <App 執行檔> [--installer 安裝檔] [--report e2e.json]

1. 從原始碼啟動管理 Portal：暫存資料夾、對外埠只聽 127.0.0.1、這台不執行（--no-local-worker）、
   不啟動測試網站（打包版自己在 127.0.0.1:8765 啟動）。
2. 用管理 API 新增裝置、產生邀請。
3. **打包版**以 ``--no-window --invite`` 配對並啟動：和視窗版同一個 controller（配對、權杖存進
   Windows 認證管理員、下載瀏覽器、接任務），訊息寫到 ``--log``（視窗程式沒有標準輸出）。
4. 等裝置上線，確認回報的是建置資訊的版本與程式指紋（和 Portal 相同）；建置資訊從同資料夾的
   ``rpa-child --version`` 讀（主控台程式）。記下權杖存在哪裡（認證管理員或退回的檔案）。
5. 以「遠端 worker」無頭執行 BA-001，再用它的出參執行 BA-002：兩個都要通過、都由這台裝置執行，
   報告回到 Portal。再執行 iframe 的範例（M7a，``scenarios/examples/iframe-form.yaml``）：
   打包版回報看得懂 ``frame``（否則伺服器不交給它），在打包版自己的測試網站 ``/frames``
   的巢狀 iframe 裡填寫、勾選、送出，出參是送出後的狀態。新分頁的範例（M7b，
   ``scenarios/examples/popup-form.yaml``）同樣：回報看得懂 ``page``、``popup``，在 ``/popup``
   開出的新分頁新增商品行並儲存。
給了 ``--installer``（M10.1 PR 3）時，第 3 步之前先**靜默安裝**到暫存資料夾（檢查檔案、開始功能表
捷徑、解除安裝項目的版本），之後的步驟都用**裝好的** App；第 5 步之後再加三步：

- **升級**：App 還在接任務時再安裝一次，安裝檔要用 ``stop.request`` 請它結束（結束碼 0）再換檔案。
- **解除安裝**：先放一個「登入時執行」的值（模擬自動啟動），靜默解除安裝後確認程式、捷徑、
  解除安裝項目與那個值都刪了，資料夾的配對保留（靜默解除安裝不問「也刪除資料」，保留）。
- **刪除資料**：再安裝一次，以 ``/REMOVEDATA=yes`` 解除安裝：資料夾刪掉、認證管理員裡的權杖也刪掉
  （解除安裝程式執行 ``rpa-child.exe --forget-pairing``）。

安裝檔與解除安裝的日誌（Inno Setup 的 ``/LOG``）在失敗時附在那一步的輸出。

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
APP_NAME: Final = "RPA Worker"
UNINSTALL_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
RUN_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\Run"
SILENT: Final = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")

JsonObject = dict[str, object]

IFRAME_EXAMPLE: Final = ROOT / "scenarios" / "examples" / "iframe-form.yaml"
"""iframe 的範例（M7a）：表單在 iframe 裡，裡面還有一個 iframe；入參 title 預設「iframe 範例」。"""
IFRAME_STATUS: Final = "已送出：iframe 範例"
POPUP_EXAMPLE: Final = ROOT / "scenarios" / "examples" / "popup-form.yaml"
"""新分頁的範例（M7b）：連結在新分頁打開商品明細；入參 item 預設 455590002。"""
POPUP_STATUS: Final = "已儲存：455590002"


class StepFailedError(Exception):
    pass


def free_port() -> int:
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


def wait_until(what: str, check: Callable[[], JsonObject | None], timeout: float) -> JsonObject:
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


def tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-_TAIL:]
    except OSError:
        return ""


def stop_process(process: subprocess.Popen[bytes] | None, request: Path | None = None) -> None:
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


def create_scene(api: Api, scene: str, path: Path) -> int:
    """用管理 API 建立場景，把第 2 版存成這個檔案的內容；回傳版本號碼。"""
    api.call("POST", "/api/scenes", {"id": scene, "name": scene})
    files = {"scenario.yaml": path.read_text(encoding="utf-8")}
    saved = api.call("POST", f"/api/scenes/{scene}/revisions", {"baseRevision": 1, "files": files})
    return int(cast("int", saved.get("number") or 2))


def _validate(api: Api, scene: str, inputs: JsonObject, revision: int = 1) -> JsonObject:
    """以「遠端 worker」無頭驗證一個範例場景，等它結束。"""
    payload = {"inputs": inputs, "headless": True, "engine": "chromium", "target": "remote"}
    created = api.call("POST", f"/api/scenes/{scene}/revisions/{revision}/validate", payload)
    run_id = str(created.get("id"))

    def finished() -> JsonObject | None:
        run = api.call("GET", f"/api/runs/{run_id}")
        return run if run.get("finished") else None

    run = wait_until(f"{scene} 的執行 {run_id}", finished, 300)
    if run.get("status") != "passed" or run.get("workerId") != DEVICE:
        raise StepFailedError(
            f"{scene}：狀態 {run.get('status')}、執行的裝置 {run.get('workerId')}、"
            f"錯誤 {run.get('error')}"
        )
    files = cast("list[object]", run.get("files") or [])
    if "report.html" not in files:
        raise StepFailedError(f"{scene}：報告沒有回到 Portal（檔案 {files[:10]}）")
    return run


def _uninstall_entry() -> JsonObject | None:
    """目前使用者的「應用程式」裡 RPA Worker 的解除安裝項目（Inno Setup 寫的）。"""
    if sys.platform != "win32":
        raise StepFailedError("只在 Windows 上")
    import winreg

    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        return None
    with root:
        for index in range(winreg.QueryInfoKey(root)[0]):
            with winreg.OpenKey(root, winreg.EnumKey(root, index)) as key:
                values: JsonObject = {}
                for field in ("DisplayName", "DisplayVersion", "InstallLocation"):
                    try:
                        values[field] = winreg.QueryValueEx(key, field)[0]
                    except OSError:
                        values[field] = None
            if values["DisplayName"] == APP_NAME:
                return values
    return None


def _run_value() -> str | None:
    if sys.platform != "win32":
        raise StepFailedError("只在 Windows 上")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, APP_NAME)[0])
    except FileNotFoundError:
        return None


def _set_run_value(command: str) -> None:
    if sys.platform != "win32":
        raise StepFailedError("只在 Windows 上")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)


def _start_menu_shortcut() -> Path:
    return (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft/Windows/Start Menu/Programs"
        / (APP_NAME + ".lnk")
    )


def run(app: Path, folder: Path, installer: Path | None = None) -> JsonObject:
    steps: list[JsonObject] = []
    portal_port, external_port = free_port(), free_port()
    base = f"http://127.0.0.1:{portal_port}"
    portal_log, app_log = folder / "portal.log", folder / "worker.log"
    app_output = folder / "worker.out"  # 視窗程式沒有標準輸出；正常是空的
    portal: subprocess.Popen[bytes] | None = None
    worker: subprocess.Popen[bytes] | None = None
    handles: list[IO[bytes]] = []
    setup_logs: list[Path] = []

    def step(name: str, action: Callable[[], str]) -> bool:
        started = time.monotonic()
        first_log = len(setup_logs)  # 失敗時只附這一步的安裝檔日誌
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
                        for log in [portal_log, app_log, *setup_logs[first_log:]]
                        if log.exists()
                    ),
                }
            )
            return False
        seconds = round(time.monotonic() - started, 1)
        steps.append({"step": name, "ok": True, "detail": detail, "seconds": seconds})
        return True

    api = Api(base)
    state: JsonObject = {}
    home = folder / "worker-home"
    env = {**os.environ, "RPA_WORKER_HOME": str(home)}
    install_dir = folder / "installed"
    built: JsonObject = {}

    def build_info() -> JsonObject:
        """建置資訊：同資料夾的 rpa-child --version（主控台程式，同一份建置）。"""
        if not built:
            child = app.with_name("rpa-child" + app.suffix)
            printed = subprocess.run([str(child), "--version"], capture_output=True, check=True)
            built.update(cast("JsonObject", json.loads(printed.stdout)))
        return built

    def run_setup(log: str) -> subprocess.CompletedProcess[bytes]:
        assert installer is not None
        setup_logs.append(folder / log)
        command = [str(installer), *SILENT, f"/DIR={install_dir}", f"/LOG={folder / log}"]
        return subprocess.run(command, env=env, capture_output=True, timeout=600, check=False)

    def run_uninstall(log: str, *options: str) -> None:
        setup_logs.append(folder / log)
        uninstaller = install_dir / "unins000.exe"
        command = [str(uninstaller), *SILENT, f"/LOG={folder / log}", *options]
        subprocess.run(command, env=env, timeout=600, check=False)

        # 解除安裝程式會把自己複製到暫存資料夾再執行，原本的程序在刪檔案時就先結束了：
        # 等到日誌寫完（usPostUninstall 刪資料在刪完程式之後）
        def removed() -> JsonObject | None:
            closed = "Log closed." in tail(folder / log)
            return {} if closed and not app.exists() and _uninstall_entry() is None else None

        wait_until("解除安裝完成", removed, 300)
        if _start_menu_shortcut().exists():
            raise StepFailedError(f"解除安裝後開始功能表捷徑還在：{_start_menu_shortcut()}")

    def install() -> str:
        nonlocal app
        completed = run_setup("setup-install.log")
        if completed.returncode != 0:
            raise StepFailedError(f"安裝檔結束碼 {completed.returncode}，見 setup-install.log")
        app = install_dir / "rpa-worker.exe"
        for name in ("rpa-worker.exe", "rpa-child.exe", "unins000.exe"):
            if not (install_dir / name).is_file():
                raise StepFailedError(f"安裝後沒有 {name}")
        entry = _uninstall_entry()
        if entry is None:
            raise StepFailedError("「應用程式」裡沒有 RPA Worker 的解除安裝項目")
        if entry["DisplayVersion"] != build_info().get("version"):
            raise StepFailedError(
                f"解除安裝項目的版本 {entry['DisplayVersion']}，建置資訊是 {built.get('version')}"
            )
        if not _start_menu_shortcut().is_file():
            raise StepFailedError(f"沒有開始功能表捷徑 {_start_menu_shortcut()}")
        return f"{install_dir}；版本 {entry['DisplayVersion']}；開始功能表捷徑"

    def upgrade() -> str:
        if worker is None or worker.poll() is not None:
            raise StepFailedError("升級前 App 應該還在執行")
        started = time.monotonic()
        completed = run_setup("setup-upgrade.log")
        if completed.returncode != 0:
            raise StepFailedError(
                f"升級的安裝檔結束碼 {completed.returncode}，見 setup-upgrade.log"
            )
        code = worker.poll()
        if code is None:
            raise StepFailedError("安裝檔換掉檔案時 App 還在執行（沒有收到 stop.request）")
        if code != 0:
            raise StepFailedError(f"App 被安裝檔請求結束時的結束碼是 {code}（應該是 0）")
        if not app.is_file():
            raise StepFailedError("升級後沒有 rpa-worker.exe")
        return f"App 收到 stop.request 後正常結束；升級花了 {round(time.monotonic() - started)} 秒"

    def uninstall() -> str:
        _set_run_value(f'"{app}" --background')  # 模擬 App 寫的自動啟動
        run_uninstall("uninstall.log")
        if _run_value() is not None:
            raise StepFailedError("解除安裝後「登入時執行」的 RPA Worker 還在")
        if not (home / "pairing.json").is_file():
            raise StepFailedError("靜默解除安裝預設應該保留配對，但 pairing.json 不見了")
        return "程式、捷徑、解除安裝項目、自動啟動已刪除；配對保留"

    def remove_data() -> str:
        from rpa_desktop.credentials import Credentials

        completed = run_setup("setup-reinstall.log")
        if completed.returncode != 0:
            raise StepFailedError(f"重新安裝的結束碼 {completed.returncode}")
        pairing = (home / "pairing.json").read_text(encoding="utf-8")
        run_uninstall("uninstall-remove-data.log", "/REMOVEDATA=yes")
        if home.exists():
            left = sorted(path.name for path in home.iterdir())
            raise StepFailedError(f"選擇刪除資料，資料夾還在：{left}")
        if state.get("storage") != "認證管理員":
            return "資料夾已刪除（權杖存在配對檔，沒有認證管理員可查）"
        # 用剛才的配對檔（沒有權杖）在認證管理員找同一個項目：應該已經刪掉
        check = folder / "token-check"
        check.mkdir()
        (check / "pairing.json").write_text(pairing, encoding="utf-8")
        if Credentials(check).load() is not None:
            raise StepFailedError("解除安裝時選擇刪除資料，認證管理員裡的權杖還在")
        return "資料夾與認證管理員裡的權杖都已刪除"

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
        wait_until("管理 Portal 啟動", lambda: api.call("GET", "/api/workers"), 120)
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

        record = wait_until("裝置上線", online, 300)
        version = build_info()
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
        pairing = home / "pairing.json"
        if not pairing.is_file():
            raise StepFailedError("配對結果沒有存在 RPA_WORKER_HOME")
        saved = cast("JsonObject", json.loads(pairing.read_text(encoding="utf-8")))
        if sys.platform == "win32" and "token" in saved:
            # 打包時漏了 keyring 的 Windows 後端（或 pywin32-ctypes）時會退回存在檔案：要擋下來
            raise StepFailedError(
                "權杖沒有存進 Windows 認證管理員（退回存在配對檔），見 worker.log"
            )
        storage = "退回配對檔" if "token" in saved else "認證管理員"
        state["storage"] = storage
        return f"{record.get('os')}；瀏覽器 {record.get('browsers')}；權杖存在{storage}"

    def ba_001() -> str:
        result = _validate(api, "ba-001", {})
        output = cast("JsonObject", result.get("output") or {})
        state["recordId"] = str(output.get("recordId"))
        return f"{result.get('id')} → recordId {state['recordId']}"

    def ba_002() -> str:
        result = _validate(api, "ba-002", {"recordId": state["recordId"]})
        return str(result.get("id"))

    def example(scene: str, path: Path, needs: set[str], status: str) -> str:
        """打包版回報看得懂場景用到的擴充，以遠端 worker 執行範例場景，出參是預期的狀態。"""
        record = api.call("GET", f"/api/workers/{DEVICE}")
        features = record.get("features")
        if not isinstance(features, list) or not needs <= set(cast("list[object]", features)):
            raise StepFailedError(f"打包版沒有回報看得懂 {sorted(needs)}：features={features}")
        revision = create_scene(api, scene, path)
        result = _validate(api, scene, {}, revision)
        output = cast("JsonObject", result.get("output") or {})
        if output.get("status") != status:
            raise StepFailedError(f"出參是 {output}，應該是「{status}」")
        return f"{result.get('id')} → {output.get('status')}"

    def iframe() -> str:
        """M7a：在巢狀 iframe 裡執行範例場景。"""
        return example("iframe-form", IFRAME_EXAMPLE, {"frame"}, IFRAME_STATUS)

    def popup() -> str:
        """M7b：在點擊開出的新分頁上執行範例場景。"""
        return example("popup-form", POPUP_EXAMPLE, {"page", "popup"}, POPUP_STATUS)

    plan: list[tuple[str, Callable[[], str]]] = [("portal", start_portal), ("invite", invite)]
    if installer is not None:
        plan.append(("install", install))
    plan += [("pair", start_worker), ("ba-001", ba_001), ("ba-002", ba_002)]
    plan += [("iframe", iframe), ("popup", popup)]
    if installer is not None:
        plan += [("upgrade", upgrade), ("uninstall", uninstall), ("remove-data", remove_data)]
    try:
        for name, action in plan:
            if not step(name, action):
                break
    finally:
        stop_process(worker, home / "stop.request")
        stop_process(portal)
        for handle in handles:
            handle.close()
    ok = len(steps) == len(plan) and all(item["ok"] for item in steps)
    return {"ok": ok, "build": built, "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="打包版 RPA Worker 的端到端測試")
    parser.add_argument("app", type=Path)
    parser.add_argument("--installer", type=Path, help="先安裝、最後升級與解除安裝（Windows）")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    installer = cast("Path | None", args.installer)
    # Windows 上剛結束的程序可能還鎖著檔案：清不掉暫存資料夾不影響結果
    with tempfile.TemporaryDirectory(prefix="rpa-e2e-", ignore_cleanup_errors=True) as folder:
        summary = run(args.app.resolve(), Path(folder), installer.resolve() if installer else None)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
