"""領域資料夾（M11）：伺服器代號、寫入資料夾、驗證與發布紀錄、重新載入、代號重複、遷移。

不需要瀏覽器：驗證用「缺少 Secret」讓執行停在入參階段（失敗也會寫紀錄）；通過的驗證紀錄
用「另一台伺服器推送來的紀錄」模擬（分散式驗證後發布，第 8 節）。
"""

import json
import shutil
import stat
from collections.abc import Callable
from datetime import timedelta
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
    PACK_FILE,
    PackManifest,
    RevisionInfo,
    SceneManifest,
    ServerRef,
    Verification,
    read_model,
    read_pack,
    write_model,
)
from rpa_server.app import create_app
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Revision, Role, Run, Scene, Setting
from rpa_server.packs import RUN_MANIFEST
from rpa_server.services import Services
from rpa_server.storage import SCENARIO_FILE, new_scene_template
from rpa_worker import Worker

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"

NEEDS_SECRET = """\
schemaVersion: 1
id: needs-secret
name: 缺少機密
secrets: [RPA_TEST_SECRET_NOT_SET]
browser:
  baseUrl: http://127.0.0.1:9
steps:
  - id: open
    action: goto
    url: /
"""

JsonObject = dict[str, object]


def body(response: Response) -> JsonObject:
    data: object = response.json()
    assert isinstance(data, dict), response.text
    return cast("JsonObject", data)


def error_code(response: Response) -> str:
    error = body(response)["error"]
    assert isinstance(error, dict)
    return str(cast("JsonObject", error)["code"])


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def worker(app: FastAPI) -> Worker:
    return cast("Worker", app.state.worker)


def pack_dir(settings: Settings, domain_id: str) -> Path:
    return settings.data_dir / "domains" / domain_id


def scene_dir(settings: Settings, domain_id: str, scene_id: str) -> Path:
    return pack_dir(settings, domain_id) / "scenes" / scene_id


def make_scene(client: Client, scene_id: str, domain_id: str, text: str | None = None) -> str:
    """建立場景；有 text 時把它存成 v2。回傳最新版本的雜湊。"""
    created = client.post(
        "/api/scenes", json={"id": scene_id, "name": "暫名", "domainId": domain_id}
    )
    assert created.status_code == 201, created.text
    if text is not None:
        saved = client.post(
            f"/api/scenes/{scene_id}/revisions",
            json={"baseRevision": 1, "files": {SCENARIO_FILE: text}, "note": "第二版"},
        )
        assert saved.status_code == 201, saved.text
    detail = body(client.get(f"/api/scenes/{scene_id}"))
    revisions = cast("list[JsonObject]", detail["revisions"])
    return str(revisions[0]["contentHash"])


def info_for(folder: Path, number: int) -> RevisionInfo:
    """別台伺服器（jia-mac）建立的版本說明檔：雜湊依磁碟上的內容計算。"""
    path = folder / "revisions" / str(number) / SCENARIO_FILE
    scenario = validate_file(path).scenario
    assert scenario is not None
    return RevisionInfo(
        number=number,
        hash=scenario_digest(path, scenario),
        created_at="2026-10-19T05:30:00-07:00",
        by="甲",
        server=ServerRef(id="3a9d", name="jia-mac"),
    )


