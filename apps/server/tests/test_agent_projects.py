"""M14 對外 Agent API 的專案：專案與組合場景的新增、編輯、驗證、發布、執行與運行過程，
以及權限範圍、可用的專案與領域、限額、冪等鍵。

節點的執行換成假的執行器（同 test_composites.py：一律通過，回報磁碟上場景版本的雜湊，驗證紀錄
才能當發布的依據）。管理 API 打管理頁面的埠，Agent 的請求打對外埠並帶 API 金鑰。
"""

import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_runner.contract import check_inputs
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Revision, Scene
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]
WORKER_PORT = 8081
AGENT = "/agent-api/v1"
EVERYTHING = [
    "scenes:read",
    "runs:validate",
    "runs:execute",
    "runs:read",
    "projects:read",
    "projects:write",
]
CHAIN: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "Agent"}}},
        {"id": "n2", "sceneId": "ba-002", "revision": 1, "inputs": {"recordId": {"auto": True}}},
    ],
    "edges": [{"source": "n1", "target": "n2"}],
}
SINGLE: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [{"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {}}],
    "edges": [],
}


def executor(
    path: Path,
    inputs: Mapping[str, object],
    *,
    out_root: Path,
    base_url: str | None = None,
    engine: str | None = None,
    headed: bool = False,
    deadline_ms: int | None = None,
    run_id: str | None = None,
    cancel: threading.Event | None = None,
    on_stage: Callable[[StageName], None] | None = None,
    login: LoginSettings | None = None,
    secrets: Mapping[str, str] | None = None,
    record_video: bool = False,
    **_files: object,
) -> RunResult:
    """假的執行器：一律通過，出參取同名的入參；回報磁碟上場景版本的真實雜湊。"""
    scenario = validate_file(path).scenario
    assert scenario is not None
    assert run_id is not None
    resolved, problems = check_inputs(scenario, inputs)
    assert problems == []
    fixed = "DEMO-" + scenario.id.upper().replace("-", "")
    directory = out_root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    return RunResult(
        run_id=run_id,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        scenario_hash=scenario_digest(path, scenario),
        kind="dsl",
        engine=engine or scenario.browser.engine,
        directory=directory,
        started_at=now().isoformat(),
        status="passed",
        input=resolved,
        output={
            name: resolved.get(name, fixed if spec.type == "string" else 1)
            for name, spec in scenario.outputs.items()
        },
        error=None,
    )


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT, worker_host="192.168.1.10")


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    """打到對外埠的用戶端（伺服器已經由 client 啟動）。"""
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


@pytest.fixture
def worker(app: FastAPI) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json() if response.content else {}
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def items(data: JsonObject, key: str) -> list[JsonObject]:
    return cast("list[JsonObject]", data[key])


@dataclass
class Agent:
    """扮演 Agent 系統：每個請求帶自己的金鑰，路徑自動加上 /agent-api/v1。"""

    remote: Client
    key: str

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"}

    def get(self, path: str, **params: object) -> Response:
        return self.remote.get(AGENT + path, params=params, headers=self.headers())  # pyright: ignore[reportArgumentType]

    def post(self, path: str, payload: JsonObject | None = None) -> Response:
        return self.remote.post(AGENT + path, json=payload or {}, headers=self.headers())

    def put(self, path: str, payload: JsonObject) -> Response:
        return self.remote.put(AGENT + path, json=payload, headers=self.headers())

    def patch(self, path: str, payload: JsonObject) -> Response:
        return self.remote.patch(AGENT + path, json=payload, headers=self.headers())


def register(client: Client, remote: Client, agent_id: str = "agent-qa", **policy: object) -> Agent:
    created = body(
        client.post("/api/agents", json={"id": agent_id, "name": "測試助理", "policy": policy}),
        201,
    )
    return Agent(remote, str(created["key"]))


def publish_scene(app: FastAPI, scene_id: str) -> None:
    """直接在資料庫把場景的第 1 版標成已發布（發布門檻在 test_packs.py 測過）。"""
    with services(app).sessions() as session:
        scene = session.get(Scene, scene_id)
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == scene_id, Revision.number == 1)
        ).one()
        assert scene is not None
        revision.status = "passed"
        revision.published_at = now()
        scene.published_number = 1
        session.commit()


