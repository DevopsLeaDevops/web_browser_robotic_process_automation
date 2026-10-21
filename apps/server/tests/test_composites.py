"""組合場景放進領域資料夾（M11 PR 2）：版本、驗證紀錄、發布門檻、依賴檢查、重新載入、遷移。

節點的執行換成假的執行器（不開瀏覽器），回報的場景雜湊依磁碟上的版本計算，驗證紀錄才能
證明「節點跑的就是釘住的場景版本」。
"""

import json
import shutil
import stat
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
from rpa_core.dsl.sources import scenario_digest
from rpa_core.pack import (
    CompositeManifest,
    CompositeRevisionInfo,
    CompositeVerification,
    check_requirements,
    read_model,
    read_pack,
    workflow_digest,
)
from rpa_core.workflow import Workflow
from rpa_runner.contract import check_inputs
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_server.app import create_app
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Revision, Scene, Setting, WorkflowRevision
from rpa_server.models import Workflow as WorkflowRow
from rpa_server.packs import RUN_MANIFEST
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]

CHAIN: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "組合"}}},
        # 同名匹配：執行的快照會解析出來源，雜湊和版本不同（驗證紀錄仍要記版本的雜湊）
        {"id": "n2", "sceneId": "ba-002", "revision": 1, "inputs": {"recordId": {"auto": True}}},
    ],
    "edges": [{"source": "n1", "target": "n2"}],
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
def worker(app: FastAPI) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int | None = None) -> JsonObject:
    if status is not None:
        assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict), response.text
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def publish(app: FastAPI, scene_id: str) -> None:
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