def _writable(function: Callable[[str], object], path: str, _error: BaseException) -> None:
    """刪除資料夾時遇到唯讀的版本檔案：改成可寫再刪。"""
    Path(path).chmod(stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
    function(path)


def foreign_record(folder: Path, number: int, digest: str, *, status: str = "passed") -> str:
    """另一台伺服器（yi-mac）的驗證紀錄，像是拉取後出現在資料夾裡。"""
    run_id = f"{folder.name}-20261019-131500-a1b2c3"
    record = Verification.model_validate(
        {
            "revision": number,
            "hash": digest,
            "status": status,
            "startedAt": "2026-10-19T06:15:00-07:00",
            "finishedAt": "2026-10-19T06:15:42-07:00",
            "by": "乙",
            "server": {"id": "5f3a", "name": "yi-mac"},
            "worker": {"id": "win-01", "os": "windows"},
            "engine": "firefox",
            "headless": True,
            "run": {"server": "5f3a", "id": run_id},
        }
    )
    write_model(folder / "verifications" / str(number) / f"{run_id}.yaml", record)
    return run_id


@pytest.fixture
def lab(client: Client) -> str:
    assert client.post("/api/domains", json={"id": "lab", "name": "實驗"}).status_code == 201
    return "lab"


# ---------------------------------------------------------------- 伺服器代號


def test_server_has_an_id_and_a_name_that_can_change(app: FastAPI, client: Client) -> None:
    server = body(client.get("/api/settings/server"))
    assert len(str(server["id"])) == 32
    assert server["name"]

    renamed = body(client.put("/api/settings/server", json={"name": " jia-mac "}))
    blank = client.put("/api/settings/server", json={"name": " "})

    assert renamed == {"id": server["id"], "name": "jia-mac"}
    assert error_code(blank) == "server_name_missing"
    assert services(app).packs.server().name == "jia-mac"


# ---------------------------------------------------------------- 寫入資料夾


def test_domains_scenes_and_revisions_are_written_to_the_folder(
    app: FastAPI, client: Client, settings: Settings, lab: str
) -> None:
    client.put("/api/settings/server", json={"name": "jia-mac"})
    digest = make_scene(client, "ba-001", lab, (DEMO / "ba-001.yaml").read_text(encoding="utf-8"))
    client.patch(f"/api/domains/{lab}", json={"description": "實驗用"})

    manifest, _ = read_model(pack_dir(settings, lab) / PACK_FILE, PackManifest)
    assert manifest is not None
    assert (manifest.id, manifest.name, manifest.description) == (lab, "實驗", "實驗用")
    folder = scene_dir(settings, lab, "ba-001")
    scene, _ = read_model(folder / "scene.yaml", SceneManifest)
    assert scene == SceneManifest(id="ba-001")
    info, _ = read_model(folder / "revisions" / "2.yaml", RevisionInfo)
    assert info is not None
    assert (info.number, info.hash, info.by, info.note) == (2, digest, "jia-mac", "第二版")
    assert info.server.id == services(app).packs.server().id
    assert (folder / "revisions" / "1" / SCENARIO_FILE).is_file()
    pack = read_pack(pack_dir(settings, lab), expected_id=lab)
    assert pack.ok, pack.issues
    assert pack.scenes["ba-001"].latest == 2


def test_scene_without_domain_goes_to_unassigned_and_can_move(
    app: FastAPI, client: Client, settings: Settings, lab: str
) -> None:
    created = body(client.post("/api/scenes", json={"id": "loose", "name": "乙"}))
    assert created["domainId"] == "unassigned"
    assert (scene_dir(settings, "unassigned", "loose") / "scene.yaml").is_file()
    assert body(client.get("/api/domains/unassigned"))["name"] == "未分類"

    moved = body(client.patch("/api/scenes/loose", json={"domainId": lab, "archived": True}))

    assert moved["domainId"] == lab
    assert not scene_dir(settings, "unassigned", "loose").exists()
    scene, _ = read_model(scene_dir(settings, lab, "loose") / "scene.yaml", SceneManifest)
    assert scene is not None
    assert scene.archived
    assert services(app).storage.revision_dir("loose", 1).is_relative_to(pack_dir(settings, lab))


def test_deleting_a_domain_removes_its_folder(client: Client, settings: Settings, lab: str) -> None:
    client.post("/api/domains", json={"id": "spare", "name": "備用"})
    role = {
        "id": "lab-user",
        "name": "實驗帳號",
        "loginUrl": "https://example.test/login",
        "check": "{ testId: current-user }",
        "domainId": lab,
    }
    assert client.post("/api/roles", json=role).status_code == 201

    has_roles = client.delete(f"/api/domains/{lab}")
    assert (has_roles.status_code, error_code(has_roles)) == (409, "domain_has_roles")
    assert body(client.delete("/api/domains/spare")) == {"deleted": "spare"}
    assert not pack_dir(settings, "spare").exists()


# ---------------------------------------------------------------- 驗證與發布紀錄


def test_validation_writes_a_record_and_run_json(
    app: FastAPI, client: Client, settings: Settings, lab: str
) -> None:
    make_scene(client, "needs-secret", lab, NEEDS_SECRET)
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))
    worker(app).run_once()
    run_id = str(run["id"])

    path = scene_dir(settings, lab, "needs-secret") / "verifications" / "2" / f"{run_id}.yaml"
    record, issues = read_model(path, Verification)
    assert record is not None, issues
    assert (record.revision, record.status, record.worker.id) == (2, "failed", "local")
    assert record.run.id == run_id
    assert record.by == services(app).packs.server().name
    manifest = json.loads((settings.data_dir / "runs" / run_id / RUN_MANIFEST).read_text("utf-8"))
    assert (manifest["domain"], manifest["scene"], manifest["revision"]) == (lab, "needs-secret", 2)
    assert manifest["status"] == "failed"
    assert manifest["server"]["id"] == services(app).packs.server().id
    files = [item["path"] for item in manifest["files"]]
    assert RUN_MANIFEST not in files
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    listed = cast(
        "list[JsonObject]",
        body(client.get("/api/scenes/needs-secret/verifications"))["verifications"],
    )
    assert [(item["id"], item["here"], item["proof"]) for item in listed] == [(run_id, True, False)]
    assert "驗證紀錄" in client.get("/scenes/needs-secret").text