def import_examples(app: FastAPI, client: Client) -> None:
    """範例場景放進「實驗」領域，發布 BA-001 與 BA-002。"""
    assert client.post("/api/domains", json={"id": "lab", "name": "實驗"}).status_code == 201
    body(client.post("/api/scenes/import", json={"domainId": "lab"}))
    publish_scene(app, "ba-001")
    publish_scene(app, "ba-002")


def drain(worker: Worker) -> None:
    while worker.run_once():
        pass


# ---------------------------------------------------------------- 權限與限制


def test_projects_follow_scopes_and_allowed_projects(client: Client, remote: Client) -> None:
    body(client.post("/api/projects", json={"id": "sales", "name": "銷售"}), 201)
    body(client.post("/api/projects", json={"id": "hr", "name": "人資"}), 201)

    reader = register(client, remote)  # 預設：scenes:read、runs:read、projects:read
    meta = body(reader.get("/meta"))
    assert meta["scopes"] == ["scenes:read", "runs:read", "projects:read"]
    assert meta["projects"] is None
    listed = items(body(reader.get("/projects")), "projects")
    assert [(p["id"], p["portalPath"]) for p in listed] == [
        ("sales", "/projects/sales"),
        ("hr", "/projects/hr"),
    ]
    denied = reader.post("/projects", {"id": "qa", "name": "測試"})
    assert error(denied, 403)["code"] == "scope_missing"

    unknown = client.post(
        "/api/agents", json={"id": "agent-x", "policy": {"projects": ["sales", "nope"]}}
    )
    assert error(unknown, 422)["code"] == "agent_project_unknown"

    limited = register(
        client, remote, "agent-sales", scopes=EVERYTHING, projects=["sales"], domains=None
    )
    assert [p["id"] for p in items(body(limited.get("/projects")), "projects")] == ["sales"]
    assert error(limited.get("/projects/hr"), 403)["code"] == "project_forbidden"
    refused = limited.post("/projects", {"id": "qa", "name": "測試"})
    assert error(refused, 403)["code"] == "project_create_forbidden"
    renamed = body(limited.patch("/projects/sales", {"description": "銷售流程的回歸測試"}))
    assert renamed["description"] == "銷售流程的回歸測試"
    assert error(limited.patch("/projects/hr", {"name": "x"}), 403)["code"] == "project_forbidden"

    # 管理後台：用戶端列表顯示可用的專案，表單可以勾專案
    page = client.get("/agents").text
    assert "專案：sales" in page
    assert 'name="all-projects"' in page
    assert 'name="project" value="hr"' in page


