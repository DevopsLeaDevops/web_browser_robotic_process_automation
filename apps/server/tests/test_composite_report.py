"""組合運行的匯總報告（2026-10-27，任務 20261027-composite-report-replay）：不需要瀏覽器。

假的執行器照 runner 的做法留下場景快照、步驟紀錄、截圖與 result.json；可以指定哪個場景在第幾步失敗。
驗證報告的資料（API）、組合運行頁、下載的離線報告與 Agent API 的版本。
"""

import shutil
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_core.dsl import validate_file
from rpa_core.i18n import use_locale
from rpa_runner.browser import plan_records
from rpa_runner.contract import CheckResult, check_inputs
from rpa_runner.files import REPORT, RESULT, SCENARIO_DIR, SCREENSHOT, STEPS, write_json
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, Stage, StageName
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Revision, Scene
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]
PNG = b"\x89PNG\r\n\x1a\n" + b"report-test" * 8
WORKER_PORT = 8081

THREE: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "報告"}}},
        {
            "id": "n2",
            "sceneId": "ba-002",
            "revision": 1,
            "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
        },
        {"id": "n3", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "後續"}}},
    ],
    "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
}


class ReportExecutor:
    """假的執行器：每一步 0.1 秒；``fail`` 指定的場景在那一步（從 0 起算）失敗。"""

    def __init__(self) -> None:
        self.fail: dict[str, int] = {}

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
        record_video: bool = False,
        **_files: object,
    ) -> RunResult:
        scenario = validate_file(path).scenario
        assert scenario is not None
        assert run_id is not None
        resolved, problems = check_inputs(scenario, inputs)
        assert problems == []
        folder = out_root / run_id
        (folder / SCENARIO_DIR).mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, folder / SCENARIO_DIR / "scenario.yaml")
        records = plan_records(scenario)
        fail_at = self.fail.get(scenario.id)
        status = "passed"
        for index, record in enumerate(records):
            if fail_at is not None and index > fail_at:
                break
            record.status = "passed"
            record.duration_ms = 100
            if index == fail_at:
                record.status = "failed"
                record.error = "TimeoutError: 找不到「查詢」按鈕"
                status = "failed"
        write_json(folder / STEPS, [record.to_json() for record in records])
        (folder / SCREENSHOT).write_bytes(PNG)
        passed = status == "passed"
        fixed = "DEMO-" + scenario.id.upper().replace("-", "")
        result = RunResult(
            run_id=run_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_hash="0" * 64,
            kind="dsl",
            engine=engine or scenario.browser.engine,
            directory=folder,
            started_at=now().isoformat(),
            status=status,  # pyright: ignore[reportArgumentType]
            duration_seconds=1.5,
            input=resolved,
            output=(
                {
                    name: resolved.get(name, fixed if spec.type == "string" else 1)
                    for name, spec in scenario.outputs.items()
                }
                if passed
                else None
            ),
            stages=[
                Stage("input", "passed"),
                Stage(
                    "automation", "passed" if passed else "failed", None if passed else "步驟失敗"
                ),
                Stage("verify", "passed" if passed else "skipped"),
            ],
            steps=[record.to_json() for record in records],
            checks=[CheckResult("紀錄編號", "matches", fixed, "^DEMO-", True)] if passed else [],
            error=None if passed else "自動化失敗：第 2 步 search",
        )
        write_json(folder / RESULT, result.to_json())
        (folder / REPORT).write_text("<html><body><p>節點報告</p></body></html>", encoding="utf-8")
        return result


@pytest.fixture
def settings(settings: Settings) -> Settings:
    from dataclasses import replace

    return replace(settings, worker_port=WORKER_PORT, worker_host="192.168.1.10")


@pytest.fixture
def executor() -> ReportExecutor:
    return ReportExecutor()


@pytest.fixture
def worker(app: FastAPI, executor: ReportExecutor) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def items(data: JsonObject, key: str) -> list[JsonObject]:
    return cast("list[JsonObject]", data[key])


def publish(app: FastAPI, scene_id: str) -> None:
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


def drain(worker: Worker) -> None:
    while worker.run_once():
        pass