def test_publish_with_a_record_from_another_server(
    app: FastAPI, client: Client, settings: Settings, lab: str
) -> None:
    digest = make_scene(client, "needs-secret", lab, NEEDS_SECRET)
    folder = scene_dir(settings, lab, "needs-secret")
    early = client.post("/api/scenes/needs-secret/revisions/2/publish")
    assert error_code(early) == "not_validated"

    proof = foreign_record(folder, 2, digest)
    reloaded = body(client.post(f"/api/domains/{lab}/reload"))
    assert reloaded["applied"] is True
    revision = cast("list[JsonObject]", body(client.get("/api/scenes/needs-secret"))["revisions"])[
        0
    ]
    assert (revision["number"], revision["verified"]) == (2, True)

    published = client.post("/api/scenes/needs-secret/revisions/2/publish")

    assert published.status_code == 200, published.text
    assert body(published)["publishedRevision"] == 2
    scene, _ = read_model(folder / "scene.yaml", SceneManifest)
    assert scene is not None
    assert scene.published is not None
    assert (scene.published.revision, scene.published.verification) == (2, proof)
    assert scene.published.server.id == services(app).packs.server().id
    listed = cast(
        "list[JsonObject]",
        body(client.get("/api/scenes/needs-secret/verifications"))["verifications"],
    )
    assert [(item["server"], item["here"]) for item in listed] == [
        ({"id": "5f3a", "name": "yi-mac"}, False)
    ]
    # 重新載入後照樣是已發布（門檻在任何一台都一樣）
    client.post(f"/api/domains/{lab}/reload")
    assert body(client.get("/api/scenes/needs-secret"))["publishedRevision"] == 2