def _writable(function: Callable[[str], object], path: str, _error: BaseException) -> None:
    """刪除資料夾時遇到唯讀的版本檔案：改成可寫再刪。"""
    Path(path).chmod(stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
    function(path)


def import_examples(app: FastAPI, client: Client) -> None:
    """範例場景放進「實驗」領域，發布 BA-001 與 BA-002。"""
    assert client.post("/api/domains", json={"id": "lab", "name": "實驗"}).status_code == 201
    body(client.post("/api/scenes/import", json={"domainId": "lab"}))
    publish(app, "ba-001")
    publish(app, "ba-002")


def composite_dir(settings: Settings, code: str, domain_id: str = "composites") -> Path:
    return settings.data_dir / "domains" / domain_id / "composites" / code


@pytest.fixture
def chain(app: FastAPI, client: Client) -> JsonObject:
    """建立「BA-001 → BA-002」的組合場景（沒指定領域：放「組合場景」領域）。"""
    import_examples(app, client)
    return body(
        client.post("/api/workflows", json={"name": "建立後查詢", "definition": CHAIN}), 201
    )


def run_to_end(client: Client, worker: Worker, workflow_id: object, **options: object) -> str:
    started = body(client.post(f"/api/workflows/{workflow_id}/runs", json=options), 202)
    while worker.run_once():
        pass
    run = body(client.get(f"/api/workflow-runs/{started['id']}"))
    assert run["status"] == "passed", run
    return str(run["id"])


# ---------------------------------------------------------------- 資料夾與版本


def test_create_writes_the_folder_and_saving_adds_revisions(
    app: FastAPI, client: Client, settings: Settings, chain: JsonObject
) -> None:
    assert (chain["code"], chain["domainId"]) == ("wf-1", "composites")
    assert (chain["latestRevision"], chain["publishedRevision"]) == (1, None)
    folder = composite_dir(settings, "wf-1")
    manifest, _ = read_model(folder / "composite.yaml", CompositeManifest)
    assert manifest is not None
    assert (manifest.id, manifest.name, manifest.published) == ("wf-1", "建立後查詢", None)
    info, issues = read_model(folder / "revisions" / "1.yaml", CompositeRevisionInfo)
    assert info is not None, issues
    workflow = Workflow.model_validate(chain["definition"])
    assert info.hash == workflow_digest(workflow)
    assert [(item.domain, item.scene, item.revision) for item in info.requires] == [
        ("lab", "ba-001", 1),
        ("lab", "ba-002", 1),
    ]
    # 用到的其他領域寫進 pack.yaml 的 requires
    pack = read_pack(settings.data_dir / "domains" / "composites", expected_id="composites")
    assert pack.ok, pack.issues
    assert pack.manifest is not None
    assert [item.domain for item in pack.manifest.requires] == ["lab"]
    assert list(pack.composites) == ["wf-1"]

    # 改名不分版本；改定義是新版本
    renamed = body(
        client.put(f"/api/workflows/{chain['id']}", json={"baseVersion": 1, "name": "改名"})
    )
    assert renamed["latestRevision"] == 1
    manifest, _ = read_model(folder / "composite.yaml", CompositeManifest)
    assert manifest is not None
    assert manifest.name == "改名"
    alone = {"nodes": [{"id": "n1", "sceneId": "ba-001", "revision": 1}]}
    saved = body(
        client.put(f"/api/workflows/{chain['id']}", json={"baseVersion": 1, "definition": alone})
    )
    assert saved["latestRevision"] == 2
    assert (folder / "revisions" / "2" / "workflow.json").is_file()
    assert (folder / "revisions" / "1" / "workflow.json").is_file()  # 舊版本保留
    detail = body(client.get(f"/api/workflows/{chain['id']}"))
    revisions = cast("list[JsonObject]", detail["revisions"])
    assert [(item["number"], item["status"]) for item in revisions] == [(2, "draft"), (1, "draft")]

    # 自訂代號與領域；代號不能重複
    custom = body(
        client.post(
            "/api/workflows",
            json={"name": "自訂", "code": "order-flow", "domainId": "lab", "definition": CHAIN},
        ),
        201,
    )
    assert (custom["code"], custom["domainId"]) == ("order-flow", "lab")
    assert (composite_dir(settings, "order-flow", "lab") / "composite.yaml").is_file()
    again = client.post("/api/workflows", json={"name": "重複", "code": "order-flow"})
    assert error(again, 409)["code"] == "workflow_code_exists"
    bad = client.post("/api/workflows", json={"name": "壞的", "code": "壞 代號"})
    assert error(bad, 422)["code"] == "workflow_code_invalid"

    # 刪除連同資料夾
    assert body(client.delete(f"/api/workflows/{custom['id']}")) == {"deleted": custom["id"]}
    assert not composite_dir(settings, "order-flow", "lab").exists()


def test_validation_record_publish_gate_and_execution(
    app: FastAPI, client: Client, settings: Settings, chain: JsonObject, worker: Worker
) -> None:
    workflow_id = chain["id"]
    # 沒有驗證過不能發布，也不能用執行的目的跑
    refused = client.post(f"/api/workflows/{workflow_id}/revisions/1/publish")
    assert error(refused, 409)["code"] == "workflow_not_validated"
    unpublished = client.post(f"/api/workflows/{workflow_id}/runs", json={"purpose": "execution"})
    assert error(unpublished, 409)["code"] == "workflow_unpublished"

    run_id = run_to_end(client, worker, workflow_id, headless=True)
    folder = composite_dir(settings, "wf-1")
    record, issues = read_model(
        folder / "verifications" / "1" / f"{run_id}.yaml", CompositeVerification
    )
    assert record is not None, issues
    assert (record.revision, record.status) == (1, "passed")
    assert [(node.node, node.scene, node.status) for node in record.nodes] == [
        ("n1", "ba-001", "passed"),
        ("n2", "ba-002", "passed"),
    ]
    manifest = json.loads(
        (settings.data_dir / "workflow-runs" / run_id / RUN_MANIFEST).read_text("utf-8")
    )
    assert (manifest["composite"], manifest["revision"], manifest["purpose"]) == (
        "wf-1",
        1,
        "validation",
    )

    detail = body(client.get(f"/api/workflows/{workflow_id}"))
    verifications = cast("list[JsonObject]", detail["verifications"])
    assert [(item["id"], item["proof"]) for item in verifications] == [(run_id, True)]
    revision = cast("list[JsonObject]", detail["revisions"])[0]
    assert (revision["status"], revision["verified"]) == ("passed", True)

    published = body(client.post(f"/api/workflows/{workflow_id}/revisions/1/publish"))
    assert published["publishedRevision"] == 1
    manifest_file, _ = read_model(folder / "composite.yaml", CompositeManifest)
    assert manifest_file is not None
    assert manifest_file.published is not None
    assert (manifest_file.published.revision, manifest_file.published.verification) == (1, run_id)

    executed = run_to_end(client, worker, workflow_id, purpose="execution", headless=True)
    # 執行不寫驗證紀錄
    assert not (folder / "verifications" / "1" / f"{executed}.yaml").exists()
    run = body(client.get(f"/api/workflow-runs/{executed}"))
    assert (run["purpose"], run["workflowCode"], run["workflowVersion"]) == (
        "execution",
        "wf-1",
        1,
    )

    pack = read_pack(settings.data_dir / "domains" / "composites", expected_id="composites")
    lab = read_pack(settings.data_dir / "domains" / "lab", expected_id="lab")
    check_requirements([pack, lab])
    assert pack.ok, pack.issues
    assert lab.ok, lab.issues
    assert 'id="composite-revisions"' in client.get(f"/playground/{workflow_id}").text


def test_dependencies_block_a_changed_scene_revision(
    app: FastAPI, client: Client, settings: Settings, chain: JsonObject
) -> None:
    detail = body(client.get(f"/api/workflows/{chain['id']}"))
    assert detail["dependency"] in ("complete", "warnings")
    assert all(
        item["level"] != "error" for item in cast("list[JsonObject]", detail["dependencies"])
    )

    # 釘住的場景版本內容變了（例如別人推送了不同的檔案）：依賴不完整，不能執行
    with services(app).sessions() as session:
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == "ba-002", Revision.number == 1)
        ).one()
        revision.content_hash = "f" * 64
        session.commit()
    detail = body(client.get(f"/api/workflows/{chain['id']}"))
    assert detail["dependency"] == "incomplete"
    items = cast("list[JsonObject]", detail["dependencies"])
    assert [
        (item["code"], item["scene"], item["action"]) for item in items if item["level"] == "error"
    ] == [("dependency.hash_mismatch", "ba-002", "resave")]
    refused = client.post(f"/api/workflows/{chain['id']}/runs", json={"headless": True})
    problems = cast("list[JsonObject]", error(refused, 422)["problems"])
    assert "dependency.hash_mismatch" in [p["code"] for p in problems]
    assert "依賴" in client.get("/composites").text

    # 有組合場景的領域不能刪
    assert error(client.delete("/api/domains/composites"), 409)["code"] == "domain_has_composites"


