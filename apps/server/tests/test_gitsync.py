"""領域資料夾的 git 同步（M11 PR 3）：空倉庫與新目錄的第一次推送、另一台伺服器拉取與推回紀錄、
不必重啟就看到新版本、衝突時三選一、推送前檢查、只動設定的目錄、憑證不外流。

遠端是本機的裸倉庫（``git init --bare``），CI 不連外部倉庫（任務紀錄第 14 節）。第二台伺服器是
另一個資料目錄的另一個 Portal。
"""

import json
import os
import shutil
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_server.models import Domain
from rpa_server.services import Services
from rpa_server.storage import SCENARIO_FILE
from rpa_worker import Worker

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="需要 git")

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


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def remote_files(remote: Path, ref: str = "main") -> list[str]:
    return git("--git-dir", str(remote), "ls-tree", "-r", "--name-only", ref).split()


def remote_head(remote: Path, ref: str = "main") -> str:
    return git("--git-dir", str(remote), "rev-parse", ref).strip()


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    path = tmp_path / "remote.git"
    git("init", "-q", "--bare", str(path))
    return path


@pytest.fixture
def lab(client: Client) -> str:
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    return "lab"


def make_scene(client: Client, scene_id: str, text: str | None = None) -> None:
    body(client.post("/api/scenes", json={"id": scene_id, "name": "暫名", "domainId": "lab"}), 201)
    if text is not None:
        save(client, scene_id, 1, text)


def save(client: Client, scene_id: str, base: int, text: str) -> None:
    body(
        client.post(
            f"/api/scenes/{scene_id}/revisions",
            json={"baseRevision": base, "files": {SCENARIO_FILE: text}},
        ),
        201,
    )


def connect(client: Client, remote: Path, directory: str = "team/lab") -> JsonObject:
    return body(
        client.put("/api/domains/lab/source", json={"url": str(remote), "directory": directory})
    )


def push(client: Client, message: str | None = None) -> JsonObject:
    return body(client.post("/api/domains/lab/sync/push", json={"message": message}))


@contextmanager
def second_server(tmp_path: Path) -> Generator[tuple[FastAPI, Client]]:
    """另一個人的伺服器：全新的資料目錄。"""
    data = tmp_path / "second"
    settings = Settings(
        data_dir=data,
        database_url=sqlite_url(data / "rpa.db"),
        examples_dir=DEMO,
        start_worker=False,
        seed_examples=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield app, client


def latest_revision(client: Client, scene_id: str) -> int:
    revisions = cast("list[JsonObject]", body(client.get(f"/api/scenes/{scene_id}"))["revisions"])
    return cast("int", revisions[0]["number"])


# ---------------------------------------------------------------- 第一次推送


def test_first_push_to_an_empty_repository(
    client: Client, settings: Settings, remote: Path, lab: str
) -> None:
    make_scene(client, "ba-101")
    assert connect(client, remote)["state"] == "unchecked"
    probe = body(client.post("/api/domains/lab/sync/test"))
    assert probe["state"] == "empty"
    status = body(client.get("/api/domains/lab/sync"))
    assert status["state"] == "empty"
    assert cast("JsonObject", status["counts"])["revisions"] == 2  # 版本目錄與版本說明檔

    preview = body(client.get("/api/domains/lab/sync/preview"))
    assert preview["blockers"] == []
    assert str(preview["message"]).startswith("lab：")
    assert "ba-101" in str(preview["message"])

    pushed = push(client)
    assert pushed["state"] == "synced"
    assert pushed["syncedCommit"] == remote_head(remote)
    files = remote_files(remote)
    assert "team/lab/pack.yaml" in files
    assert f"team/lab/scenes/ba-101/revisions/1/{SCENARIO_FILE}" in files
    assert "team/lab/scenes/ba-101/revisions/1.yaml" in files
    assert not any(name.endswith(("state.json", "secrets.json", "run.json")) for name in files)
    # 再推一次沒有變更：不建立空的提交
    assert push(client)["syncedCommit"] == remote_head(remote)
    assert len(git("--git-dir", str(remote), "log", "--format=%H", "main").split()) == 1


def test_new_directory_leaves_the_rest_of_the_repository_alone(
    client: Client, tmp_path: Path, remote: Path, lab: str
) -> None:
    work = tmp_path / "work"
    git("init", "-q", "-b", "main", str(work))
    (work / "README.md").write_text("其他人的目錄\n", encoding="utf-8")
    (work / "other").mkdir()
    (work / "other" / "pack.yaml").write_text("id: other\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("-c", "user.name=x", "-c", "user.email=x@example.com", "commit", "-qm", "init", cwd=work)
    git("push", "-q", str(remote), "HEAD:main", cwd=work)
    before = remote_head(remote)

    connect(client, remote, "lab")
    assert body(client.post("/api/domains/lab/sync/test"))["state"] == "no_directory"
    assert body(client.get("/api/domains/lab/sync"))["state"] == "no_directory"
    push(client, "lab：第一次推送")
    assert {"README.md", "other/pack.yaml", "lab/pack.yaml"} <= set(remote_files(remote))
    parent = git("--git-dir", str(remote), "rev-parse", "main^").strip()
    assert parent == before
    assert git("--git-dir", str(remote), "log", "-1", "--format=%s", "main").strip() == (
        "lab：第一次推送"
    )


# ---------------------------------------------------------------- 兩台之間


def test_records_and_revisions_travel_between_servers(
    app: FastAPI, client: Client, tmp_path: Path, remote: Path, lab: str
) -> None:
    make_scene(client, "needs-secret", NEEDS_SECRET)
    connect(client, remote)
    push(client)

    with second_server(tmp_path) as (other_app, other):
        probe = body(
            other.post("/api/git/probe", json={"url": str(remote), "directory": "team/lab"})
        )
        assert (probe["state"], probe["packId"], probe["packName"]) == ("ready", "lab", "實驗")
        created = body(
            other.post("/api/domains/from-git", json={"url": str(remote), "directory": "team/lab"}),
            201,
        )
        assert created["id"] == "lab"
        assert cast("JsonObject", created["sync"])["state"] == "synced"
        assert latest_revision(other, "needs-secret") == 2

        # 第二台驗證（缺少 Secret：停在入參階段，也會寫驗證紀錄）並推送紀錄
        run = body(
            other.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}), 202
        )
        cast("Worker", other_app.state.worker).run_once()
        status = body(other.get("/api/domains/lab/sync"))
        assert status["state"] == "ahead"
        assert cast("JsonObject", status["counts"])["verifications"] == 1
        push(other, "第二台的驗證")

        # 第一台改了場景、推送；第二台不必重新啟動，拉取就看到新版本
        save(client, "needs-secret", 2, NEEDS_SECRET.replace("缺少機密", "缺少機密 v3"))
        pushed = push(client)
        assert pushed["state"] == "synced"
        assert body(other.get("/api/domains/lab/sync"))["state"] == "synced"  # 還沒檢查遠端
        services(other_app).git.pull_on_startup()  # 和啟動時自動拉取同一個流程
        assert latest_revision(other, "needs-secret") == 3

    # 第一台推送時已經順便取回第二台的驗證紀錄
    listed = cast(
        "list[JsonObject]",
        body(client.get("/api/scenes/needs-secret/verifications"))["verifications"],
    )
    assert [(item["id"], item["here"]) for item in listed] == [(run["id"], False)]
    subjects = git("--git-dir", str(remote), "log", "--format=%s", "main").splitlines()
    assert "第二台的驗證" in subjects
    assert body(client.post("/api/domains/lab/sync/pull"))["state"] == "synced"