def test_published_record_without_proof_is_not_published(
    client: Client, settings: Settings, lab: str
) -> None:
    make_scene(client, "needs-secret", lab, NEEDS_SECRET)
    folder = scene_dir(settings, lab, "needs-secret")
    published = {
        "revision": 2,
        "verification": None,
        "at": "2026-10-19T06:40:00-07:00",
        "by": "丙",
        "server": {"id": "7c1e", "name": "bing-mac"},
    }
    manifest = SceneManifest.model_validate(
        {"id": "needs-secret", "published": published}, by_alias=True
    )
    write_model(folder / "scene.yaml", manifest)

    reloaded = body(client.post(f"/api/domains/{lab}/reload"))

    codes = [item["code"] for item in cast("list[JsonObject]", reloaded["issues"])]
    assert "pack.published_unverified" in codes
    assert body(client.get("/api/scenes/needs-secret"))["publishedRevision"] is None
    assert "沒有雜湊相符的通過驗證紀錄" in client.get(f"/domains/{lab}").text


# ---------------------------------------------------------------- 重新載入


def test_reload_picks_up_new_revisions_and_missing_scenes(
    client: Client, settings: Settings, lab: str
) -> None:
    make_scene(client, "keep", lab)
    make_scene(client, "gone", lab)
    folder = scene_dir(settings, lab, "keep")
    target = folder / "revisions" / "2"
    target.mkdir()
    text = new_scene_template("keep", "從別處推送的第二版", None)
    (target / SCENARIO_FILE).write_text(text, encoding="utf-8")
    write_model(folder / "revisions" / "2.yaml", info_for(folder, 2))
    shutil.rmtree(scene_dir(settings, lab, "gone"), onexc=_writable)

    body(client.post(f"/api/domains/{lab}/reload"))

    keep = body(client.get("/api/scenes/keep"))
    assert (keep["latestRevision"], keep["name"]) == (2, "從別處推送的第二版")
    scenes = cast("list[JsonObject]", body(client.get(f"/api/scenes?domain={lab}"))["scenes"])
    assert [scene["id"] for scene in scenes] == ["keep"]
    assert body(client.get("/api/scenes/gone"))["missing"] is True
    run = client.post("/api/scenes/gone/revisions/1/validate", json={"inputs": {}})
    assert (run.status_code, error_code(run)) == (409, "scene_missing")


def test_changed_revision_cannot_run(client: Client, settings: Settings, lab: str) -> None:
    make_scene(client, "needs-secret", lab, NEEDS_SECRET)
    path = scene_dir(settings, lab, "needs-secret") / "revisions" / "2" / SCENARIO_FILE
    path.chmod(stat.S_IWUSR | stat.S_IRUSR)
    path.write_text(NEEDS_SECRET + "# 被改過\n", encoding="utf-8")

    domain = body(client.post(f"/api/domains/{lab}/reload"))["domain"]

    problems = cast("list[JsonObject]", cast("JsonObject", domain)["problems"])
    assert "pack.revision_hash_mismatch" in [item["code"] for item in problems]
    validate = client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}})
    assert (validate.status_code, error_code(validate)) == (409, "revision_unusable")
    revision = cast("list[JsonObject]", body(client.get("/api/scenes/needs-secret"))["revisions"])[
        0
    ]
    assert revision["problem"] == "pack.revision_hash_mismatch"


def test_ids_are_unique_across_domains(client: Client, settings: Settings, lab: str) -> None:
    client.post("/api/domains", json={"id": "other", "name": "其他"})
    make_scene(client, "shared", lab)
    shutil.copytree(scene_dir(settings, lab, "shared"), scene_dir(settings, "other", "shared"))

    reloaded = body(client.post("/api/domains/other/reload"))

    issues = cast("list[JsonObject]", reloaded["issues"])
    assert [item["code"] for item in issues] == ["server.duplicate_scene"]
    assert body(client.get("/api/scenes/shared"))["domainId"] == lab
    taken = client.post("/api/scenes", json={"id": "shared", "name": "重複", "domainId": "other"})
    assert error_code(taken) == "scene_exists"


