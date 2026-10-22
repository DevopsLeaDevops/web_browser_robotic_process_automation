"""M10.2 錄製端：登記與邀請、對外埠上的 Portal、Client API 的指令通道與互動子程序。不需要瀏覽器。

管理 API 打到管理頁面的埠；錄製端的請求打到對外埠（base_url 帶 :8081）並帶錄製端的權杖。
這裡的測試自己扮演錄製端（上線、輪詢、傳回檔案與輸出）；真的 HTTP 與 rpa_worker.recorder
在 test_recorder_flow.py。
"""

import io
import json
import os
import re
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

from rpa_core.dsl import dynamic
from rpa_server.config import Settings
from rpa_server.context import Via, use_recorder
from rpa_server.devices import LOST_EXIT
from rpa_server.errors import ServiceError
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


def test_recorders_hide_cluster_and_admin_menus(client: Client, remote: Client) -> None:
    """三段分工：伺服器本機五個第一級選單都在；錄製端預設不顯示叢集管理與管理後台，
    裝置頁替那台打開後才顯示。只是選單，不是權限。"""
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    device = paired(client, remote)
    headers = auth(device.token)

    def top(via: Client, headers: dict[str, str] | None = None) -> list[str]:
        html = via.get("/domains/lab", headers=headers).text
        return re.findall(r'href="([^"]+)"', html.split('id="topnav"')[1].split("</nav>")[0])

    everything = ["/scenes", "/recording", "/runs", "/devices", "/domains"]
    assert top(client) == everything
    assert top(remote, headers=headers) == ["/scenes", "/recording", "/runs"]
    assert 'href="/domains"' not in remote.get("/domains/lab", headers=headers).text
    assert remote.get("/devices", headers=headers).status_code == 200
    assert body(client.get("/api/recorders/mac-01"))["menus"] == []

    # 依 RECORDER_MENUS 的順序存，重複的只留一個
    menus = body(
        client.patch("/api/recorders/mac-01", json={"menus": ["admin", "cluster", "admin"]})
    )
    assert menus["menus"] == ["cluster", "admin"]
    assert top(remote, headers=headers) == everything
    body(client.patch("/api/recorders/mac-01", json={"menus": ["cluster"]}))
    assert top(remote, headers=headers) == ["/scenes", "/recording", "/runs", "/devices"]
    bad = error(client.patch("/api/recorders/mac-01", json={"menus": ["produce"]}), 422)
    assert bad["code"] == "recorder_menu_invalid"
    assert body(client.get("/api/recorders/mac-01"))["menus"] == ["cluster"]
    # 改名稱、停用不動到選單
    body(client.patch("/api/recorders/mac-01", json={"name": "Amy 的 Mac"}))
    assert body(client.get("/api/recorders/mac-01"))["menus"] == ["cluster"]
    page = client.get("/devices").text
    assert 'data-recorder-menus="mac-01"' in page
    assert 'value="cluster" checked' in page
    assert 'value="admin">' in page