def test_conflict_stops_and_offers_three_choices(
    client: Client, settings: Settings, tmp_path: Path, remote: Path, lab: str
) -> None:
    make_scene(client, "ba-101")
    connect(client, remote)
    push(client)

    with second_server(tmp_path) as (_, other):
        body(
            other.post("/api/domains/from-git", json={"url": str(remote), "directory": "team/lab"}),
            201,
        )
        # 兩台同時替同一個場景建立第 2 版，內容不同
        template = body(client.get("/api/scenes/ba-101/revisions/1"))["files"]
        text = cast("dict[str, str]", template)[SCENARIO_FILE]
        save(client, "ba-101", 1, text.replace("暫名", "第一台"))
        save(other, "ba-101", 1, text.replace("暫名", "第二台"))
        push(client)
        head = remote_head(remote)

        refused = other.post("/api/domains/lab/sync/push", json={})
        details = error(refused, 409)
        assert details["code"] == "sync_conflict"
        assert f"scenes/ba-101/revisions/2/{SCENARIO_FILE}" in cast(
            "list[str]", details["conflicts"]
        )
        assert remote_head(remote) == head  # 遠端沒有被覆蓋
        status = body(other.get("/api/domains/lab/sync"))
        assert status["state"] == "conflict"
        assert "sync-conflict" in other.get("/domains/lab/sync").text

        # 推送到新分支：遠端多一個分支，main 不變
        branched = body(other.post("/api/domains/lab/sync/resolve", json={"action": "branch"}))
        branch = str(branched["pushedBranch"])
        assert branch.startswith("rpa/lab-")
        assert "第二台" in git(
            "--git-dir",
            str(remote),
            "show",
            f"{branch}:team/lab/scenes/ba-101/revisions/2/{SCENARIO_FILE}",
        )
        assert remote_head(remote) == head

        # 以遠端為準：先備份，再套用遠端
        taken = body(other.post("/api/domains/lab/sync/resolve", json={"action": "remote"}))
        assert taken["state"] == "synced"
        files = cast("dict[str, str]", body(other.get("/api/scenes/ba-101/revisions/2"))["files"])
        assert "第一台" in files[SCENARIO_FILE]
        backups = list((tmp_path / "second" / "backups").glob("*-before-remote-lab"))
        assert len(backups) == 1
        assert "第二台" in (
            backups[0] / "scenes" / "ba-101" / "revisions" / "2" / SCENARIO_FILE
        ).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 推送前檢查與憑證