def test_folders_are_found_at_startup(settings: Settings) -> None:
    folder = settings.data_dir / "domains" / "pulled"
    write_model(folder / PACK_FILE, PackManifest(spec_version=1, id="pulled", name="拉取的領域"))
    scene = folder / "scenes" / "p-001"
    write_model(scene / "scene.yaml", SceneManifest(id="p-001"))
    revision = scene / "revisions" / "1"
    revision.mkdir(parents=True)
    (revision / SCENARIO_FILE).write_text(new_scene_template("p-001", "拉取", None), "utf-8")
    write_model(revision.with_name("1.yaml"), info_for(scene, 1))

    with TestClient(create_app(settings)) as client:
        domains = cast("list[JsonObject]", body(client.get("/api/domains"))["domains"])
        assert [(item["id"], item["sceneCount"]) for item in domains] == [("pulled", 1)]
        assert body(client.get("/api/scenes/p-001"))["name"] == "拉取"


# ---------------------------------------------------------------- 角色


def test_roles_live_in_domain_folders(client: Client, settings: Settings, lab: str) -> None:
    client.post("/api/domains", json={"id": "other", "name": "其他"})
    role = {
        "id": "lab-user",
        "name": "實驗帳號",
        "loginUrl": "https://example.test/login",
        "check": "{ testId: current-user }",
        "domainId": lab,
    }
    created = body(client.post("/api/roles", json=role))
    assert created["domainId"] == lab
    path = pack_dir(settings, lab) / "roles" / "lab-user.yaml"
    assert "check: { testId: current-user }" in path.read_text(encoding="utf-8")

    moved = body(client.patch("/api/roles/lab-user", json={"domainId": "other", "name": "改名"}))

    assert moved["domainId"] == "other"
    assert not path.exists()
    text = (pack_dir(settings, "other") / "roles" / "lab-user.yaml").read_text(encoding="utf-8")
    assert "name: 改名" in text
    assert body(client.delete("/api/roles/lab-user")) == {"deleted": "lab-user"}
    assert not (pack_dir(settings, "other") / "roles" / "lab-user.yaml").exists()


# ---------------------------------------------------------------- 遷移（D7）


@pytest.fixture
def legacy(settings: Settings) -> tuple[Settings, str]:
    """M11 之前的資料目錄：資料庫有場景、版本、角色、通過的驗證執行，版本在 scenes/<場景>/<n>/。

    先用現在的程式建立資料，再改回舊的樣子：版本搬回 scenes/、刪掉 domains/、清掉「已經遷移」。
    """
    app = create_app(settings)
    with TestClient(app):  # 結束時關閉資料庫連線
        run_id = _legacy_data(services(app))
    data = settings.data_dir
    for domain_id, scene_id in (("lab", "ba-004"), ("unassigned", "loose")):
        old = data / "scenes" / scene_id
        old.mkdir(parents=True)
        shutil.move(
            data / "domains" / domain_id / "scenes" / scene_id / "revisions" / "1", old / "1"
        )
    shutil.rmtree(data / "domains", onexc=_writable)
    (data / "runs" / run_id).mkdir(parents=True)
    (data / "runs" / run_id / "result.json").write_text('{"status": "passed"}', encoding="utf-8")
    return settings, run_id


