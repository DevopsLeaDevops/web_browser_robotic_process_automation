"""M6 自由試驗場的 API（不需要瀏覽器）：序列的存檔與檢查、依序執行、失敗即停、繼續與取消。

節點的執行換成假的執行器（不開瀏覽器）：出參取同名的入參，其餘是固定的值；可以指定哪些場景失敗。
真實瀏覽器的串接在 test_workflow_flow.py。
"""

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_core.dsl import validate_file
from rpa_runner.contract import check_inputs
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, RunStatus, StageName
from rpa_server.domain import now
from rpa_server.errors import ServiceError
from rpa_server.models import Revision, Scene
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]

CHAIN: JsonObject = {
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "試驗場"}}},
        {
            "id": "n2",
            "sceneId": "ba-002",
            "revision": 1,
            "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
        },
    ]
}


class FakeExecutor:
    """假的執行器：記下每次執行的場景與入參；fail 指定的場景以那個狀態結束。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail: dict[str, RunStatus] = {}

    def __call__(
        self,
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
    ) -> RunResult:
        scenario = validate_file(path).scenario
        assert scenario is not None
        assert run_id is not None
        resolved, problems = check_inputs(scenario, inputs)
        assert problems == []
        self.calls.append((scenario.id, resolved))
        status = self.fail.get(scenario.id, "passed")
        output: dict[str, object] | None = None
        if status == "passed":
            fixed = "DEMO-" + scenario.id.upper().replace("-", "")
            output = {
                name: resolved.get(name, fixed if spec.type == "string" else 1)
                for name, spec in scenario.outputs.items()
            }
        directory = out_root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        return RunResult(
            run_id=run_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_hash="0" * 64,
            kind="dsl",
            engine=engine or scenario.browser.engine,
            directory=directory,
            started_at=now().isoformat(),
            status=status,
            input=resolved,
            output=output,
            error=None if status == "passed" else f"假的結果：{status}",
        )


@pytest.fixture
def executor() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
def worker(app: FastAPI, executor: FakeExecutor) -> Worker:
    """同一個任務來源（資料庫的佇列），換成假的執行器；測試自己呼叫 run_once。"""
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int | None = None) -> JsonObject:
    if status is not None:
        assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def publish(app: FastAPI, scene_id: str, number: int = 1) -> None:
    """直接在資料庫標成已發布（發布門檻本身在 test_api.py 測過）。"""
    with services(app).sessions() as session:
        scene = session.get(Scene, scene_id)
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == scene_id, Revision.number == number)
        ).one()
        assert scene is not None
        revision.status = "passed"
        revision.published_at = now()
        scene.published_number = number
        session.commit()


def nodes(run: JsonObject) -> list[JsonObject]:
    return cast("list[JsonObject]", run["nodes"])


def statuses(run: JsonObject) -> list[str]:
    return [str(node["status"]) for node in nodes(run)]


def node_run(node: JsonObject) -> JsonObject:
    run = node["run"]
    assert isinstance(run, dict)
    return cast("JsonObject", run)


@pytest.fixture
def chain(app: FastAPI, client: Client) -> int:
    """匯入範例、發布 BA-001 與 BA-002，建立「BA-001 → BA-002」的序列。"""
    body(client.post("/api/scenes/import"))
    publish(app, "ba-001")
    publish(app, "ba-002")
    created = body(
        client.post("/api/workflows", json={"name": "建立後查詢", "definition": CHAIN}), 201
    )
    assert created["problems"] == []
    return cast("int", created["id"])


def start(client: Client, workflow_id: int, **options: object) -> JsonObject:
    return body(client.post(f"/api/workflows/{workflow_id}/runs", json=options), 202)


def get(client: Client, run_id: object) -> JsonObject:
    return body(client.get(f"/api/workflow-runs/{run_id}"))


# ---------------------------------------------------------------- 序列


def test_save_check_and_version_conflict(app: FastAPI, client: Client) -> None:
    services(app).seed_examples_domain()  # 「測試網站自動化」領域與範例
    publish(app, "ba-001")
    publish(app, "ba-002")

    created = body(client.post("/api/workflows", json={"name": " 建立後查詢 "}), 201)
    workflow = created["id"]
    assert created["name"] == "建立後查詢"
    assert created["version"] == 1
    assert cast("JsonObject", created["definition"])["nodes"] == []
    assert [p["code"] for p in cast("list[JsonObject]", created["problems"])] == ["workflow.empty"]

    library = cast("list[JsonObject]", body(client.get("/api/workflows/library"))["scenes"])
    assert [scene["id"] for scene in library] == ["ba-001", "ba-002"]  # 只有發布過的
    first = cast("list[JsonObject]", library[0]["revisions"])[0]
    assert first["number"] == 1
    assert [name for name, _ in cast("list[list[object]]", first["inputs"])] == [
        "title",
        "quantity",
    ]
    assert library[0]["domainName"] == "測試網站自動化"

    checked = body(client.post("/api/workflows/check", json={"definition": CHAIN}))
    assert checked == {"ok": True, "problems": []}

    saved = body(
        client.put(f"/api/workflows/{workflow}", json={"baseVersion": 1, "definition": CHAIN})
    )
    assert saved["version"] == 2
    assert saved["problems"] == []
    stale = client.put(f"/api/workflows/{workflow}", json={"baseVersion": 1, "name": "改名"})
    assert error(stale, 409)["code"] == "stale_workflow"
    renamed = body(
        client.put(f"/api/workflows/{workflow}", json={"baseVersion": 2, "name": "改名"})
    )
    assert (renamed["name"], renamed["version"]) == ("改名", 2)  # 改名不分版本（M11 PR 2）
    assert renamed["definition"] == {"version": 1, "mode": "serial", "onFailure": "stop", **CHAIN}

    assert [
        w["id"] for w in cast("list[JsonObject]", body(client.get("/api/workflows"))["workflows"])
    ] == [workflow]
    assert body(client.delete(f"/api/workflows/{workflow}")) == {"deleted": workflow}
    assert error(client.get(f"/api/workflows/{workflow}"), 404)["code"] == "workflow_not_found"


def test_check_reports_scenes_revisions_and_bindings(app: FastAPI, client: Client) -> None:
    body(client.post("/api/scenes/import"))
    publish(app, "ba-001")

    def codes(definition: JsonObject) -> list[str]:
        checked = body(client.post("/api/workflows/check", json={"definition": definition}))
        return [str(p["code"]) for p in cast("list[JsonObject]", checked["problems"])]

    def single(scene: str, revision: int = 1, **inputs: object) -> JsonObject:
        node = {"id": "n1", "sceneId": scene, "revision": revision, "inputs": inputs}
        return {"nodes": [node]}

    assert codes(single("ba-003")) == ["workflow.revision_unpublished"]
    assert codes(single("nope")) == ["workflow.scene_missing"]
    assert codes(single("ba-001", 9)) == ["workflow.revision_missing"]
    assert codes(single("ba-001", quantity={"value": 99})) == ["workflow.value_invalid"]
    assert codes(CHAIN) == ["workflow.revision_unpublished"]  # BA-002 還沒發布
    assert codes({"nodes": [{"id": "n1", "sceneId": "ba-001", "revision": 0}]}) == [
        "workflow.invalid"
    ]
    client.patch("/api/scenes/ba-001", json={"archived": True})
    assert codes(single("ba-001")) == ["workflow.scene_archived"]

    bad = client.post("/api/workflows", json={"name": "壞的", "definition": {"version": 2}})
    assert error(bad, 422)["code"] == "workflow_format"
    missing = client.post("/api/workflows", json={"name": "  "})
    assert error(missing, 422)["code"] == "workflow_name_missing"


# ---------------------------------------------------------------- 執行


def test_nodes_run_in_order_and_outputs_flow_downstream(
    app: FastAPI, client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    run = start(client, chain, headless=True)
    assert run["status"] == "running"
    assert statuses(run) == ["queued", "pending"]
    sources = cast("JsonObject", nodes(run)[1]["sources"])
    assert sources["recordId"] == {
        "kind": "output",
        "node": "n1",
        "output": "recordId",
        "value": None,
    }

    assert worker.run_once() is True  # n1；結束後自動排入 n2
    run = get(client, run["id"])
    assert statuses(run) == ["passed", "queued"]
    assert worker.run_once() is True
    run = get(client, run["id"])
    assert run["status"] == "passed"
    assert run["failedNode"] is None
    assert worker.run_once() is False

    assert executor.calls == [
        ("ba-001", {"title": "試驗場", "quantity": 12}),
        ("ba-002", {"recordId": "DEMO-BA001"}),
    ]
    first, second = (node_run(node) for node in nodes(run))
    assert first["output"] == {"recordId": "DEMO-BA001", "title": "試驗場", "quantity": 12}
    assert second["input"] == {"recordId": "DEMO-BA001"}
    assert (second["purpose"], second["workflowRunId"], second["nodeId"]) == (
        "workflow",
        run["id"],
        "n2",
    )
    assert second["revision"] == 1

    reported = cast("list[JsonObject]", body(client.get("/api/runs?purpose=workflow"))["runs"])
    assert [item["nodeId"] for item in reported] == ["n2", "n1"]
    listed = cast(
        "list[JsonObject]", body(client.get(f"/api/workflow-runs?workflow={chain}"))["runs"]
    )
    assert [item["id"] for item in listed] == [run["id"]]
    workflow = body(client.get(f"/api/workflows/{chain}"))
    assert cast("JsonObject", workflow["lastRun"])["status"] == "passed"

    # 頁面
    for url in ("/playground", f"/playground/{chain}", f"/playground/runs/{run['id']}"):
        page = client.get(url)
        assert page.status_code == 200, url
    assert 'id="workflow-data"' in client.get(f"/playground/{chain}").text
    run_page = client.get(f"/playground/runs/{run['id']}").text
    assert 'data-status="passed"' in run_page
    assert "DEMO-BA001" in run_page
    node_page = client.get(f"/runs/{second['id']}").text
    assert f'href="/playground/runs/{run["id"]}"' in node_page
    assert 'data-action="rerun"' not in node_page  # 節點的執行從序列執行頁繼續


def test_failure_stops_and_resume_reuses_passed_nodes(
    app: FastAPI, client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    executor.fail["ba-002"] = "needs_login"
    run = start(client, chain, headless=True)
    worker.run_once()
    worker.run_once()
    run = get(client, run["id"])
    assert run["status"] == "needs_login"
    assert run["failedNode"] == "n2"
    assert run["resumable"] is True
    assert "n2" in str(run["error"])
    assert statuses(run) == ["passed", "needs_login"]
    page = client.get(f"/playground/runs/{run['id']}").text
    assert 'data-resume="1"' in page

    # 登入之後：從 n2 繼續，n1 沿用上次的結果，不會再建立一次紀錄
    executor.fail.clear()
    resumed = body(client.post(f"/api/workflow-runs/{run['id']}/rerun", json={"resume": True}), 202)
    assert resumed["resumedFrom"] == run["id"]
    assert statuses(resumed) == ["reused", "queued"]
    assert node_run(nodes(resumed)[0])["id"] == node_run(nodes(run)[0])["id"]
    worker.run_once()
    resumed = get(client, resumed["id"])
    assert resumed["status"] == "passed"
    assert [scene for scene, _ in executor.calls] == ["ba-001", "ba-002", "ba-002"]
    assert executor.calls[-1][1] == {"recordId": "DEMO-BA001"}

    # 通過的不能「繼續」；從頭再執行兩個節點都重跑
    again = client.post(f"/api/workflow-runs/{resumed['id']}/rerun", json={"resume": True})
    assert error(again, 409)["code"] == "workflow_not_resumable"
    fresh = body(client.post(f"/api/workflow-runs/{resumed['id']}/rerun", json={}), 202)
    assert statuses(fresh) == ["queued", "pending"]
    assert fresh["resumedFrom"] is None


def test_upstream_failure_skips_the_rest(
    client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    executor.fail["ba-001"] = "failed"
    run = start(client, chain, headless=True)
    assert worker.run_once() is True
    run = get(client, run["id"])
    assert run["status"] == "failed"
    assert run["failedNode"] == "n1"
    assert statuses(run) == ["failed", "skipped"]
    assert nodes(run)[1]["run"] is None
    assert worker.run_once() is False  # 下游沒有排入佇列
    assert [scene for scene, _ in executor.calls] == ["ba-001"]


def test_bound_value_against_the_rules_stops_before_the_browser(
    client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    """綁定的值要等上游通過才知道；不符合下游入參的規則時，下游不啟動瀏覽器就停下。"""
    definition = {
        "nodes": [
            cast("list[object]", CHAIN["nodes"])[0],
            {
                "id": "n2",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"node": "n1", "output": "title"}},
            },
        ]
    }
    body(client.put(f"/api/workflows/{chain}", json={"baseVersion": 1, "definition": definition}))
    run = start(client, chain, headless=True)
    worker.run_once()
    run = get(client, run["id"])
    assert run["status"] == "failed"
    assert run["failedNode"] == "n2"
    assert statuses(run) == ["passed", "failed"]
    second = nodes(run)[1]
    assert second["run"] is None
    assert "recordId" in str(second["error"])
    assert worker.run_once() is False
    assert len(executor.calls) == 1


def test_cancel_stops_the_current_node(
    client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    run = start(client, chain, headless=True)
    cancelled = body(client.post(f"/api/workflow-runs/{run['id']}/cancel"), 202)
    assert cancelled["status"] == "cancelled"
    assert statuses(cancelled) == ["cancelled", "skipped"]
    assert cancelled["failedNode"] == "n1"
    assert worker.run_once() is False
    assert executor.calls == []
    # 結束後再取消：不變
    assert body(client.post(f"/api/workflow-runs/{run['id']}/cancel"), 202)["status"] == "cancelled"


def test_cannot_run_with_problems_or_delete_while_running(
    app: FastAPI, client: Client, chain: int
) -> None:
    empty = body(client.post("/api/workflows", json={"name": "空的"}), 201)
    refused = client.post(f"/api/workflows/{empty['id']}/runs", json={})
    assert error(refused, 422)["code"] == "workflow_invalid"

    alone = {"nodes": [{"id": "n1", "sceneId": "ba-002", "revision": 1}]}
    body(client.put(f"/api/workflows/{empty['id']}", json={"baseVersion": 1, "definition": alone}))
    refused = client.post(f"/api/workflows/{empty['id']}/runs", json={})
    problems = cast("list[JsonObject]", error(refused, 422)["problems"])
    assert [p["code"] for p in problems] == ["workflow.input_missing"]

    services(app).display = False
    headed = client.post(f"/api/workflows/{chain}/runs", json={"headless": False})
    assert error(headed, 422)["code"] == "display_unavailable"

    key = {"idempotencyKey": "same-click"}
    first = start(client, chain, **key)
    assert first["headless"] is True  # 沒有圖形介面時用無頭模式
    assert start(client, chain, **key)["id"] == first["id"]
    busy = client.delete(f"/api/workflows/{chain}")
    assert error(busy, 409)["code"] == "workflow_running"


def test_pinned_revision_stays_after_a_new_publish(
    app: FastAPI, client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    files = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    body(
        client.post(
            "/api/scenes/ba-001/revisions",
            json={"baseRevision": 1, "files": {"scenario.yaml": files["scenario.yaml"] + "\n"}},
        ),
        201,
    )
    publish(app, "ba-001", 2)
    library = cast("list[JsonObject]", body(client.get("/api/workflows/library"))["scenes"])
    scene = next(item for item in library if item["id"] == "ba-001")
    assert scene["publishedRevision"] == 2
    assert [r["number"] for r in cast("list[JsonObject]", scene["revisions"])] == [2, 1]

    run = start(client, chain, headless=True)
    worker.run_once()
    assert node_run(nodes(get(client, run["id"]))[0])["revision"] == 1

    # 沒發布過的版本不能當成序列的節點執行
    body(
        client.post(
            "/api/scenes/ba-001/revisions",
            json={"baseRevision": 2, "files": {"scenario.yaml": files["scenario.yaml"]}},
        ),
        201,
    )
    with pytest.raises(ServiceError) as raised:
        services(app).request_run("ba-001", purpose="workflow", number=3)
    assert (raised.value.status, raised.value.code) == (409, "revision_unpublished")


def test_server_restart_settles_interrupted_sequences(
    app: FastAPI, client: Client, chain: int
) -> None:
    run = start(client, chain, headless=True)
    job = cast("Worker", app.state.worker).source.claim()  # n1 開始執行後伺服器停了
    assert job is not None
    assert services(app).recover() == 1
    run = get(client, run["id"])
    assert run["status"] == "failed"
    assert run["failedNode"] == "n1"
    assert statuses(run) == ["failed", "skipped"]


def graph_definition() -> JsonObject:
    """非線性菱形圖：儲存順序與執行順序不同，匯合處同時使用兩個分支的值。"""
    return {
        "version": 2,
        "mode": "dag",
        "nodes": [
            {
                "id": "join",
                "sceneId": "ba-001",
                "revision": 1,
                "inputs": {
                    "title": {"node": "left", "output": "title"},
                    "quantity": {"node": "right", "output": "quantity"},
                },
            },
            {
                "id": "right",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"auto": True}},
            },
            {
                "id": "left",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"node": "root", "output": "recordId"}},
            },
            {
                "id": "root",
                "sceneId": "ba-001",
                "revision": 1,
                "position": {"x": 720, "y": 90},
                "inputs": {"title": {"value": "DAG"}, "quantity": {"value": 3}},
            },
        ],
        "edges": [
            {"source": "root", "target": "right"},
            {"source": "root", "target": "left"},
            {"source": "left", "target": "join"},
            {"source": "right", "target": "join"},
        ],
    }


def test_dag_execution_snapshot_fork_join_and_duplicate_notifications(
    app: FastAPI, client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    graph = graph_definition()
    saved = body(
        client.put(f"/api/workflows/{chain}", json={"baseVersion": 1, "definition": graph})
    )
    assert saved["problems"] == []
    run = start(client, chain, headless=True)
    assert [node["id"] for node in nodes(run)] == ["root", "right", "left", "join"]
    assert statuses(run) == ["queued", "pending", "pending", "pending"]
    # 開始之後修改編排不會改變本次執行；快照中的同名匹配已固定成具體來源。
    body(client.put(f"/api/workflows/{chain}", json={"baseVersion": 2, "definition": {}}))
    for _ in range(4):
        assert worker.run_once()
        finished = get(client, run["id"])
        previous = [node_run(node) for node in nodes(finished) if node["status"] == "passed"]
        if previous:
            services(app).workflows.node_finished(str(previous[-1]["id"]))
    finished = get(client, run["id"])
    assert finished["status"] == "passed"
    assert not worker.run_once()
    assert len(executor.calls) == 4
    first, right, left, join = [node_run(node) for node in nodes(finished)]
    assert (
        right["input"]
        == left["input"]
        == {"recordId": cast("JsonObject", first["output"])["recordId"]}
    )
    assert join["input"] == {
        "title": cast("JsonObject", left["output"])["title"],
        "quantity": cast("JsonObject", right["output"])["quantity"],
    }
    sources = cast("JsonObject", nodes(finished)[1]["sources"])
    assert cast("JsonObject", sources["recordId"])["node"] == "root"


def test_dag_failure_resume_uses_topological_prefix(
    client: Client, chain: int, worker: Worker, executor: FakeExecutor
) -> None:
    body(
        client.put(
            f"/api/workflows/{chain}", json={"baseVersion": 1, "definition": graph_definition()}
        )
    )
    executor.fail["ba-002"] = "failed"
    run = start(client, chain, headless=True)
    assert worker.run_once()
    assert worker.run_once()
    stopped = get(client, run["id"])
    assert statuses(stopped) == ["passed", "failed", "skipped", "skipped"]
    assert stopped["failedNode"] == "right"
    assert not worker.run_once()
    executor.fail.clear()
    resumed = body(client.post(f"/api/workflow-runs/{run['id']}/rerun", json={"resume": True}), 202)
    assert statuses(resumed) == ["reused", "queued", "pending", "pending"]
    for _ in range(3):
        assert worker.run_once()
    assert get(client, resumed["id"])["status"] == "passed"
    assert len([call for call in executor.calls if call[1].get("title") == "DAG"]) == 1


def test_dag_invalid_draft_is_saved_but_never_queued(
    client: Client, chain: int, worker: Worker
) -> None:
    graph = graph_definition()
    cast("list[JsonObject]", graph["edges"]).append({"source": "join", "target": "root"})
    saved = body(
        client.put(f"/api/workflows/{chain}", json={"baseVersion": 1, "definition": graph})
    )
    assert "workflow.cycle" in [p["code"] for p in cast("list[JsonObject]", saved["problems"])]
    assert client.post(f"/api/workflows/{chain}/runs", json={"headless": True}).status_code == 422
    assert not worker.run_once()
    assert body(client.get("/api/workflow-runs"))["runs"] == []


def test_composite_management_and_navigation(client: Client, chain: int) -> None:
    html = client.get("/composites").text
    assert 'scene-card composite-card"' in html
    assert 'data-action="run-composite"' in html
    assert 'class="preview-edge"' in html
    assert 'href="/playground/' + str(chain) + '"' in html
    side = html.split('id="sidenav"')[1].split("</nav>")[0]
    assert side.index("/roles") < side.index("/composites")
    production = client.get("/playground").text.split('id="sidenav"')[1].split("</nav>")[0]
    assert (
        production.index("/recording") < production.index("/playground") < production.index("/runs")
    )
    assert 'data-action="delete-workflow"' not in client.get("/playground").text