def test_push_is_blocked_by_secret_values_and_private_files(
    client: Client, settings: Settings, remote: Path, lab: str
) -> None:
    body(client.put("/api/secrets/LAB_PASSWORD", json={"value": "hunter2-very-secret"}))
    folder = settings.data_dir / "domains" / "lab"
    (folder / "notes.md").write_text("密碼 hunter2-very-secret\n", encoding="utf-8")
    (folder / "state.json").write_text("{}", encoding="utf-8")
    connect(client, remote)

    preview = body(client.get("/api/domains/lab/sync/preview"))
    blockers = cast("list[str]", preview["blockers"])
    assert any("state.json" in item for item in blockers)
    assert any("notes.md" in item and "LAB_PASSWORD" in item for item in blockers)
    assert not any("hunter2" in item for item in blockers)
    refused = client.post("/api/domains/lab/sync/push", json={})
    assert error(refused, 422)["code"] == "sync_blocked"
    assert git("--git-dir", str(remote), "for-each-ref").strip() == ""  # 遠端還是空的


def test_tokens_stay_out_of_the_database_and_responses(
    app: FastAPI, client: Client, settings: Settings, lab: str
) -> None:
    token = "ghp_example_token_1234567890"
    source = {
        "url": "https://example.invalid/org/rpa-data.git",
        "directory": "lab",
        "auth": "https",
        "username": "bot",
        "token": token,
    }
    status = body(client.put("/api/domains/lab/source", json=source))
    assert status["hasToken"] is True
    assert token not in json.dumps(status)
    with services(app).sessions() as session:
        domain = session.get(Domain, "lab")
        assert domain is not None
        assert token not in json.dumps(domain.source)
    credentials = settings.data_dir / "git" / "credentials.json"
    assert token in credentials.read_text(encoding="utf-8")
    if os.name != "nt":
        assert credentials.stat().st_mode & 0o777 == 0o600
    assert token not in client.get("/domains/lab/sync").text
    # 改其他欄位、權杖留空：權杖不變
    body(client.put("/api/domains/lab/source", json={**source, "token": None, "autoPull": False}))
    assert token in credentials.read_text(encoding="utf-8")

    bad = {**source, "url": "https://bot:secret@example.invalid/org/rpa-data.git"}
    refused = client.put("/api/domains/lab/source", json=bad)
    assert error(refused, 422)["code"] == "sync_url_credentials"
    refused = client.put("/api/domains/lab/source", json={**source, "directory": "../x"})
    assert error(refused, 422)["code"] == "sync_directory_invalid"
    refused = client.put(
        "/api/domains/lab/source", json={**source, "url": "git@github.com:o/r.git"}
    )
    assert error(refused, 422)["code"] == "sync_url_https"

    assert body(client.delete("/api/domains/lab/source")) == {"disconnected": "lab"}
    assert token not in credentials.read_text(encoding="utf-8")
    assert body(client.get("/api/domains/lab/sync"))["state"] == "local"
    assert (settings.data_dir / "domains" / "lab" / "pack.yaml").is_file()  # 資料夾保留


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="需要 ssh-keygen")
def test_deploy_key_is_generated_per_domain(client: Client, settings: Settings, lab: str) -> None:
    key = body(client.post("/api/domains/lab/source/key"))["publicKey"]
    assert str(key).startswith("ssh-ed25519 ")
    private = settings.data_dir / "git" / "keys" / "lab"
    if os.name != "nt":
        assert private.stat().st_mode & 0o777 == 0o600
    status = body(
        client.put(
            "/api/domains/lab/source",
            json={"url": "git@github.com:org/rpa-data.git", "directory": "lab", "auth": "ssh"},
        )
    )
    assert status["publicKey"] == key
    assert "PRIVATE KEY" not in json.dumps(status)
    assert body(client.delete("/api/domains/lab")) == {"deleted": "lab"}
    assert not private.exists()


def test_sync_pages(client: Client, remote: Path, lab: str) -> None:
    html = client.get("/domains").text
    assert 'data-action="new-domain-git"' in html
    assert 'href="/domains/lab/sync"' in html
    assert 'id="server"' in html
    page = client.get("/domains/lab/sync")
    assert page.status_code == 200
    assert 'id="sync-source"' in page.text
    assert 'data-action="sync-push"' not in page.text  # 還沒設定資料來源
    connect(client, remote)
    page = client.get("/domains/lab/sync").text
    assert 'data-action="sync-push"' in page
    assert 'id="sync-status"' in page
    assert 'href="/domains/lab/sync"' in client.get("/domains/lab").text