def test_pages_follow_the_recorder_display(client: Client, remote: Client) -> None:
    """伺服器沒有畫面（Linux）時，透過有桌面的錄製端照樣可以錄製、人工登入、有頭調試。"""
    body(client.post("/api/scenes/import"))
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    device = paired(client, remote)
    device.hello()
    headers = auth(device.token)
    # 伺服器這台（測試的設定沒有畫面）：不能錄製、不能人工登入
    assert body(client.get("/api/recordings"))["display"] is False
    assert "執行 Portal 的這台電腦沒有圖形介面" in client.get("/recording").text
    assert 'data-display="false"' in client.get("/roles").text
    # 透過錄製端：看錄製端回報的，用詞也指錄製端
    assert body(remote.get("/api/recordings", headers=headers))["display"] is True
    assert body(remote.get("/api/roles", headers=headers))["display"] is True
    page = remote.get("/recording", headers=headers).text
    assert 'data-display="true"' in page
    assert "沒有圖形介面" not in page
    assert 'data-for="record" disabled' not in page
    assert "錄製端這台會開啟瀏覽器" in page
    roles = remote.get("/roles", headers=headers).text
    assert 'data-display="true"' in roles
    assert "登入狀態傳回伺服器" in roles
    assert "值只存在伺服器" in roles
    started_text = "已開始錄製：請在錄製端這台操作瀏覽器"  # 頁面腳本的訊息也換掉（tojson 會跳脫）
    assert started_text in page or json.dumps(started_text)[1:-1] in page
    debug = remote.get("/scenes/ba-001/debug", headers=headers).text
    assert "有頭模式會在錄製端這台打開瀏覽器視窗" in debug
    assert 'name="headless" value="0" checked' in debug

    # 錄製端這台在錄製：只有它的頁面顯示錄製中，伺服器這台的不受影響
    started = body(
        remote.post(
            "/api/recordings",
            json={
                "target": {"sceneId": "rec-001", "new": True, "name": "錄製", "domainId": "lab"},
                "url": "http://127.0.0.1:8765/",
            },
            headers=headers,
        ),
        202,
    )
    assert started["deviceId"] == "mac-01"
    busy = remote.get("/recording", headers=headers).text
    assert f'data-poll="{started["id"]}"' in busy
    assert "開在錄製端這台" in busy
    assert 'data-for="record" disabled' in busy
    assert "data-poll=" not in client.get("/recording").text
    # 錄製端回報沒有畫面：照樣說明，不能錄製
    device.hello(display=False)
    assert "這台錄製端沒有圖形介面" in remote.get("/roles", headers=headers).text
    (start,) = [item for item in device.commands() if item["type"] == "start"]
    assert start["module"] == "playwright"
    device.output(str(start["process"]), [], exit_code=1)  # 關掉視窗前就結束：不留到測試收尾
    recording = f"/api/recordings/{started['id']}"
    wait_until(lambda: body(client.get(recording))["status"] != "recording")


def test_the_server_address_is_not_a_start_url(client: Client, remote: Client) -> None:
    """2026-10-19 的人工驗收：起始網址填了伺服器的對外埠，錄製的瀏覽器只得到 401。"""
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    device = paired(client, remote)
    device.hello()
    headers = auth(device.token)
    target = {"sceneId": "rec-001", "new": True, "name": "錄製", "domainId": "lab"}
    # 透過錄製端時，閘道轉送的 Host 是錄製端連的伺服器網址（這裡是 testserver:8081）
    for url in (f"http://testserver:{WORKER_PORT}/", f"http://TESTSERVER:{WORKER_PORT}/scenes"):
        refused = remote.post(
            "/api/recordings", json={"target": target, "url": url}, headers=headers
        )
        problem = error(refused, 422)
        assert problem["code"] == "recording_url_portal"
        assert "錄製開的瀏覽器沒有權杖" in str(problem["message"])
    assert body(client.get("/api/recordings"))["recordings"] == []
    assert [item for item in device.commands() if item["type"] == "start"] == []


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


IFRAME_EXAMPLE = Path(__file__).resolve().parents[3] / "scenarios" / "examples" / "iframe-form.yaml"


def create_scene(client: Client, scene_id: str, text: str) -> None:
    """建立場景，並把 v2 存成指定的內容。"""
    body(client.post("/api/scenes", json={"id": scene_id, "name": "暫名"}), 201)
    files = {"scenario.yaml": text}
    url = f"/api/scenes/{scene_id}/revisions"
    body(client.post(url, json={"baseRevision": 1, "files": files}), 201)


def test_outdated_recorder_is_told_to_update_for_iframes(
    app: FastAPI, client: Client, remote: Client
) -> None:
    """M7a：場景用到 iframe 的 frame。M7a 之前的錄製端 App 沒有回報 features，
    交給它只會得到「場景校驗失敗」，所以伺服器先擋下並說明要更新 App。"""
    create_scene(client, "iframe-form", IFRAME_EXAMPLE.read_text(encoding="utf-8"))
    device = paired(client, remote)
    device.hello()  # 舊 App：INFO 沒有 features
    refused = remote.post("/api/scenes/iframe-form/debug", json={}, headers=auth(device.token))
    problem = error(refused, 422)
    assert problem["code"] == "recorder_outdated"
    assert "Amy <Mac>" in str(problem["message"])
    assert "frame" in str(problem["message"])
    assert device.commands() == []  # 沒有交給錄製端
    # 不用 iframe 的場景照舊交給它（見 test_debug_session_runs_on_the_recorder）；
    # 新的 App 回報看得懂 frame、anyFrame：檢查通過
    hub = services(app).recorders
    via = Via("mac-01", "Amy <Mac>")
    with pytest.raises(ServiceError):
        hub.check(via, features={"frame"})
    device.hello(features=["anyFrame", "frame"])
    hub.check(via, engine="chromium", features={"frame", "anyFrame"})
    with pytest.raises(ServiceError):
        hub.check(via, features={"somethingNew"})