def test_code_domain_and_archive_can_change(
    app: FastAPI, client: Client, settings: Settings, chain: JsonObject, worker: Worker
) -> None:
    """改代號、搬到其他領域、封存（M11 收尾）：資料夾跟著改名或搬走，版本與驗證紀錄都在。"""
    workflow_id = chain["id"]
    run_to_end(client, worker, workflow_id, headless=True)  # 留一份驗證紀錄
    renamed = body(client.patch(f"/api/workflows/{workflow_id}", json={"code": "order-flow"}))
    assert renamed["code"] == "order-flow"
    assert not composite_dir(settings, "wf-1").exists()
    folder = composite_dir(settings, "order-flow")
    manifest, _ = read_model(folder / "composite.yaml", CompositeManifest)
    assert manifest is not None
    assert manifest.id == "order-flow"
    assert list((folder / "verifications" / "1").glob("*.yaml"))

    moved = body(client.patch(f"/api/workflows/{workflow_id}", json={"domainId": "lab"}))
    assert moved["domainId"] == "lab"
    assert not folder.exists()
    folder = composite_dir(settings, "order-flow", "lab")
    assert (folder / "revisions" / "1" / "workflow.json").is_file()
    detail = body(client.get(f"/api/workflows/{workflow_id}"))
    assert cast("list[JsonObject]", detail["verifications"])  # 驗證紀錄跟著搬
    lab = read_pack(settings.data_dir / "domains" / "lab", expected_id="lab")
    assert lab.ok, lab.issues
    assert list(lab.composites) == ["order-flow"]

    archived = body(client.patch(f"/api/workflows/{workflow_id}", json={"archived": True}))
    assert archived["archived"] is True
    manifest, _ = read_model(folder / "composite.yaml", CompositeManifest)
    assert manifest is not None
    assert manifest.archived is True
    refused = client.post(f"/api/workflows/{workflow_id}/runs", json={"headless": True})
    assert error(refused, 409)["code"] == "workflow_archived"
    assert "composite.archived" not in client.get("/composites").text
    assert "已封存" in client.get("/composites").text
    body(client.patch(f"/api/workflows/{workflow_id}", json={"archived": False}))

    # 重新載入：從資料夾認得新的代號與領域
    body(client.post("/api/domains/lab/reload"))
    reloaded = body(client.get(f"/api/workflows/{workflow_id}"))
    assert (reloaded["code"], reloaded["domainId"]) == ("order-flow", "lab")
    bad = client.patch(f"/api/workflows/{workflow_id}", json={"code": "壞 代號"})
    assert error(bad, 422)["code"] == "workflow_code_invalid"
    other = body(client.post("/api/workflows", json={"name": "另一個", "definition": CHAIN}), 201)
    taken = client.patch(f"/api/workflows/{other['id']}", json={"code": "order-flow"})
    assert error(taken, 409)["code"] == "workflow_code_exists"
    missing = client.patch(f"/api/workflows/{workflow_id}", json={"domainId": "nope"})
    assert error(missing, 404)["code"] == "domain_not_found"

    # 驗證指定的版本；領域管理頁列出依賴 lab 的組合場景
    page = client.get(f"/playground/{workflow_id}").text
    assert 'data-action="validate-composite"' in page
    assert 'id="composite-settings"' in page
    dependents = client.get("/domains").text.split("data-dependents")
    assert len(dependents) == 2  # 只有 lab：被組合場景領域的另一個依賴
    used = dependents[1].split("</span>")[0]
    assert other["code"] in used
    assert "order-flow" not in used  # 在 lab 裡、只用 lab 的場景，不算依賴別的領域