def _legacy_data(svc: Services) -> str:
    """資料庫的部分：場景、版本、角色、一次通過的驗證執行與發布；角色與 loose 沒有領域。"""
    svc.create_domain("lab", "實驗")
    ba_004 = (DEMO / "ba-004.yaml").read_text(encoding="utf-8")
    svc.add_scene("ba-004", {SCENARIO_FILE: ba_004}, note="匯入", domain_id="lab")
    svc.add_scene("loose", {SCENARIO_FILE: new_scene_template("loose", "乙", None)}, note=None)
    svc.roles.create_role(
        "testsite-user",
        {
            "name": "測試網站：一般使用者",
            "loginUrl": "http://127.0.0.1:8765/login",
            "check": {"testId": "current-user"},
            "engine": "firefox",
            "domainId": "lab",
        },
    )
    svc.roles.create_role(
        "spare-user",
        {"name": "沒人用", "loginUrl": "https://example.test/", "check": {"testId": "x"}},
    )
    moment = now() - timedelta(days=1)
    run_id = "ba-004-20261018-131500-a1b2c3"
    with svc.sessions() as session:
        revision = session.scalars(select(Revision).where(Revision.scene_id == "ba-004")).one()
        session.add(
            Run(
                id=run_id,
                scene_id="ba-004",
                revision_id=revision.id,
                revision_number=1,
                scene_name="查詢帳號",
                category=None,
                purpose="validation",
                status="passed",
                headless=True,
                input={},
                scenario_hash=revision.content_hash,
                cancel_requested=False,
                created_at=moment,
                started_at=moment,
                finished_at=moment,
                duration_seconds=3.0,
                target="local",
                worker_id="local",
            )
        )
        revision.status = "passed"
        revision.published_at = moment
        scene = session.get(Scene, "ba-004")
        assert scene is not None
        scene.published_number = 1
        loose = session.get(Scene, "loose")
        assert loose is not None
        loose.domain_id = None
        for role in session.scalars(select(Role)):
            role.domain_id = None
        layout = session.get(Setting, "storage_layout")
        assert layout is not None
        session.delete(layout)
        session.commit()
    return run_id


def test_migration_from_the_old_layout(legacy: tuple[Settings, str]) -> None:
    settings, run_id = legacy
    data = settings.data_dir

    with TestClient(create_app(settings)) as client:
        backups = list((data / "backups").glob("*-before-domains"))
        assert len(backups) == 1
        assert (backups[0] / "rpa.db").is_file()
        assert (backups[0] / "scenes" / "ba-004" / "1" / SCENARIO_FILE).is_file()
        assert not (data / "scenes").exists()

        folder = data / "domains" / "lab" / "scenes" / "ba-004"
        assert (folder / "revisions" / "1" / SCENARIO_FILE).is_file()
        record, _ = read_model(folder / "verifications" / "1" / f"{run_id}.yaml", Verification)
        assert record is not None
        assert (record.status, record.by) == ("passed", "遷移")
        scene, _ = read_model(folder / "scene.yaml", SceneManifest)
        assert scene is not None
        assert scene.published is not None
        assert (scene.published.revision, scene.published.verification) == (1, run_id)
        assert (data / "domains" / "unassigned" / "scenes" / "loose" / "scene.yaml").is_file()
        assert (data / "domains" / "lab" / "roles" / "testsite-user.yaml").is_file()
        assert (data / "domains" / "unassigned" / "roles" / "spare-user.yaml").is_file()
        manifest = json.loads((data / "runs" / run_id / RUN_MANIFEST).read_text("utf-8"))
        assert (manifest["domain"], manifest["status"]) == ("lab", "passed")
        for domain_id in ("lab", "unassigned"):
            pack = read_pack(data / "domains" / domain_id, expected_id=domain_id)
            assert pack.ok, pack.issues

        detail = body(client.get("/api/scenes/ba-004"))
        assert (detail["domainId"], detail["publishedRevision"]) == ("lab", 1)
        assert detail["latestStatus"] == "passed"
        assert body(client.get("/api/scenes/loose"))["domainId"] == "unassigned"
        role = body(client.get("/api/roles/testsite-user"))
        assert role["domainId"] == "lab"

    # 再啟動一次：不再遷移、不再備份
    with TestClient(create_app(settings)):
        assert len(list((data / "backups").glob("*-before-domains"))) == 1


def test_new_data_folder_needs_no_migration(settings: Settings) -> None:
    with TestClient(create_app(settings)):
        assert not (settings.data_dir / "backups").exists()
        assert (settings.data_dir / "domains").is_dir()