def test_dynamic_debug_inputs_are_evaluated_and_returned_by_the_recorder(
    app: FastAPI, client: Client, remote: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("伺服器不應替錄製端求值")

    monkeypatch.setattr("rpa_runner.contract.evaluate", forbidden)
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    device.hello()
    options = {"inputs": {"title": "{{today}}", "quantity": "{{random:7:7}}"}}
    refused = remote.post("/api/scenes/ba-001/debug", json=options, headers=auth(device.token))
    assert error(refused, 422)["code"] == "recorder_outdated"
    assert device.commands() == []
    device.hello(features=["dynamicValues"])
    session = start_debug(remote, device, **options)
    (start,) = device.commands()
    files = cast("dict[str, str]", start["files"])
    assert json.loads(b64decode(files["input.json"])) == options["inputs"]
    process = str(start["process"])
    # 裝置的日期故意與伺服器不同：Portal 必須顯示裝置實際用到的值。
    resolved = {"title": "2035-01-02", "quantity": 7}
    device.output(process, [json.dumps({"event": "ready", "inputs": resolved})])
    session_id = str(session["id"])
    wait_until(lambda: body(client.get(f"/api/debug/{session_id}"))["status"] == "ready")
    assert body(client.get(f"/api/debug/{session_id}"))["inputs"] == resolved
    path = services(app).storage.debug_dir(session_id) / "input.json"
    assert json.loads(path.read_text(encoding="utf-8")) == resolved
    device.output(process, [], exit_code=0)


def test_continue_recording_sends_dynamic_defaults_without_server_evaluation(
    app: FastAPI, client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("伺服器不應替接著錄製的子程序求值")

    monkeypatch.setattr(dynamic, "_local_now", forbidden)
    monkeypatch.setattr("rpa_runner.contract.evaluate", forbidden)
    create_scene(
        client,
        "dynamic-replay",
        """schemaVersion: 1
id: dynamic-replay
name: 接著錄製
inputs:
  title: {default: '{{today}}'}
steps:
  - {id: open, action: goto, url: https://example.test/}
""",
    )
    replay = services(app).recordings._replay("dynamic-replay")  # pyright: ignore[reportPrivateUsage]
    assert replay.inputs == {"title": "{{today}}"}


# ---------------------------------------------------------------- 登入檢查交給錄製端

ROLE: JsonObject = {
    "id": "erp-clerk",
    "name": "ERP 職員",
    "loginUrl": "http://127.0.0.1:9/login",
    "checkUrl": "http://127.0.0.1:9/home",
    "check": "{ testId: current-user }",
    "engine": "firefox",
}
OLD_STATE = b'{"cookies": [], "origins": []}'
NEW_STATE = (
    b'{"cookies": [{"name": "s", "value": "new", "domain": "x", "path": "/"}], "origins": []}'
)


def start_role_check(app: FastAPI, client: Client, remote: Client) -> tuple[Device, JsonObject]:
    """伺服器沒有下載瀏覽器：透過錄製端按「檢查」，檢查交給錄製端（無頭）。"""
    body(client.post("/api/roles", json=ROLE), 201)
    services(app).roles.local_engines = lambda: ()
    state = services(app).storage.role_state("erp-clerk")
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_bytes(OLD_STATE)
    device = paired(client, remote)
    device.hello(display=False)  # 無頭檢查：錄製端沒有畫面也可以
    started = body(remote.post("/api/roles/erp-clerk/check", headers=auth(device.token)), 202)
    assert started["activity"] == "checking"
    # 子程序在背景的檢查執行緒啟動：等到「啟動」指令出現
    (start,) = device.collect(lambda items: any(item["type"] == "start" for item in items))
    return device, start


def role_when_idle(client: Client) -> JsonObject:
    deadline = time.monotonic() + 10
    while True:
        role = body(client.get("/api/roles/erp-clerk"))
        if not role["activity"]:
            return role
        assert time.monotonic() < deadline, role
        time.sleep(0.05)


def test_role_check_runs_on_the_recorder(app: FastAPI, client: Client, remote: Client) -> None:
    device, start = start_role_check(app, client, remote)
    assert start["module"] == "rpa_runner.login"
    args = cast("list[str]", start["args"])
    assert args[:3] == ["check", "--out", WORK]
    assert args[args.index("--engine") + 1] == "firefox"
    assert args[args.index("--state") + 1] == f"{WORK}/state.json"
    assert "--headed" not in args
    files = cast("dict[str, str]", start["files"])
    assert b64decode(files["state.json"]) == OLD_STATE  # 送過去的是角色登入狀態的複本
    env = cast("dict[str, str]", start["env"])
    assert json.loads(env["RPA_LOGIN"])["role"] == "erp-clerk"
    assert start["log"] == "login.log"

    # 錄製端：檢查通過，寫回換發過的登入狀態
    process = str(start["process"])
    result = {"role": "erp-clerk", "status": "passed", "refreshed": False, "url": None}
    device.files(process, {"login.json": json.dumps(result).encode(), "state.json": NEW_STATE})
    device.output(process, [], exit_code=0)
    role = role_when_idle(client)
    assert (role["status"], role["message"]) == ("logged_in", None)
    storage = services(app).storage
    assert storage.role_state("erp-clerk").read_bytes() == NEW_STATE
    assert not (storage.roles / "erp-clerk" / "check" / "state.json").exists()


def test_role_check_keeps_a_newer_state(app: FastAPI, client: Client, remote: Client) -> None:
    """檢查期間角色的登入狀態被別人更新（例如人工登入、執行時自動登入）：不拿檢查的複本蓋掉。"""
    device, start = start_role_check(app, client, remote)
    state = services(app).storage.role_state("erp-clerk")
    newer = (
        b'{"cookies": [{"name": "s", "value": "newer", "domain": "x", "path": "/"}], "origins": []}'
    )
    state.write_bytes(newer)
    later = time.time_ns() + 5_000_000_000
    os.utime(state, ns=(later, later))
    process = str(start["process"])
    result = {"role": "erp-clerk", "status": "passed", "refreshed": True, "url": None}
    device.files(process, {"login.json": json.dumps(result).encode(), "state.json": NEW_STATE})
    device.output(process, [], exit_code=0)
    assert role_when_idle(client)["status"] == "logged_in"
    assert state.read_bytes() == newer


def test_role_check_on_an_outdated_recorder(app: FastAPI, client: Client, remote: Client) -> None:
    device, start = start_role_check(app, client, remote)
    process = str(start["process"])
    usage = f"error: unrecognized arguments: --state {WORK}/state.json\n".encode()
    device.files(process, {"login.log": usage})
    device.output(process, [], exit_code=2)
    role = role_when_idle(client)
    assert role["status"] == "unknown"
    assert "這台錄製端的版本較舊" in str(role["message"])
    assert services(app).storage.role_state("erp-clerk").read_bytes() == OLD_STATE


def test_role_check_page_through_a_recorder(app: FastAPI, client: Client, remote: Client) -> None:
    """伺服器沒有瀏覽器：直接打開時「檢查」是灰的，透過錄製端打開時可以按。"""
    body(client.post("/api/roles", json=ROLE), 201)
    services(app).roles.local_engines = lambda: ()
    device = paired(client, remote)
    device.hello()
    assert 'data-action="check-role" data-role="erp-clerk" disabled>' in client.get("/roles").text
    page = remote.get("/roles", headers=auth(device.token)).text
    assert 'data-action="check-role" data-role="erp-clerk" title=' in page


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
    early: JsonObject = {"after": 0, "wait": 0, "running": []}
    assert body(remote.post(f"{API}/control", json=early, headers=auth(device.token)))["commands"]
    assert body(client.get(f"/api/debug/{session['id']}"))["status"] == "starting"
    # 確認收到、而且還在執行
    running: JsonObject = {"after": device.after, "wait": 0, "running": [process]}
    body(remote.post(f"{API}/control", json=running, headers=auth(device.token)))
    assert body(client.get(f"/api/debug/{session['id']}"))["status"] == "starting"
    # 確認收到、但錄製端沒有這個子程序
    gone: JsonObject = {"after": device.after, "wait": 0, "running": []}
    reply = body(remote.post(f"{API}/control", json=gone, headers=auth(device.token)))
    kills = cast("list[JsonObject]", reply["commands"])
    assert [(item["type"], item["process"]) for item in kills] == [("kill", process)]
    wait_until(lambda: body(client.get(f"/api/debug/{session['id']}"))["status"] == "failed")
    log = services(app).storage.debug_dir(str(session["id"])) / "debug.log"
    assert "那邊沒有這個子程序" in log.read_text(encoding="utf-8")
