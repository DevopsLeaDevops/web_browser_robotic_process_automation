"""M6 驗收：真實瀏覽器跑原型的試驗場流程。

BA-001（建立紀錄）→ BA-002（用 BA-001 的出參 recordId 查詢）：上游通過才把出參交給下游；
上游失敗時下游不執行。每個情境在 Chromium 與 Firefox 各跑一次；佇列由測試呼叫 worker.run_once()。
"""

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_worker import Worker
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

JsonObject = dict[str, object]


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with running() as url:
        yield url


def body(response: Response) -> JsonObject:
    assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def worker(app: FastAPI) -> Worker:
    return cast("Worker", app.state.worker)


def validate_and_publish(
    app: FastAPI, client: Client, scene: str, inputs: JsonObject, engine: str
) -> JsonObject:
    """真實驗證後發布第 1 版；回傳驗證的結果。"""
    queued = body(
        client.post(
            f"/api/scenes/{scene}/revisions/1/validate",
            json={"inputs": inputs, "engine": engine, "headless": True},
        )
    )
    assert worker(app).run_once() is True
    validated = body(client.get(f"/api/runs/{queued['id']}"))
    assert validated["status"] == "passed", validated["error"]
    body(client.post(f"/api/scenes/{scene}/revisions/1/publish"))
    return validated


@pytest.fixture
def published(app: FastAPI, client: Client, site: str, engine: str) -> None:
    """匯入範例，預設網址指到測試網站，BA-001 與 BA-002 驗證通過並發布。"""
    body(client.post("/api/scenes/import"))
    for scene in ("ba-001", "ba-002", "ba-003"):
        body(client.patch(f"/api/scenes/{scene}", json={"baseUrl": site}))
    created = validate_and_publish(app, client, "ba-001", {}, engine)
    record = cast("JsonObject", created["output"])
    validate_and_publish(app, client, "ba-002", {"recordId": record["recordId"]}, engine)


def run_all(app: FastAPI, client: Client, run_id: object) -> JsonObject:
    """把序列排入的節點一個一個執行完，回傳序列的執行。"""
    while worker(app).run_once():
        pass
    return body(client.get(f"/api/workflow-runs/{run_id}"))


def test_chain_passes_outputs_downstream(
    app: FastAPI, client: Client, engine: str, published: None
) -> None:
    definition = {
        "nodes": [
            {
                "id": "n1",
                "sceneId": "ba-001",
                "revision": 1,
                "inputs": {"title": {"value": "試驗場串接"}, "quantity": {"value": 7}},
            },
            {
                "id": "n2",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
            },
        ]
    }
    workflow = body(
        client.post("/api/workflows", json={"name": "建立後查詢", "definition": definition})
    )
    assert workflow["problems"] == []
    started = body(
        client.post(
            f"/api/workflows/{workflow['id']}/runs", json={"engine": engine, "headless": True}
        )
    )

    run = run_all(app, client, started["id"])

    assert run["status"] == "passed", run["error"]
    first, second = (
        cast("JsonObject", node["run"]) for node in cast("list[JsonObject]", run["nodes"])
    )
    created = cast("JsonObject", first["output"])
    assert (created["title"], created["quantity"]) == ("試驗場串接", 7)
    assert second["input"] == {"recordId": created["recordId"]}
    assert second["output"] == created  # 查到的就是剛建立的那一筆
    assert (first["engine"], second["engine"]) == (engine, engine)
    report = body(client.get(f"/api/runs/{second['id']}"))
    assert "report.html" in cast("list[str]", report["files"])


def test_failed_upstream_stops_the_sequence(
    app: FastAPI, client: Client, engine: str, published: None
) -> None:
    """查詢不存在的紀錄（BA-002 失敗）排在前面：後面的 BA-001 不執行，不會建立紀錄。"""
    definition = {
        "nodes": [
            {
                "id": "lookup",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"value": "DEMO-NOTFOUND1"}},
            },
            {"id": "create", "sceneId": "ba-001", "revision": 1},
        ]
    }
    workflow = body(
        client.post("/api/workflows", json={"name": "失敗即停", "definition": definition})
    )
    started = body(
        client.post(
            f"/api/workflows/{workflow['id']}/runs", json={"engine": engine, "headless": True}
        )
    )

    run = run_all(app, client, started["id"])

    assert run["status"] == "failed"
    assert run["failedNode"] == "lookup"
    assert [node["status"] for node in cast("list[JsonObject]", run["nodes"])] == [
        "failed",
        "skipped",
    ]
    executed = cast("list[JsonObject]", body(client.get("/api/runs?purpose=workflow"))["runs"])
    assert [item["nodeId"] for item in executed] == ["lookup"]