def start(app: FastAPI, client: Client) -> str:
    """建立三個節點的組合場景（n1 → n2 → n3）並開始執行，回傳組合運行的編號。"""
    assert client.post("/api/scenes/import").status_code < 400
    publish(app, "ba-001")
    publish(app, "ba-002")
    body(client.post("/api/projects", json={"id": "qa", "name": "回歸測試"}), 201)
    created = body(
        client.post(
            "/api/workflows", json={"name": "報告測試", "definition": THREE, "projectId": "qa"}
        ),
        201,
    )
    run = body(client.post(f"/api/workflows/{created['id']}/runs", json={}), 202)
    return str(run["id"])


def test_report_explains_where_the_run_stopped(
    app: FastAPI, client: Client, worker: Worker, executor: ReportExecutor
) -> None:
    executor.fail["ba-002"] = 2  # 第 3 步 search 失敗
    run_id = start(app, client)

    running = body(client.get(f"/api/workflow-runs/{run_id}/report"))
    assert running["status"] == "running"
    assert (running["active"], running["failure"]) == (["n1", "n2", "n3"], None)

    drain(worker)
    report = body(client.get(f"/api/workflow-runs/{run_id}/report"))
    assert report["status"] == "failed"
    counts = cast("JsonObject", report["counts"])
    assert counts["nodes"] == {"passed": 1, "total": 3}
    assert counts["checks"] == {"passed": 1, "total": 1}
    steps = cast("dict[str, int]", counts["steps"])
    assert steps["passed"] == steps["total"] - 1 - 3  # 失敗的一步、後面三步沒有執行
    assert report["skipped"] == ["n3"]

    failure = cast("JsonObject", report["failure"])
    assert failure["node"] == "n2"
    step = cast("JsonObject", failure["step"])
    assert (step["index"], step["id"], step["action"]) == (3, "search", "click")
    assert step["error"] == "TimeoutError: 找不到「查詢」按鈕"
    assert step["target"] == "{ role: button, name: 查詢, exact: true }"  # 場景檔的寫法

    first, second, third = items(report, "nodes")
    recorded = {item["name"]: item for item in cast("list[JsonObject]", first["outputs"])}
    assert recorded["recordId"] == {
        "name": "recordId",
        "value": "DEMO-BA001",
        "hasValue": True,
        "to": ["n2.recordId"],
    }
    assert second["inputs"] == [
        {
            "name": "recordId",
            "value": "DEMO-BA001",
            "hasValue": True,
            "given": True,
            "source": {"kind": "output", "node": "n1", "output": "recordId", "value": None},
        }
    ]
    assert (first["open"], second["open"], third["open"]) == (False, True, False)
    assert second["screenshotUrl"] == f"/runs/{second['runId']}/files/{SCREENSHOT}"
    assert (third["status"], third["runId"]) == ("skipped", None)
    timeline = cast("JsonObject", report["timeline"])
    assert [bar["id"] for bar in cast("list[JsonObject]", timeline["bars"])] == ["n1", "n2"]

    page = client.get(f"/playground/runs/{run_id}").text
    assert "停在 n2「查詢範例紀錄」" in page
    assert "TimeoutError: 找不到「查詢」按鈕" in page
    assert f'src="/runs/{second["runId"]}/files/screenshot.png"' in page
    assert 'data-node="n2" data-status="failed" open>' in page
    assert "n3 沒有執行（上游沒有通過）" in page
    assert 'class="creport-dag-node red" data-status="failed"' in page
    assert f'href="/playground/runs/{run_id}/report.html"' in page

    # 下載的離線報告：單一 HTML，只嵌入沒通過的節點的截圖，沒有連到 Portal 的連結
    download = client.get(f"/playground/runs/{run_id}/report.html")
    assert download.status_code == 200
    assert f'filename="{run_id}-report.html"' in download.headers["content-disposition"]
    offline = download.text
    assert offline.count("data:image/png;base64,") == 2  # n2 的截圖：結論與節點明細各一次
    assert 'href="/' not in offline
    assert 'src="/' not in offline
    assert "停在 n2「查詢範例紀錄」" in offline
    assert "下載的報告只放沒通過的節點的截圖" in offline  # n1 有截圖但沒有嵌入

    # 節點自己的報告在 Portal 打開時，上方的連結列連回整次組合運行
    node_report = client.get(f"/runs/{second['runId']}/files/report.html").text
    assert f'href="/playground/runs/{run_id}">整次組合運行的報告（這是節點 n2）' in node_report

    with use_locale("en"):
        client.cookies.set("rpa_lang", "en")
        english = client.get(f"/playground/runs/{run_id}").text
    assert "Stopped at n2" in english


