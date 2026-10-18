"""M10.2 錄製端：登記與邀請、對外埠上的 Portal、Client API 的指令通道與互動子程序。不需要瀏覽器。

管理 API 打到管理頁面的埠；錄製端的請求打到對外埠（base_url 帶 :8081）並帶錄製端的權杖。
這裡的測試自己扮演錄製端（上線、輪詢、傳回檔案與輸出）；真的 HTTP 與 rpa_worker.recorder
在 test_recorder_flow.py。
"""

import io
import json
import threading
import time
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_server.config import Settings
from rpa_server.context import Via, use_recorder
from rpa_server.devices import LOST_EXIT
from rpa_server.processes import child_env
from rpa_server.services import Services
from rpa_worker.environment import PROTOCOL
from rpa_worker.interactive import INPUTS, WORK, b64decode
from rpa_worker.pairing import CLIENT_API_PREFIX, parse_invite

JsonObject = dict[str, object]
WORKER_PORT = 8081
API = CLIENT_API_PREFIX
INFO: JsonObject = {
    "protocol": PROTOCOL,
    "fingerprint": "f",
    "version": "0.3.0",
    "os": "macOS 15",
    "host": "amy-mac",
    "browsers": ["chromium", "firefox"],
    "display": True,
}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT, worker_host="192.168.1.10")


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    """打到對外埠的用戶端（伺服器已經由 client 啟動）。"""
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json() if response.content else {}
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wait_until(check: Callable[[], bool], timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "逾時"
        time.sleep(0.05)


@dataclass
class Device:
    """扮演錄製端：上線、取得指令、傳回檔案與輸出。"""

    remote: Client
    token: str
    after: int = 0

    def hello(self, boot: str = "boot-1", **info: object) -> JsonObject:
        payload = {**INFO, "boot": boot, **info}
        return body(self.remote.post(f"{API}/hello", json=payload, headers=auth(self.token)))

    def commands(self) -> list[JsonObject]:
        reply = body(
            self.remote.post(
                f"{API}/control", json={"after": self.after, "wait": 0}, headers=auth(self.token)
            )
        )
        items = cast("list[JsonObject]", reply["commands"])
        if items:
            self.after = cast("int", items[-1]["seq"])
        return items

    def collect(
        self, until: Callable[[list[JsonObject]], bool], timeout: float = 10
    ) -> list[JsonObject]:
        """一直取指令，直到 ``until`` 滿足；回傳這段期間收到的全部指令。"""
        seen: list[JsonObject] = []
        deadline = time.monotonic() + timeout
        while not until(seen):
            assert time.monotonic() < deadline, f"逾時；指令：{seen}"
            seen.extend(self.commands())
            time.sleep(0.02)
        return seen

    def files(self, process: str, files: Mapping[str, bytes], status: int = 204) -> Response:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        response = self.remote.put(
            f"{API}/processes/{process}/files",
            content=buffer.getvalue(),
            headers={**auth(self.token), "Content-Type": "application/zip"},
        )
        assert response.status_code == status, response.text
        return response

    def output(
        self, process: str, lines: list[str], exit_code: int | None = None, status: int = 204
    ) -> Response:
        payload: JsonObject = {"lines": lines}
        if exit_code is not None:
            payload["exit"] = exit_code
        response = self.remote.post(
            f"{API}/processes/{process}/output", json=payload, headers=auth(self.token)
        )
        assert response.status_code == status, response.text
        return response


def paired(client: Client, remote: Client, recorder_id: str = "mac-01") -> Device:
    """登記一台錄製端、用邀請配對；回傳它的權杖。"""
    created = body(
        client.post("/api/recorders", json={"id": recorder_id, "name": "Amy <Mac>"}), 201
    )
    assert cast("JsonObject", created["recorder"])["kind"] == "recorder"
    invited = cast(
        "JsonObject", body(client.post(f"/api/recorders/{recorder_id}/invite"))["invite"]
    )
    invite = parse_invite(str(invited["line"]))
    assert invite.app == "recorder"
    assert invite.server == "http://192.168.1.10:8081"
    reply = body(remote.post(f"{API}/pair", json={"code": invite.code, "app": "recorder"}))
    assert reply["device"] == recorder_id
    return Device(remote, str(reply["token"]))


# ---------------------------------------------------------------- 登記、邀請、配對


def test_recorders_are_registered_invited_and_paired(client: Client, remote: Client) -> None:
    body(client.post("/api/workers", json={"id": "win-01"}), 201)
    # 代號和 worker 共用：兩邊都不能重複
    assert error(client.post("/api/recorders", json={"id": "win-01"}), 409)["code"] == (
        "worker_exists"
    )
    body(client.post("/api/recorders", json={"id": "mac-01", "name": "Mac"}), 201)
    assert error(client.post("/api/workers", json={"id": "mac-01"}), 409)["code"] == (
        "worker_exists"
    )
    invited = cast("JsonObject", body(client.post("/api/recorders/mac-01/invite"))["invite"])
    code = parse_invite(str(invited["line"])).code
    # 邀請的 App 種類不對：代碼保留
    wrong = error(remote.post(f"{API}/pair", json={"code": code, "app": "worker"}), 409)
    assert wrong["code"] == "invite_wrong_app"
    token = str(body(remote.post(f"{API}/pair", json={"code": code, "app": "recorder"}))["token"])
    assert error(remote.post(f"{API}/pair", json={"code": code, "app": "recorder"}), 401)
    # worker 的 API 不認錄製端的權杖
    assert remote.post("/worker-api/v1/hello", json=INFO, headers=auth(token)).status_code == 401

    listed = cast("list[JsonObject]", body(client.get("/api/recorders"))["recorders"])
    assert [(item["id"], item["status"]) for item in listed] == [("mac-01", "offline")]
    body(client.patch("/api/recorders/mac-01", json={"name": "Amy 的 Mac"}))
    assert body(client.get("/api/recorders/mac-01"))["name"] == "Amy 的 Mac"
    page = client.get("/devices").text
    assert 'id="recorder-mac-01"' in page
    assert "Amy 的 Mac" in page
    body(client.delete("/api/recorders/mac-01"))
    assert error(client.get("/api/recorders/mac-01"), 404)["code"] == "recorder_not_found"
    assert remote.post(f"{API}/hello", json=INFO, headers=auth(token)).status_code == 401


def test_portal_on_the_external_port_needs_a_recorder_token(client: Client, remote: Client) -> None:
    worker = str(body(client.post("/api/workers", json={"id": "win-01"}), 201)["token"])
    device = paired(client, remote)
    assert remote.get("/scenes", follow_redirects=False).status_code == 401
    assert remote.get("/devices", headers=auth(worker)).status_code == 401
    assert remote.get("/static/portal.css", headers=auth("nope")).status_code == 401
    page = remote.get("/devices", headers=auth(device.token))
    assert page.status_code == 200
    assert 'id="via-recorder"' in page.text
    assert "透過錄製端「Amy &lt;Mac&gt;」" in page.text
    assert remote.get("/static/portal.css", headers=auth(device.token)).status_code == 200
    listed = body(remote.get("/api/recorders", headers=auth(device.token)))
    assert listed["recorders"]
    # 從伺服器本機（8080）看：沒有錄製端的標示
    assert 'id="via-recorder"' not in client.get("/devices").text
    # 停用、重新邀請後舊權杖失效
    body(client.patch("/api/recorders/mac-01", json={"disabled": True}))
    assert remote.get("/devices", headers=auth(device.token)).status_code == 401
    body(client.patch("/api/recorders/mac-01", json={"disabled": False}))
    assert remote.get("/devices", headers=auth(device.token)).status_code == 200
    body(client.post("/api/recorders/mac-01/invite"))
    assert remote.get("/devices", headers=auth(device.token)).status_code == 401


# ---------------------------------------------------------------- 指令通道


def test_hello_and_control(app: FastAPI, client: Client, remote: Client) -> None:
    device = paired(client, remote)
    # 還沒上線就輪詢：要先 hello
    refused = remote.post(f"{API}/control", json={"wait": 0}, headers=auth(device.token))
    assert error(refused, 409)["code"] == "recorder_hello_first"
    mismatch = remote.post(
        f"{API}/hello", json={**INFO, "protocol": 99}, headers=auth(device.token)
    )
    problem = error(mismatch, 409)
    assert problem["code"] == "protocol_mismatch"
    assert "錄製端的協定版本 99" in str(problem["message"])
    reply = device.hello()
    assert reply["device"] == "mac-01"
    assert reply["seq"] == 0
    channel = reply["channel"]
    assert isinstance(channel, str)
    assert device.hello()["channel"] == channel  # 同一次啟動：同一個通道
    # 錄製端以為還是上一個通道（序號比這邊發過的大）：要它重新 hello
    stale = remote.post(f"{API}/control", json={"after": 5, "wait": 0}, headers=auth(device.token))
    assert error(stale, 409)["code"] == "recorder_hello_first"
    assert reply["protocol"] == PROTOCOL
    assert reply["sameVersion"] is False  # 指紋 f 和管理 Portal 不同
    assert device.commands() == []
    record = body(client.get("/api/recorders/mac-01"))
    assert record["status"] == "online"
    assert record["browsers"] == ["chromium", "firefox"]
    assert record["version"] == "0.3.0"
    # 指令依序號，確認後才丟掉
    hub = services(app).recorders
    hub.enqueue("mac-01", {"type": "kill", "process": "x"})
    first = body(
        remote.post(f"{API}/control", json={"after": 0, "wait": 0}, headers=auth(device.token))
    )
    again = body(
        remote.post(f"{API}/control", json={"after": 0, "wait": 0}, headers=auth(device.token))
    )
    assert first["commands"] == again["commands"]  # 回應沒收到也不會漏
    seq = cast("list[JsonObject]", first["commands"])[0]["seq"]
    done = body(
        remote.post(f"{API}/control", json={"after": seq, "wait": 0}, headers=auth(device.token))
    )
    assert done["commands"] == []


# ---------------------------------------------------------------- 互動子程序


def start_debug(remote: Client, device: Device, **options: object) -> JsonObject:
    return body(
        remote.post("/api/scenes/ba-001/debug", json=options, headers=auth(device.token)), 202
    )


def test_debug_session_runs_on_the_recorder(app: FastAPI, client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    # 錄製端沒有連線：說明，不啟動
    offline = remote.post("/api/scenes/ba-001/debug", json={}, headers=auth(device.token))
    assert error(offline, 409)["code"] == "recorder_offline"
    # BA-001 用 Firefox：這台只下載了 Chromium 時說明，不啟動
    device.hello(browsers=["chromium"])
    missing = remote.post("/api/scenes/ba-001/debug", json={}, headers=auth(device.token))
    assert error(missing, 422)["code"] == "recorder_browser_missing"
    assert device.commands() == []
    device.hello()  # 同一個開機代號：只是更新資訊
    session = start_debug(remote, device)
    assert session["deviceId"] == "mac-01"
    assert session["headless"] is False  # 錄製端有桌面：預設有頭模式，視窗開在那台
    (start,) = device.commands()
    assert start["type"] == "start"
    assert start["module"] == "rpa_runner.debug"
    args = cast("list[str]", start["args"])
    assert args[args.index("--scenario") + 1] == f"{WORK}/scenario.yaml"
    assert args[args.index("--out") + 1] == WORK
    assert "--headed" in args
    files = cast("dict[str, str]", start["files"])
    assert set(files) == {"scenario.yaml", "input.json"}
    assert b"ba-001" in b64decode(files["scenario.yaml"])
    env = cast("dict[str, str]", start["env"])
    assert env["RPA_LANG"] == "zh-Hant"
    assert "PATH" not in env  # 只送這次另外給的變數，不送伺服器自己的環境
    assert start["log"] == "debug.log"
    process = str(start["process"])
    assert body(client.get("/api/recorders/mac-01"))["status"] == "busy"

    # 錄製端：先傳截圖，再送 ready
    device.files(process, {"shot-0.png": b"\x89PNG", "debug.log": b"started\n"})
    device.output(process, [json.dumps({"event": "ready"})])
    session_id = str(session["id"])
    wait_until(lambda: body(client.get(f"/api/debug/{session_id}"))["status"] == "ready")
    folder = services(app).storage.debug_dir(session_id)
    assert (folder / "shot-0.png").read_bytes() == b"\x89PNG"

    # 結束：送 close 命令、關標準輸入，錄製端回報結束碼
    closing = threading.Thread(target=lambda: client.delete(f"/api/debug/{session_id}"))
    closing.start()
    seen = device.collect(lambda items: any(item["type"] == "close" for item in items))
    assert seen[0] == {"seq": seen[0]["seq"], "type": "input", "line": '{"cmd": "close"}',
                       "process": process}  # fmt: skip
    device.output(process, [], exit_code=0)
    closing.join(10)
    assert not closing.is_alive()
    assert error(device.output(process, ["late"], status=404), 404)["code"] == "process_not_found"
    assert body(client.get("/api/recorders/mac-01"))["status"] == "online"
    assert not folder.exists()


def test_unsafe_files_are_refused(client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    device.hello()
    start_debug(remote, device)
    (start,) = device.commands()
    process = str(start["process"])
    refused = device.files(process, {"../escape.txt": b"x"}, status=422)
    assert error(refused, 422)["code"] == "files_invalid"
    refused = device.files(process, {f"{INPUTS}/state.json": b"{}"}, status=422)
    assert error(refused, 422)["code"] == "files_invalid"
    # 別台錄製端不能動這個子程序
    other = paired(client, remote, "mac-02")
    other.hello()
    assert other.output(process, ["x"], status=404).status_code == 404


def test_lost_and_restarted_recorders_end_their_processes(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    device.hello(boot="boot-1")
    first = start_debug(remote, device)
    hub = services(app).recorders
    # 錄製端重新啟動（啟動代號不同）：舊的子程序結束
    device.hello(boot="boot-2")
    wait_until(lambda: body(client.get(f"/api/debug/{first['id']}"))["status"] == "failed")
    log = services(app).storage.debug_dir(str(first["id"])) / "debug.log"
    assert "重新啟動" in log.read_text(encoding="utf-8")

    second = start_debug(remote, device, restart=True)
    hub.lost_seconds = 0
    time.sleep(0.01)
    assert hub.reap() == 1
    wait_until(lambda: body(client.get(f"/api/debug/{second['id']}"))["status"] == "failed")
    log = services(app).storage.debug_dir(str(second["id"])) / "debug.log"
    assert "失聯" in log.read_text(encoding="utf-8")
    assert body(client.get("/api/recorders/mac-01"))["status"] == "offline"


def test_remote_process_translates_paths(
    app: FastAPI, client: Client, remote: Client, tmp_path: Path
) -> None:
    device = paired(client, remote)
    device.hello()
    hub = services(app).recorders
    work = tmp_path / "work"
    work.mkdir()
    (work / "base.yaml").write_text("steps: []", encoding="utf-8")
    state = tmp_path / "roles" / "clerk" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"cookies": []}', encoding="utf-8")
    command = [
        "/usr/bin/python3",
        "-m",
        "rpa_runner.record",
        "--scenario",
        str(work / "base.yaml"),
        "--output",
        str(work / ".recording.py"),
        "--storage-state",
        str(state),
        "--engine",
        "chromium",
    ]
    env = child_env(
        "en", {"RPA_SECRET_X": str(state), "RPA_STORAGE_STATE": str(state)}
    )  # Secrets 的值剛好是伺服器上的路徑：原樣送出
    process = hub.start("mac-01", command, env=env, log=work / "codegen.log", cwd=work, pipes=False)
    assert process.stdin is None
    assert process.stdout is None
    (start,) = device.commands()
    assert start["args"] == [
        "--scenario", f"{WORK}/base.yaml", "--output", f"{WORK}/.recording.py",
        "--storage-state", f"{WORK}/{INPUTS}/0-state.json", "--engine", "chromium",
    ]  # fmt: skip
    assert cast("dict[str, str]", start["env"]) == {
        "PYTHONIOENCODING": "utf-8",
        "RPA_LANG": "en",
        "RPA_SECRET_X": str(state),
        "RPA_STORAGE_STATE": f"{WORK}/{INPUTS}/0-state.json",
    }
    assert set(cast("dict[str, str]", start["files"])) == {"base.yaml", f"{INPUTS}/0-state.json"}
    assert start["pipes"] is False
    # 結束前先傳回錄製稿
    device.files(str(start["process"]), {".recording.py": b"page.goto('x')", "codegen.log": b"ok"})
    device.output(str(start["process"]), [], exit_code=0)
    assert process.wait(timeout=5) == 0
    assert (work / ".recording.py").read_text(encoding="utf-8") == "page.goto('x')"
    # 已經結束：再傳也不收
    device.files(str(start["process"]), {"x.txt": b"x"}, status=404)
    # 伺服器自己的環境不送：一定要用 child_env()
    with pytest.raises(TypeError, match="child_env"):
        hub.start("mac-01", command, env={"PATH": "/bin"}, log=work / "codegen.log", cwd=work)


def test_stop_asks_the_recorder_to_kill(
    app: FastAPI, client: Client, remote: Client, tmp_path: Path
) -> None:
    from rpa_server.processes import send, stop

    device = paired(client, remote)
    device.hello()
    hub = services(app).recorders
    work = tmp_path / "debug"
    work.mkdir()
    process = hub.start(
        "mac-01", ["/py", "-m", "rpa_runner.debug"], env=child_env("en"), log=work / "debug.log"
    )
    assert send(process, "step 3")
    (start, line) = device.commands()
    assert line == {
        "seq": line["seq"],
        "type": "input",
        "line": "step 3",
        "process": start["process"],
    }
    stopping = threading.Thread(target=lambda: stop(process, grace=0.1))
    stopping.start()  # 等不到結束：請錄製端結束整個程序樹
    seen = device.collect(lambda items: any(item["type"] == "kill" for item in items))
    assert [item["type"] for item in seen] == ["close", "kill"]
    assert process.poll() is None  # 錄製端回報之前還在
    device.output(str(start["process"]), [], exit_code=-9)
    stopping.join(10)
    assert process.wait(timeout=5) == -9
    assert not send(process, "step 4")


def test_lost_exit_code_and_requests_without_recorder() -> None:
    assert LOST_EXIT < 0
    with use_recorder(Via("mac-01", "Mac")):
        from rpa_server.context import via_recorder

        assert via_recorder() == Via("mac-01", "Mac")


def test_processes_the_recorder_does_not_have_are_ended(
    app: FastAPI, client: Client, remote: Client
) -> None:
    """錄製端確認收到「啟動」，正在執行的清單裡卻沒有它（啟動失敗沒回報到）：視為結束。"""
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    device.hello()
    session = start_debug(remote, device)
    (start,) = device.commands()
    process = str(start["process"])
    # 還沒確認收到「啟動」時，不在清單裡也不算
    early = {"after": 0, "wait": 0, "running": []}
    assert body(remote.post(f"{API}/control", json=early, headers=auth(device.token)))["commands"]
    assert body(client.get(f"/api/debug/{session['id']}"))["status"] == "starting"
    # 確認收到、而且還在執行
    running = {"after": device.after, "wait": 0, "running": [process]}
    body(remote.post(f"{API}/control", json=running, headers=auth(device.token)))
    assert body(client.get(f"/api/debug/{session['id']}"))["status"] == "starting"
    # 確認收到、但錄製端沒有這個子程序
    gone = {"after": device.after, "wait": 0, "running": []}
    reply = body(remote.post(f"{API}/control", json=gone, headers=auth(device.token)))
    kills = cast("list[JsonObject]", reply["commands"])
    assert [(item["type"], item["process"]) for item in kills] == [("kill", process)]
    wait_until(lambda: body(client.get(f"/api/debug/{session['id']}"))["status"] == "failed")
    log = services(app).storage.debug_dir(str(session["id"])) / "debug.log"
    assert "那邊沒有這個子程序" in log.read_text(encoding="utf-8")
