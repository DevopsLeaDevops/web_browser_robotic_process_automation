"""M14 對外 Agent API（/agent-api/v1）：金鑰、權限範圍、領域與錄製端的限制、限額、冪等鍵、稽核，
以及在錄製端調試（讀頁面結構）。不需要瀏覽器：錄製端由測試扮演（同 test_recorder_api.py）。

管理 API 打到管理頁面的埠；Agent 的請求打到對外埠（base_url 帶 :8081）並帶 API 金鑰。
"""

import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_server.config import Settings
from rpa_worker.environment import PROTOCOL
from rpa_worker.pairing import CLIENT_API_PREFIX, parse_invite

JsonObject = dict[str, object]
WORKER_PORT = 8081
AGENT = "/agent-api/v1"
INFO: JsonObject = {
    "protocol": PROTOCOL,
    "fingerprint": "f",
    "version": "0.6.0",
    "os": "macOS 15",
    "host": "agent-mac",
    "browsers": ["chromium", "firefox"],
    "display": True,
}
EVERYTHING = [
    "scenes:read",
    "scenes:write",
    "debug",
    "runs:validate",
    "scenes:publish",
    "runs:execute",
    "runs:read",
]


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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wait_until(check: Callable[[], bool], timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "逾時"
        time.sleep(0.05)


@dataclass
class Agent:
    """扮演 Agent 系統：每個請求帶自己的金鑰，路徑自動加上 /agent-api/v1。"""

    remote: Client
    key: str

    def get(self, path: str, **params: object) -> Response:
        return self.remote.get(AGENT + path, params=params, headers=auth(self.key))  # pyright: ignore[reportArgumentType]

    def post(self, path: str, payload: JsonObject | None = None) -> Response:
        return self.remote.post(AGENT + path, json=payload or {}, headers=auth(self.key))

    def put(self, path: str, payload: JsonObject) -> Response:
        return self.remote.put(AGENT + path, json=payload, headers=auth(self.key))

    def delete(self, path: str) -> Response:
        return self.remote.delete(AGENT + path, headers=auth(self.key))


def register(
    client: Client, remote: Client, agent_id: str = "agent-erp", **policy: object
) -> Agent:
    created = body(
        client.post("/api/agents", json={"id": agent_id, "name": "ERP 助理", "policy": policy}),
        201,
    )
    key = str(created["key"])
    assert key.startswith("rpa_ak_")
    assert cast("JsonObject", created["agent"])["keyPrefix"] == key[:11]
    return Agent(remote, key)


def policy(client: Client, agent_id: str = "agent-erp", **values: object) -> JsonObject:
    return body(client.patch(f"/api/agents/{agent_id}", json={"policy": values}))


def scene_yaml(scene_id: str, steps: str = "") -> str:
    return (
        f"schemaVersion: 1\nid: {scene_id}\nname: 建立訂單\n"
        "inputs:\n  customer: {type: string, default: 測試客戶}\n"
        "steps:\n  - {id: open, action: goto, url: 'https://erp.example.test/orders/new'}\n" + steps
    )


# ---------------------------------------------------------------- 金鑰與認證


def test_agent_api_needs_the_external_port_and_a_valid_key(client: Client, remote: Client) -> None:
    assert client.get(f"{AGENT}/meta").status_code == 404  # 管理頁面的埠沒有這組路徑
    assert error(remote.get(f"{AGENT}/meta"), 401)["code"] == "unauthorized"
    worker = str(body(client.post("/api/workers", json={"id": "win-01"}), 201)["token"])
    assert error(remote.get(f"{AGENT}/meta", headers=auth(worker)), 401)["code"] == "unauthorized"

    agent = register(client, remote)
    meta = body(agent.get("/meta"))
    assert meta["apiVersion"] == "1"
    assert meta["client"] == {"id": "agent-erp", "name": "ERP 助理"}
    assert meta["scopes"] == ["scenes:read", "runs:read"]
    assert meta["pageContent"] is False
    assert meta["limits"] == {"debugSessions": 2, "queuedRuns": 20}
    assert "frame" in cast("list[str]", meta["dslFeatures"])
    listed = cast("list[JsonObject]", body(client.get("/api/agents"))["agents"])
    assert [item["id"] for item in listed] == ["agent-erp"]
    assert "key" not in listed[0]
    assert listed[0]["lastUsedAt"] is not None

    # 停用、到期、不在允許的來源 IP：立刻失效
    body(client.patch("/api/agents/agent-erp", json={"disabled": True}))
    assert error(agent.get("/meta"), 401)["code"] == "unauthorized"
    body(client.patch("/api/agents/agent-erp", json={"disabled": False}))
    assert agent.get("/meta").status_code == 200
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    policy(client, expiresAt=past)
    assert agent.get("/meta").status_code == 401
    policy(client, allowedIps=["192.168.1.0/24"])  # 測試用戶端的位址不是這個網段
    assert agent.get("/meta").status_code == 401
    bad = error(client.patch("/api/agents/agent-erp", json={"policy": {"allowedIps": ["x"]}}), 422)
    assert bad["code"] == "agent_ip_invalid"
    policy(client)
    assert agent.get("/meta").status_code == 200

    # 重新產生金鑰：舊的立刻失效
    rotated = body(client.post("/api/agents/agent-erp/key"))
    assert agent.get("/meta").status_code == 401
    assert Agent(remote, str(rotated["key"])).get("/meta").status_code == 200
    body(client.delete("/api/agents/agent-erp"))
    assert Agent(remote, str(rotated["key"])).get("/meta").status_code == 401

    # 這組 API 自己的 OpenAPI：不需要金鑰
    schema = body(remote.get(f"{AGENT}/openapi.json"))
    assert "/scenes/{scene_id}/debug" in cast("JsonObject", schema["paths"])


def test_clients_are_validated(client: Client, remote: Client) -> None:
    register(client, remote)
    assert error(client.post("/api/agents", json={"id": "agent-erp"}), 409)["code"] == (
        "agent_exists"
    )
    assert error(client.post("/api/agents", json={"id": "Agent ERP"}), 422)["code"] == (
        "agent_id_invalid"
    )
    for values, code in (
        ({"scopes": ["scenes:delete"]}, "agent_scope_invalid"),
        ({"domains": ["nope"]}, "agent_domain_unknown"),
        ({"recorders": ["nope"]}, "agent_recorder_unknown"),
        ({"workers": ["nope"]}, "agent_worker_unknown"),
    ):
        assert (
            error(client.patch("/api/agents/agent-erp", json={"policy": values}), 422)["code"]
            == code
        )
    # 權限範圍依固定順序存，重複的只留一個；local 是伺服器本機
    saved = policy(client, scopes=["runs:read", "debug", "runs:read"], workers=["local"])
    assert saved["scopes"] == ["debug", "runs:read"]
    assert saved["workers"] == ["local"]


# ---------------------------------------------------------------- 場景與版本


def test_scenes_follow_scopes_domains_and_idempotency(client: Client, remote: Client) -> None:
    body(client.post("/api/domains", json={"id": "sales", "name": "業務"}), 201)
    body(client.post("/api/domains", json={"id": "hr", "name": "人資"}), 201)
    body(client.post("/api/scenes", json={"id": "hr-leave", "name": "請假", "domainId": "hr"}), 201)
    agent = register(client, remote, domains=["sales"])

    create: JsonObject = {"id": "order-create", "name": "建立訂單", "domainId": "sales"}
    missing = error(agent.post("/scenes", create), 403)
    assert missing["code"] == "scope_missing"
    assert missing["scopes"] == ["scenes:write"]
    policy(client, scopes=["scenes:read", "scenes:write"], domains=["sales"])
    other = error(agent.post("/scenes", {**create, "domainId": "hr"}), 403)
    assert other["code"] == "domain_forbidden"
    assert error(agent.post("/scenes", {"id": "x-1", "name": "x"}), 403)["code"] == (
        "domain_forbidden"  # 沒給領域：放進「未分類」，這把金鑰也不能用
    )
    keyed = {**create, "idempotencyKey": "order-create-1"}
    first = body(agent.post("/scenes", keyed), 201)
    assert body(agent.post("/scenes", keyed), 201) == first  # 逾時重送
    assert error(agent.post("/scenes", create), 409)["code"] == "scene_exists"
    scenes = cast("list[JsonObject]", body(agent.get("/scenes"))["scenes"])
    assert [scene["id"] for scene in scenes] == ["order-create"]
    assert error(agent.get("/scenes/hr-leave"), 403)["code"] == "domain_forbidden"
    detail = body(agent.get("/scenes/order-create"))
    revisions = cast("list[JsonObject]", detail["revisions"])
    assert revisions[0]["note"] == "由 Agent〈ERP 助理〉建立"
    assert detail["debug"] is None

    save: JsonObject = {
        "baseRevision": 1,
        "files": {"scenario.yaml": scene_yaml("order-create")},
        "note": "開頁面",
        "idempotencyKey": "order-create-r2",
    }
    saved = body(agent.post("/scenes/order-create/revisions", save), 201)
    assert saved["number"] == 2
    assert saved["note"] == "Agent〈ERP 助理〉：開頁面"
    assert body(agent.post("/scenes/order-create/revisions", save), 201) == saved
    stale = error(
        agent.post("/scenes/order-create/revisions", {**save, "idempotencyKey": None}), 409
    )
    assert stale["code"] == "stale_base"
    assert stale["latest"] == 2
    invalid = error(
        agent.post(
            "/scenes/order-create/revisions",
            {"baseRevision": 2, "files": {"scenario.yaml": "schemaVersion: 1\nid: order-create\n"}},
        ),
        422,
    )
    assert invalid["code"] == "revision_invalid"
    assert invalid["issues"]
    request = error(agent.post("/scenes/order-create/revisions", {"baseRevision": "x"}), 422)
    assert request["code"] == "request_invalid"
    assert request["problems"]

    revision = body(agent.get("/scenes/order-create/revisions/2"))
    assert "id: order-create" in cast("dict[str, str]", revision["files"])["scenario.yaml"]
    section = body(agent.get("/scenes/order-create/sections/steps"))
    assert str(section["text"]).startswith("steps:")
    steps = (
        str(section["text"])
        + "\n  - {id: name, action: fill, target: {label: 客戶}, value: '{{ inputs.customer }}'}"
    )
    third = body(
        agent.put("/scenes/order-create/sections/steps", {"baseRevision": 2, "text": steps}), 201
    )
    assert third["number"] == 3
    assert third["note"] == "Agent〈ERP 助理〉：編輯自動化腳本"
    contract = body(
        agent.put(
            "/scenes/order-create/contract",
            {
                "baseRevision": 3,
                "inputs": [
                    {"name": "customer", "previous": "customer", "type": "string"},
                    {"name": "quantity", "type": "integer", "default": 1},
                ],
            },
        ),
        201,
    )
    assert contract["number"] == 4
    assert str(contract["note"]).startswith("Agent〈ERP 助理〉：")

    checked = body(agent.post("/dsl/check", {"yaml": "schemaVersion: 1\nid: x\nsteps: 3\n"}))
    assert checked["ok"] is False
    assert cast("list[JsonObject]", checked["issues"])[0]["line"] is not None
    good = body(agent.post("/dsl/check", {"yaml": scene_yaml("x"), "sceneId": "order-create"}))
    assert good["ok"] is False  # id 和場景不同
    assert body(agent.post("/dsl/check", {"yaml": scene_yaml("x")}))["ok"] is True
    assert "properties" in body(agent.get("/dsl/schema"))
    domains = cast("list[JsonObject]", body(agent.get("/domains"))["domains"])
    assert [domain["id"] for domain in domains] == ["sales"]
    assert body(agent.get("/secrets")) == {"secrets": []}

    # 稽核：寫入請求都有一筆（包含被拒絕的），讀取不記
    audit = cast("list[JsonObject]", body(client.get("/api/agent-audit"))["audit"])
    actions = [(item["method"], item["action"], item["status"], item["code"]) for item in audit]
    assert ("POST", "/scenes", 403, "scope_missing") in actions
    assert ("POST", "/scenes", 201, None) in actions
    assert ("POST", "/scenes/{scene_id}/revisions", 409, "stale_base") in actions
    assert ("PUT", "/scenes/{scene_id}/sections/{key}", 201, None) in actions
    assert all(item["method"] != "GET" for item in audit)
    assert audit[0]["clientId"] == "agent-erp"
    section_audit = next(
        item for item in audit if item["method"] == "PUT" and "sections" in str(item["action"])
    )
    assert section_audit["target"] == "order-create/steps"
    only = body(client.get("/api/agent-audit", params={"client": "nobody"}))
    assert only == {"audit": []}


# ---------------------------------------------------------------- 驗證、發布、執行


def test_runs_follow_scopes_limits_and_placement(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/domains", json={"id": "sales", "name": "業務"}), 201)
    agent = register(client, remote, scopes=[*EVERYTHING[:4], "runs:read"], maxQueuedRuns=2)
    body(
        agent.post("/scenes", {"id": "order-create", "name": "建立訂單", "domainId": "sales"}), 201
    )
    body(
        agent.post(
            "/scenes/order-create/revisions",
            {"baseRevision": 1, "files": {"scenario.yaml": scene_yaml("order-create")}},
        ),
        201,
    )
    keyed: JsonObject = {"inputs": {"customer": "王小明"}, "idempotencyKey": "v2-1"}
    run = body(agent.post("/scenes/order-create/revisions/2/validate", keyed), 202)
    assert run["purpose"] == "validation"
    assert run["status"] == "queued"
    assert run["clientId"] == "agent-erp"
    assert (
        body(agent.post("/scenes/order-create/revisions/2/validate", keyed), 202)["id"] == run["id"]
    )
    # 另一個用戶端用同一個冪等鍵：不會拿到別人的運行
    body(client.post("/api/agents", json={"id": "agent-bi", "policy": {"scopes": EVERYTHING}}), 201)
    other = Agent(remote, str(body(client.post("/api/agents/agent-bi/key"))["key"]))
    other_run = body(other.post("/scenes/order-create/revisions/2/validate", keyed), 202)
    assert other_run["id"] != run["id"]
    invalid_inputs = error(
        agent.post("/scenes/order-create/revisions/2/validate", {"inputs": {"customer": 3}}), 422
    )
    assert invalid_inputs["code"] == "inputs_invalid"
    body(agent.post("/scenes/order-create/revisions/2/validate", {}), 202)
    limited = error(agent.post("/scenes/order-create/revisions/2/validate", {}), 429)
    assert limited["code"] == "limit_reached"
    assert limited["limit"] == 2
    # 冪等鍵用過時仍回傳那次運行，不受限額影響
    assert (
        body(agent.post("/scenes/order-create/revisions/2/validate", keyed), 202)["id"] == run["id"]
    )

    assert error(agent.post("/scenes/order-create/revisions/2/publish"), 403)["code"] == (
        "scope_missing"
    )
    assert error(agent.post("/scenes/order-create/runs", {}), 403)["code"] == "scope_missing"
    policy(client, scopes=EVERYTHING, maxQueuedRuns=20)
    assert error(agent.post("/scenes/order-create/runs", {}), 409)["code"] == "not_published"
    assert error(agent.post("/scenes/order-create/revisions/2/publish"), 409)["code"] == (
        "not_validated"
    )

    # 取消：只能取消自己觸發的
    cancelled = body(agent.post(f"/runs/{run['id']}/cancel"), 202)
    assert cancelled["status"] == "cancelled"
    assert error(agent.post(f"/runs/{other_run['id']}/cancel"), 403)["code"] == "run_forbidden"
    rerun = body(agent.post(f"/runs/{run['id']}/rerun", {"idempotencyKey": "again"}), 202)
    assert rerun["clientId"] == "agent-erp"
    assert rerun["revision"] == 2

    # 運行過程
    detail = body(agent.get(f"/runs/{run['id']}"))
    assert detail["status"] == "cancelled"
    assert detail["files"] == []  # 沒有開「回傳頁面內容」
    assert detail["reportUrl"] is None
    steps = body(agent.get(f"/runs/{run['id']}/steps"))
    assert steps["finished"] is True
    assert steps["steps"] == []
    shot = agent.get(f"/runs/{run['id']}/files/screenshot.png")
    assert error(shot, 403)["code"] == "content_disabled"
    mine = cast("list[JsonObject]", body(agent.get("/runs", mine="true"))["runs"])
    assert {item["clientId"] for item in mine} == {"agent-erp"}
    everyone = cast("list[JsonObject]", body(agent.get("/runs"))["runs"])
    assert len(everyone) == len(mine) + 1
    policy(client, scopes=EVERYTHING, domains=["sales"])
    assert len(cast("list[JsonObject]", body(agent.get("/runs"))["runs"])) == len(everyone)
    body(client.post("/api/domains", json={"id": "hr", "name": "人資"}), 201)
    policy(client, scopes=EVERYTHING, domains=["hr"])
    assert body(agent.get("/runs")) == {"runs": []}
    assert error(agent.get(f"/runs/{run['id']}"), 404)["code"] == "run_not_found"

    # 執行位置：固定了位置就不能指定別的；指定 Worker 要在清單裡
    body(client.post("/api/workers", json={"id": "win-01"}), 201)
    policy(client, scopes=EVERYTHING, target="local", workers=["local"])
    validate = "/scenes/order-create/revisions/2/validate"
    assert error(agent.post(validate, {"target": "remote"}), 403)["code"] == "target_forbidden"
    assert error(agent.post(validate, {"workerId": "win-01"}), 403)["code"] == "worker_forbidden"
    placed = body(agent.post(validate, {"workerId": "local"}), 202)
    assert placed["target"] == "local"
    policy(client, scopes=EVERYTHING)
    pinned = body(agent.post(validate, {"workerId": "win-01"}), 202)
    assert pinned["target"] == "remote"
    assert error(agent.post(validate, {"workerId": "win-01", "target": "local"}), 422)["code"] == (
        "worker_target_mismatch"
    )
    workers = body(agent.get("/workers"))
    assert [item["id"] for item in cast("list[JsonObject]", workers["workers"])] == [
        "local",
        "win-01",
    ]


# ---------------------------------------------------------------- 調試


@dataclass
class Device:
    """扮演錄製端：上線、取得指令、傳回輸出。"""

    remote: Client
    token: str
    after: int = 0

    def hello(self, **info: object) -> None:
        payload = {**INFO, "boot": "boot-1", **info}
        body(self.remote.post(f"{CLIENT_API_PREFIX}/hello", json=payload, headers=auth(self.token)))

    def commands(self) -> list[JsonObject]:
        reply = body(
            self.remote.post(
                f"{CLIENT_API_PREFIX}/control",
                json={"after": self.after, "wait": 0},
                headers=auth(self.token),
            )
        )
        items = cast("list[JsonObject]", reply["commands"])
        if items:
            self.after = cast("int", items[-1]["seq"])
        return items

    def next(self, kind: str, timeout: float = 10) -> JsonObject:
        deadline = time.monotonic() + timeout
        while True:
            for item in self.commands():
                if item["type"] == kind:
                    return item
            assert time.monotonic() < deadline, f"逾時：等不到 {kind}"
            time.sleep(0.02)

    def output(self, process: str, lines: list[str], exit_code: int | None = None) -> None:
        payload: JsonObject = {"lines": lines}
        if exit_code is not None:
            payload["exit"] = exit_code
        response = self.remote.post(
            f"{CLIENT_API_PREFIX}/processes/{process}/output",
            json=payload,
            headers=auth(self.token),
        )
        assert response.status_code == 204, response.text

    def answer(self, process: str, call: Callable[[], Response], **reply: object) -> Response:
        """在背景送請求，等它變成給子程序的一行命令，再照命令的 id 回覆。"""
        result: list[Response] = []
        thread = threading.Thread(target=lambda: result.append(call()))
        thread.start()
        line = json.loads(str(self.next("input")["line"]))
        self.output(process, [json.dumps({"id": line["id"], **reply})])
        thread.join(10)
        assert result, "請求沒有結束"
        return result[0]


def paired(client: Client, remote: Client, recorder_id: str = "agent-mac") -> Device:
    body(client.post("/api/recorders", json={"id": recorder_id, "name": "Agent 專用 Mac"}), 201)
    invited = cast(
        "JsonObject", body(client.post(f"/api/recorders/{recorder_id}/invite"))["invite"]
    )
    code = parse_invite(str(invited["line"])).code
    reply = body(remote.post(f"{CLIENT_API_PREFIX}/pair", json={"code": code, "app": "recorder"}))
    return Device(remote, str(reply["token"]))


def test_debug_runs_on_an_allowed_recorder(app: FastAPI, client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    device = paired(client, remote)
    device.hello(capabilities=["debugSnapshot"])
    agent = register(client, remote, scopes=["scenes:read", "debug"])
    assert error(agent.post("/scenes/ba-001/debug"), 422)["code"] == "recorder_required"
    assert body(agent.get("/recorders")) == {"recorders": []}
    policy(client, scopes=["scenes:read", "debug"], recorders=["agent-mac"], maxDebugSessions=1)
    assert error(agent.post("/scenes/ba-001/debug"), 403)["code"] == "recorder_agent_off"
    assert error(agent.post("/scenes/ba-001/debug", {"recorderId": "mac-02"}), 403)["code"] == (
        "recorder_forbidden"
    )
    body(
        client.patch(
            "/api/recorders/agent-mac", json={"allowAgent": True, "agentHeadlessOnly": True}
        )
    )
    recorders = cast("list[JsonObject]", body(agent.get("/recorders"))["recorders"])
    assert recorders[0]["allowAgent"] is True
    assert recorders[0]["headlessOnly"] is True
    assert recorders[0]["capabilities"] == ["debugSnapshot"]
    headed = error(agent.post("/scenes/ba-001/debug", {"headless": False}), 403)
    assert headed["code"] == "recorder_headless_only"

    session = body(agent.post("/scenes/ba-001/debug"), 202)
    assert session["deviceId"] == "agent-mac"
    assert session["clientId"] == "agent-erp"
    assert session["headless"] is True
    start = device.next("start")
    assert "--headed" not in cast("list[str]", start["args"])
    process = str(start["process"])
    device.output(process, [json.dumps({"event": "ready"})])
    session_id = str(session["id"])
    wait_until(lambda: body(agent.get(f"/debug/{session_id}"))["status"] == "ready")
    assert body(agent.post("/scenes/ba-001/debug"), 202)["id"] == session_id  # 已經有就回傳它
    assert body(agent.get("/scenes/ba-001"))["debug"] == {
        "id": session_id,
        "mine": True,
        "status": "ready",
    }

    # 另一個用戶端：不搶走，也看不到這個工作階段
    body(
        client.post(
            "/api/agents",
            json={
                "id": "agent-bi",
                "policy": {"scopes": ["debug", "scenes:read"], "recorders": ["agent-mac"]},
            },
        ),
        201,
    )
    other = Agent(remote, str(body(client.post("/api/agents/agent-bi/key"))["key"]))
    assert error(other.post("/scenes/ba-001/debug"), 409)["code"] == "debug_in_use"
    assert error(other.get(f"/debug/{session_id}"), 404)["code"] == "debug_not_found"
    assert body(other.get("/debug")) == {"sessions": []}
    # 限額：同時只能開一個
    assert error(agent.post("/scenes/ba-002/debug"), 429)["code"] == "limit_reached"

    # 讀頁面結構：要開「回傳頁面內容」
    assert error(agent.post(f"/debug/{session_id}/snapshot"), 403)["code"] == "content_disabled"
    assert error(agent.post(f"/debug/{session_id}/screenshot"), 403)["code"] == "content_disabled"
    policy(
        client,
        scopes=["scenes:read", "debug"],
        recorders=["agent-mac"],
        maxDebugSessions=1,
        pageContent=True,
    )
    page = {
        "ok": True,
        "url": "https://erp.example.test/orders/new",
        "title": "新增訂單",
        "tabs": [{"page": None, "url": "https://erp.example.test/orders/new", "active": True}],
        "frames": [],
        "fields": [{"role": "textbox", "label": "客戶", "value": "***"}],
        "aria": '- textbox "客戶"',
        "truncated": False,
    }
    reply = device.answer(
        process,
        lambda: agent.post(f"/debug/{session_id}/snapshot", {"within": {"css": "#main"}}),
        **page,
    )
    snapshot = body(reply)
    assert snapshot == {key: value for key, value in page.items() if key != "ok"}
    located = device.answer(
        process,
        lambda: agent.post(
            f"/debug/{session_id}/locate", {"locator": {"role": "button", "name": "建立"}}
        ),
        ok=True,
        count=1,
        matches=[{"tag": "button", "text": "建立"}],
    )
    assert cast("JsonObject", body(located)["located"])["count"] == 1

    # 舊版的錄製端 App 沒有回報這個功能：說明要更新
    device.hello()
    outdated = error(agent.post(f"/debug/{session_id}/snapshot"), 422)
    assert outdated["code"] == "recorder_outdated"
    assert "讀頁面結構" in str(outdated["message"])

    # 關掉「允許 Agent 調試」：新的工作階段被拒絕
    body(client.patch("/api/recorders/agent-mac", json={"allowAgent": False}))
    assert error(agent.post("/scenes/ba-001/debug", {"restart": True}), 403)["code"] == (
        "recorder_agent_off"
    )

    closing = threading.Thread(target=lambda: agent.delete(f"/debug/{session_id}"))
    closing.start()
    device.next("close")
    device.output(process, [], exit_code=0)
    closing.join(10)
    assert not closing.is_alive()
    assert error(agent.get(f"/debug/{session_id}"), 404)["code"] == "debug_not_found"
    audit = cast(
        "list[JsonObject]",
        body(client.get("/api/agent-audit", params={"client": "agent-erp"}))["audit"],
    )
    assert ("DELETE", "/debug/{session_id}", 200) in [
        (item["method"], item["action"], item["status"]) for item in audit
    ]