def test_agent_builds_validates_publishes_and_runs_a_project(
    app: FastAPI, client: Client, remote: Client, worker: Worker
) -> None:
    import_examples(app, client)
    agent = register(client, remote, scopes=EVERYTHING)

    # 專案：新增（冪等鍵重送拿到同一個）、改名稱
    created = body(
        agent.post("/projects", {"id": "orders", "name": "訂單", "idempotencyKey": "p-1"}), 201
    )
    again = body(
        agent.post("/projects", {"id": "orders", "name": "訂單", "idempotencyKey": "p-1"}), 201
    )
    assert created == again
    assert error(agent.post("/projects", {"id": "orders", "name": "訂單"}), 409)["code"] == (
        "project_exists"
    )

    # 場景庫與檢查
    library = items(body(agent.get("/composites/library")), "scenes")
    assert [scene["id"] for scene in library] == ["ba-001", "ba-002"]
    assert body(agent.post("/composites/check", {"definition": CHAIN})) == {
        "ok": True,
        "problems": [],
    }
    broken = {**SINGLE, "nodes": [{"id": "n1", "sceneId": "ba-003", "revision": 1}]}
    checked = body(agent.post("/composites/check", {"definition": broken}))
    assert checked["ok"] is False
    assert [p["code"] for p in items(checked, "problems")] == ["workflow.revision_unpublished"]

    # 組合場景：建立（第 1 版）、存新版本、版本衝突
    composite = body(
        agent.post(
            "/projects/orders/composites",
            {
                "name": "建立後查詢",
                "code": "tc-order-001",
                "definition": SINGLE,
                "idempotencyKey": "c-1",
            },
        ),
        201,
    )
    assert (composite["code"], composite["projectId"], composite["version"]) == (
        "tc-order-001",
        "orders",
        1,
    )
    assert composite["portalPath"] == f"/playground/{composite['id']}"
    resent = agent.post(
        "/projects/orders/composites",
        {"name": "建立後查詢", "code": "tc-order-001", "idempotencyKey": "c-1"},
    )
    assert body(resent, 201)["id"] == composite["id"]
    saved = body(
        agent.put(
            "/composites/tc-order-001",
            {"baseRevision": 1, "definition": CHAIN, "note": "加上查詢"},
        )
    )
    assert saved["version"] == 2
    stale = agent.put("/composites/tc-order-001", {"baseRevision": 1, "name": "改名"})
    assert error(stale, 409)["code"] == "stale_workflow"
    detail = body(agent.get("/composites/tc-order-001"))
    notes = [(r["number"], r["note"]) for r in items(detail, "revisions")]
    assert notes == [(2, "Agent〈測試助理〉：加上查詢"), (1, "由 Agent〈測試助理〉建立")]
    assert detail["runs"] == []

    # 驗證第 2 版：進度、節點的運行記下 Agent
    started = body(agent.post("/composites/tc-order-001/revisions/2/validate", {}), 202)
    assert (started["status"], started["purpose"], started["clientId"]) == (
        "running",
        "validation",
        "agent-qa",
    )
    assert started["progress"] == {"total": 2, "done": 0, "passed": 0, "current": "n1"}
    assert started["portalPath"] == f"/playground/runs/{started['id']}"
    first = cast("JsonObject", items(started, "nodes")[0]["run"])
    assert (first["clientId"], first["portalPath"]) == ("agent-qa", f"/runs/{first['id']}")
    drain(worker)
    finished = body(agent.get(f"/composite-runs/{started['id']}"))
    assert finished["status"] == "passed"
    assert finished["progress"] == {"total": 2, "done": 2, "passed": 2, "current": None}
    second = cast("JsonObject", items(finished, "nodes")[1]["run"])
    assert second["input"] == {"recordId": "DEMO-BA001"}
    steps = body(agent.get(f"/runs/{second['id']}/steps"))
    assert steps["finished"] is True

    # 發布要 projects:publish
    denied = agent.post("/composites/tc-order-001/revisions/2/publish")
    assert error(denied, 403)["code"] == "scope_missing"
    client.patch(
        "/api/agents/agent-qa", json={"policy": {"scopes": [*EVERYTHING, "projects:publish"]}}
    )
    published = body(agent.post("/composites/tc-order-001/revisions/2/publish"))
    assert published["publishedRevision"] == 2

    # 正式執行（冪等鍵）、專案的執行（沒發布的列在 skipped）
    body(
        agent.post(
            "/projects/orders/composites",
            {"name": "只建立", "code": "tc-order-002", "definition": SINGLE},
        ),
        201,
    )
    run = body(agent.post("/composites/tc-order-001/runs", {"idempotencyKey": "r-1"}), 202)
    assert (
        body(agent.post("/composites/tc-order-001/runs", {"idempotencyKey": "r-1"}), 202)["id"]
        == run["id"]
    )
    drain(worker)
    batch = body(agent.post("/projects/orders/runs", {"composites": ["tc-order-001", "nope"]}), 202)
    assert [r["workflowCode"] for r in items(batch, "runs")] == ["tc-order-001"]
    assert [
        (s["code"], cast("JsonObject", s["error"])["code"]) for s in items(batch, "skipped")
    ] == [("nope", "workflow_not_found")]
    everything = body(agent.post("/projects/orders/runs", {"purpose": "execution"}), 202)
    skipped = [
        (s["code"], cast("JsonObject", s["error"])["code"]) for s in items(everything, "skipped")
    ]
    assert skipped == [("tc-order-002", "workflow_unpublished")]
    drain(worker)

    # 運行過程：列表的篩選
    listed = items(
        body(agent.get("/composite-runs", project="orders", purpose="execution")), "runs"
    )
    assert len(listed) == 3
    assert all(item["status"] == "passed" for item in listed)
    assert len(items(body(agent.get("/composite-runs", composite="tc-order-001")), "runs")) == 4
    project = body(agent.get("/projects/orders"))
    summaries = {c["code"]: c for c in items(project, "composites")}
    assert cast("JsonObject", summaries["tc-order-001"]["lastRun"])["status"] == "passed"
    assert summaries["tc-order-002"]["publishedRevision"] is None

    # 重跑（從頭）；別人的執行不能取消
    rerun = body(agent.post(f"/composite-runs/{run['id']}/rerun", {}), 202)
    assert rerun["clientId"] == "agent-qa"
    other = register(client, remote, "agent-other", scopes=EVERYTHING)
    cancelled = other.post(f"/composite-runs/{rerun['id']}/cancel")
    assert error(cancelled, 403)["code"] == "run_forbidden"
    assert body(agent.post(f"/composite-runs/{rerun['id']}/cancel"), 202)["status"] == "cancelled"

    # Portal：組合場景的執行標出觸發的 Agent
    page = client.get("/projects/orders").text
    assert "由 Agent〈測試助理〉觸發" in page
    assert "觸發的 Agent" in client.get(f"/playground/runs/{run['id']}").text

    # 移到另一個專案
    body(agent.post("/projects", {"id": "archive", "name": "封存區"}), 201)
    moved = body(agent.patch("/composites/tc-order-002", {"projectId": "archive"}))
    assert moved["projectId"] == "archive"