def test_reload_picks_up_and_loses_composite_folders(
    app: FastAPI, client: Client, settings: Settings, chain: JsonObject
) -> None:
    # 別台伺服器建立的組合場景：拉取後出現在資料夾裡
    source = composite_dir(settings, "wf-1")
    shutil.copytree(source, composite_dir(settings, "pulled"))
    pulled = composite_dir(settings, "pulled")
    manifest, _ = read_model(pulled / "composite.yaml", CompositeManifest)
    assert manifest is not None
    (pulled / "composite.yaml").chmod(0o644)
    (pulled / "composite.yaml").write_text(
        (pulled / "composite.yaml").read_text("utf-8").replace("id: wf-1", "id: pulled"), "utf-8"
    )
    body(client.post("/api/domains/composites/reload"))
    codes = {
        str(item["code"])
        for item in cast("list[JsonObject]", body(client.get("/api/workflows"))["workflows"])
    }
    assert codes == {"wf-1", "pulled"}

    # 資料夾被刪除（別人刪除後推送）：重新載入後列表不再出現
    shutil.rmtree(pulled, onexc=_writable)
    body(client.post("/api/domains/composites/reload"))
    codes = {
        str(item["code"])
        for item in cast("list[JsonObject]", body(client.get("/api/workflows"))["workflows"])
    }
    assert codes == {"wf-1"}


# ---------------------------------------------------------------- 遷移（格式 2 → 3）


def test_migration_moves_database_composites_into_the_folder(settings: Settings) -> None:
    data = settings.data_dir
    app = create_app(settings)
    with TestClient(app) as client:
        import_examples(app, client)
        created = body(
            client.post("/api/workflows", json={"name": "舊的組合場景", "definition": CHAIN}), 201
        )
        # 改回 M11 PR 2 之前的樣子：只有資料庫，格式版本 2
        with services(app).sessions() as session:
            row = session.get(WorkflowRow, created["id"])
            assert row is not None
            row.version = 4
            row.domain_id = None
            for item in session.scalars(select(WorkflowRevision)):
                session.delete(item)
            layout = session.get(Setting, "storage_layout")
            assert layout is not None
            layout.value = {**dict(layout.value), "version": 2}
            session.commit()
    shutil.rmtree(data / "domains" / "composites", onexc=_writable)

    with TestClient(create_app(settings)) as client:
        assert len(list((data / "backups").glob("*-before-composites"))) == 1
        folder = composite_dir(settings, "wf-1")
        info, issues = read_model(folder / "revisions" / "1.yaml", CompositeRevisionInfo)
        assert info is not None, issues
        assert "4" in (info.note or "")  # 說明記下原本的版本號碼
        detail = body(client.get(f"/api/workflows/{created['id']}"))
        assert (detail["code"], detail["domainId"], detail["latestRevision"]) == (
            "wf-1",
            "composites",
            1,
        )
        pack = read_pack(data / "domains" / "composites", expected_id="composites")
        assert pack.ok, pack.issues

    # 再啟動一次：不再遷移、不再備份
    with TestClient(create_app(settings)):
        assert len(list((data / "backups").glob("*-before-composites"))) == 1