def test_report_marks_reused_nodes_after_resuming(
    app: FastAPI, client: Client, worker: Worker, executor: ReportExecutor
) -> None:
    executor.fail["ba-002"] = 0
    first = start(app, client)
    drain(worker)
    executor.fail.clear()
    resumed = body(client.post(f"/api/workflow-runs/{first}/rerun", json={"resume": True}), 202)
    drain(worker)

    report = body(client.get(f"/api/workflow-runs/{resumed['id']}/report"))
    assert report["status"] == "passed"
    assert cast("JsonObject", report["counts"])["reused"] == 1
    reused = items(report, "nodes")[0]
    assert (reused["status"], reused["reusedFrom"]) == ("reused", first)
    assert reused["reusedUrl"] == f"/playground/runs/{first}"
    bars = cast("list[JsonObject]", cast("JsonObject", report["timeline"])["bars"])
    assert [bar["id"] for bar in bars] == ["n2", "n3"]  # 沿用的節點這次沒有執行

    page = client.get(f"/playground/runs/{resumed['id']}").text
    assert "3 個節點全部通過" in page
    assert "1 個節點沿用上一次通過的結果" in page
    assert f'href="/playground/runs/{first}"' in page


def test_agent_reads_the_report_with_its_own_links(
    app: FastAPI, client: Client, worker: Worker, executor: ReportExecutor
) -> None:
    executor.fail["ba-002"] = 2
    run_id = start(app, client)
    drain(worker)
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as remote:
        headers: dict[str, str] = {}
        for agent_id, content in (("agent-text", False), ("agent-pages", True)):
            created = body(
                client.post(
                    "/api/agents",
                    json={
                        "id": agent_id,
                        "name": agent_id,
                        "policy": {"scopes": ["runs:read"], "pageContent": content},
                    },
                ),
                201,
            )
            headers = {"Authorization": f"Bearer {created['key']}"}
            run = body(remote.get(f"/agent-api/v1/composite-runs/{run_id}", headers=headers))
            assert run["reportUrl"] == f"/agent-api/v1/composite-runs/{run_id}/report"
            assert run["replayPath"] == f"/playground/runs/{run_id}/replay"
            report = body(remote.get(str(run["reportUrl"]), headers=headers))
            assert cast("JsonObject", report["failure"])["node"] == "n2"
            assert report["portalPath"] == f"/playground/runs/{run_id}"
            second = items(report, "nodes")[1]
            assert second["portalPath"] == f"/runs/{second['runId']}"
            assert "runUrl" not in second
            assert "replayUrl" not in second
            files = f"/agent-api/v1/runs/{second['runId']}/files/"
            if content:
                assert second["screenshotUrl"] == files + SCREENSHOT
                assert second["reportUrl"] == files + "report.html"
                shot = remote.get(str(second["screenshotUrl"]), headers=headers)
                assert shot.content == PNG
            else:
                assert (second["screenshotUrl"], second["reportUrl"]) == (None, None)
        missing = remote.get("/agent-api/v1/composite-runs/nope/report", headers=headers)
        assert missing.status_code == 404


def test_runs_page_lists_composite_runs(
    app: FastAPI, client: Client, worker: Worker, executor: ReportExecutor
) -> None:
    """運行報告的「組合運行」檢視：一列一次組合運行、可以篩選；場景運行檢視裡的節點連到組合運行。"""
    executor.fail["ba-002"] = 2
    run_id = start(app, client)
    drain(worker)

    page = client.get("/runs", params={"view": "composite"}).text
    assert f'data-workflow-run="{run_id}"' in page
    assert f'href="/playground/runs/{run_id}"' in page
    assert "回歸測試" in page  # 組合場景所在的專案
    assert "停在 n2" in page
    assert 'name="view" value="composite"' in page  # 篩選時留在這個檢視
    assert 'name="project" value="qa"' in page
    filtered = client.get("/runs", params={"view": "composite", "status": "passed"}).text
    assert f'data-workflow-run="{run_id}"' not in filtered
    assert "沒有符合條件的組合運行" in filtered
    composite_id = body(client.get(f"/api/workflow-runs/{run_id}"))["workflowId"]
    chosen = client.get("/runs", params={"view": "composite", "composite": str(composite_id)})
    assert f'data-workflow-run="{run_id}"' in chosen.text

    scenes = client.get("/runs").text
    assert f'<a class="mono" href="/playground/runs/{run_id}">{run_id}</a> · n2' in scenes