def test_composites_follow_domains_projects_and_limits(
    app: FastAPI, client: Client, remote: Client, worker: Worker
) -> None:
    import_examples(app, client)
    body(client.post("/api/projects", json={"id": "orders", "name": "訂單"}), 201)
    loose = body(
        client.post("/api/workflows", json={"name": "沒有專案", "definition": SINGLE}), 201
    )

    # 組合場景放在「組合場景」領域：沒有這個領域時不能建立
    only_lab = register(client, remote, scopes=EVERYTHING, domains=["lab"])
    refused = only_lab.post("/projects/orders/composites", {"name": "x", "definition": SINGLE})
    assert error(refused, 403)["code"] == "domain_forbidden"

    # 有「組合場景」領域、沒有場景的領域：節點用到的場景不能用
    no_lab = register(client, remote, "agent-composites", scopes=EVERYTHING, domains=["composites"])
    blocked = no_lab.post("/projects/orders/composites", {"name": "x", "definition": SINGLE})
    assert error(blocked, 403)["code"] == "composite_scenes_forbidden"
    assert error(no_lab.post("/composites/check", {"definition": CHAIN}), 403)["scenes"] == [
        "ba-001",
        "ba-002",
    ]
    assert body(no_lab.get("/composites/library"))["scenes"] == []

    # 不屬於任何專案的組合場景不給 Agent
    both = register(client, remote, "agent-both", scopes=EVERYTHING, domains=["lab", "composites"])
    assert error(both.get(f"/composites/{loose['code']}"), 404)["code"] == "workflow_not_found"
    created = body(
        both.post("/projects/orders/composites", {"name": "可以", "definition": SINGLE}), 201
    )
    assert [c["code"] for c in items(body(both.get("/composites")), "composites")] == [
        created["code"]
    ]

    # 限額：排隊中與執行中的運行（含組合場景的節點）
    client.patch(
        "/api/agents/agent-both",
        json={
            "policy": {
                "scopes": EVERYTHING,
                "domains": ["lab", "composites"],
                "maxQueuedRuns": 1,
            }
        },
    )
    body(both.post(f"/composites/{created['code']}/revisions/1/validate", {}), 202)
    limited = both.post(f"/composites/{created['code']}/revisions/1/validate", {})
    assert error(limited, 429)["code"] == "limit_reached"
    drain(worker)
    body(both.post(f"/composites/{created['code']}/revisions/1/validate", {}), 202)

    # 稽核記下專案的寫入請求
    audit = items(body(client.get("/api/agent-audit", params={"client": "agent-both"})), "audit")
    actions = {item["action"] for item in audit}
    assert "/composites/{code}/revisions/{number}/validate" in actions
    assert "/projects/{project_id}/composites" in actions
