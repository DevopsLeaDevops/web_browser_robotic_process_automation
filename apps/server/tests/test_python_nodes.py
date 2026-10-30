"""Python 節點（ADR 0020）在管理 Portal：存檔校驗、派工、等待說明、共用工作資料夾的清理。

不需要瀏覽器；遠端 worker 用 Worker API 的 TestClient（同 test_remote_worker_api.py）。
"""

import io
import json
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from typing import cast
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_core.dsl.features import FEATURES
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Revision, Run, Scene
from rpa_server.services import Services
from rpa_worker import Worker
from rpa_worker.environment import PROTOCOL

JsonObject = dict[str, object]
WORKER_PORT = 8081
API = "/worker-api/v1"

NODE = """\
schemaVersion: 1
id: py-sum
name: 加總
inputs:
  rows: { type: array, default: [1, 2, 3] }
outputs:
  total: { type: number, from: '{{ facts.total }}' }
script:
  runtime: '1'
  automation: automation.py
  files: [helpers.py]
  platforms: [linux, windows]
verify:
  - { value: '{{ facts.total }}', matches: '^[0-9]' }
"""
AUTOMATION = """\
from helpers import total
from rpa_script import automation


@automation
def main(run):
    run.facts["total"] = total(run.inputs["rows"])
"""
HELPERS = "def total(rows):\n    return sum(rows)\n"

INFO: JsonObject = {
    "name": "BOX",
    "protocol": PROTOCOL,
    "fingerprint": "x",
    "os": "Linux",
    "python": "3.13.1",
    "host": "BOX",
    "browsers": [],
    "display": False,
    "features": sorted(FEATURES),
}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT)


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


@pytest.fixture(autouse=True)
def _no_local_runtime(app: FastAPI) -> None:
    """這台伺服器沒有運行環境（測試不依賴執行測試的電腦）。"""
    services(app).queue.runtimes = lambda: ()


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int | None = None) -> JsonObject:
    if status is not None:
        assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: Client, worker_id: str) -> str:
    created = body(client.post("/api/workers", json={"id": worker_id, "name": worker_id}), 201)
    return str(created["token"])


def hello(remote: Client, token: str, **changes: object) -> None:
    body(remote.post(f"{API}/hello", json={**INFO, **changes}, headers=auth(token)), 200)


def claim(remote: Client, token: str) -> JsonObject | None:
    response = remote.post(f"{API}/claim", json={"waitSeconds": 0}, headers=auth(token))
    if response.status_code == 204:
        return None
    return body(response, 200)


def create_node(client: Client, text: str = NODE) -> Response:
    assert client.post("/api/scenes", json={"id": "py-sum", "name": "暫名"}).status_code == 201
    files = {"scenario.yaml": text, "automation.py": AUTOMATION, "helpers.py": HELPERS}
    return client.post("/api/scenes/py-sum/revisions", json={"baseRevision": 1, "files": files})


def validate(client: Client, target: str = "any") -> JsonObject:
    payload: JsonObject = {"inputs": {}, "target": target}
    return body(client.post("/api/scenes/py-sum/revisions/2/validate", json=payload), 202)


def test_python_node_is_saved_with_its_files(client: Client) -> None:
    body(create_node(client), 201)
    detail = client.get("/scenes/py-sum").text
    assert "helpers.py" in detail
    assert "RPA Python 運行環境 1" in detail
    editor = client.get("/scenes/py-sum/edit?file=helpers.py").text
    assert 'data-file-tab="helpers.py" class="active"' in editor


def test_python_node_rules_are_checked_on_save(client: Client) -> None:
    broken = NODE.replace("script:\n", "browser: { engine: firefox }\nscript:\n")
    problem = body(create_node(client, broken), 422)["error"]
    assert isinstance(problem, dict)
    issues = cast("list[JsonObject]", cast("JsonObject", problem)["issues"])
    assert [item["code"] for item in issues] == ["script.runtime_no_browser"]


def test_runtime_nodes_go_only_to_workers_with_the_runtime(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(create_node(client), 201)
    plain = register(client, "plain")
    with_runtime = register(client, "py-box")
    hello(remote, plain, browsers=["chromium"], display=True, platform="linux-x86_64")
    # 沒有瀏覽器、不能顯示視窗也沒關係；要有運行環境 1、平台在 platforms 裡
    hello(remote, with_runtime, runtimes=["1.2.0"], platform="linux-x86_64")
    queued = validate(client)

    # 本機沒有運行環境：「任一」的 Python 節點留給遠端
    assert cast("Worker", app.state.worker).source.claim() is None
    assert claim(remote, plain) is None
    job = claim(remote, with_runtime)
    assert job is not None
    assert job["runId"] == queued["id"]
    assert set(cast("JsonObject", job["files"])) == {
        "scenario.yaml",
        "automation.py",
        "helpers.py",
    }
    assert job["workspace"] is None  # 單獨驗證：沒有共用工作資料夾


def test_platforms_are_respected(app: FastAPI, client: Client, remote: Client) -> None:
    body(create_node(client), 201)
    mac = register(client, "mac")
    hello(remote, mac, runtimes=["1.0.0"], platform="macos-arm64")
    queued = validate(client, target="remote")
    assert claim(remote, mac) is None
    wait = services(app).worker_wait(str(queued["id"]))
    assert wait == {"worker": None, "runtime": "1", "platforms": "linux, windows"}
    assert "系統是 linux, windows" in client.get(f"/runs/{queued['id']}").text


def test_waiting_for_a_runtime_is_explained(app: FastAPI, client: Client, remote: Client) -> None:
    body(create_node(client), 201)
    token = register(client, "old-app")
    hello(remote, token, features=["frame"])  # 舊版 App：沒有回報運行環境
    queued = validate(client)
    assert services(app).worker_wait(str(queued["id"])) == {
        "worker": None,
        "runtime": "1",
        "platforms": "linux, windows",
    }
    devices = client.get("/devices").text
    assert "RPA Python 運行環境：—" in devices


def test_finished_composite_tells_its_worker_to_clean_up(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(create_node(client), 201)
    portal = services(app)
    with portal.sessions() as session:
        scene = session.get(Scene, "py-sum")
        assert scene is not None
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == "py-sum", Revision.number == 2)
        ).one()
        revision.status = "passed"
        revision.published_at = now()
        scene.published_number = 2
        session.commit()
    token = register(client, "py-box")
    hello(remote, token, runtimes=["1.0.0"], platform="linux-x86_64")
    definition: JsonObject = {
        "nodes": [{"id": "n1", "sceneId": "py-sum", "revision": 2}],
    }
    created = body(client.post("/api/workflows", json={"name": "加總", "definition": definition}))
    started = body(
        client.post(f"/api/workflows/{created['id']}/runs", json={"target": "remote"}), 202
    )
    job = claim(remote, token)
    assert job is not None
    assert job["workspace"] == started["id"]  # 組合運行的節點帶著共用工作資料夾
    beat = body(
        remote.post(
            f"{API}/runs/{job['runId']}/heartbeat", json={"stage": "runtime"}, headers=auth(token)
        )
    )
    assert beat == {"cancel": False}  # 沒有要刪的共用工作資料夾：不附 cleanup
    with portal.sessions() as session:
        run = session.get(Run, str(job["runId"]))
        assert run is not None
        assert run.stage == "runtime"
    result: JsonObject = {
        "runId": job["runId"],
        "status": "passed",
        "scenarioHash": "0" * 64,
        "durationSeconds": 0.5,
        "output": {"total": 6},
        "error": None,
    }
    finished = remote.post(
        f"{API}/runs/{job['runId']}/finish", json={"result": result}, headers=auth(token)
    )
    assert finished.status_code == 204, finished.text
    assert body(client.get(f"/api/workflow-runs/{started['id']}"))["status"] == "passed"
    # 沒有任務了也立刻回覆要刪的共用工作資料夾，只回一次
    assert claim(remote, token) == {"cleanup": [started["id"]]}
    assert claim(remote, token) is None


def zipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_run_page_shows_produced_files_changes_and_previews(
    app: FastAPI, client: Client, remote: Client
) -> None:
    """Python 節點的運行詳情（ADR 0020）：運行環境、產出檔案、檔案變化、資料預覽。"""
    body(create_node(client), 201)
    token = register(client, "py-box")
    hello(remote, token, runtimes=["1.0.0"], platform="linux-x86_64")
    validate(client)
    job = claim(remote, token)
    assert job is not None
    run_id = str(job["runId"])
    python = {
        "mode": "runtime",
        "runtime": "1.0.0",
        "platform": "linux-x86_64",
        "python": "3.13.14",
        "reused": False,
        "preparedMs": 1234,
    }
    steps = [
        {
            "id": "write",
            "action": "python",
            "name": "寫出",
            "status": "passed",
            "durationMs": 20,
            "error": None,
            "artifacts": [],
            "startedAt": "2026-10-29T10:00:00.000Z",
            "endedAt": "2026-10-29T10:00:00.020Z",
            "occurrence": 1,
            "parent": None,
            "source": "automation.py:7",
            "previews": ["previews/001.json"],
            "files": {"added": ["outputs/彙總.csv"]},
            "console": [0, len(b"token ***\n")],
        }
    ]
    result = {
        "runId": run_id,
        "status": "passed",
        "kind": "script",
        "engine": "chromium",
        "input": {"rows": [1, 2, 3]},
        "stages": [{"name": "runtime", "status": "passed", "durationMs": 1234, "message": None}],
        "problems": [],
        "checks": [],
        "steps": steps,
        "python": python,
    }
    preview = {
        "name": "資料",
        "kind": "table",
        "columns": ["分店", "金額"],
        "rows": [["台北", 10], ["高雄", 20]],
        "rowCount": 2,
        "columnCount": 2,
        "truncated": False,
    }
    changes = {
        "added": [{"where": "workspace", "path": "notes/log.txt", "size": 2}],
        "changed": [],
        "removed": [],
        "truncated": False,
    }
    archive = zipped(
        {
            "result.json": json.dumps(result).encode(),
            "outputs/彙總.csv": "分店,金額\n".encode(),
            "previews/001.json": json.dumps(preview, ensure_ascii=False).encode(),
            "files.json": json.dumps(changes).encode(),
            "steps.json": json.dumps(steps, ensure_ascii=False).encode(),
            "scenario/automation.py": AUTOMATION.encode(),
            "automation.log": b"token ***\n",
        }
    )
    uploaded = remote.put(
        f"{API}/runs/{run_id}/artifacts",
        content=archive,
        headers={**auth(token), "Content-Type": "application/zip"},
    )
    assert uploaded.status_code == 204, uploaded.text
    digest = services(app).get_revision("py-sum", 2).content_hash
    finished = remote.post(
        f"{API}/runs/{run_id}/finish",
        json={
            "result": {
                "runId": run_id,
                "status": "passed",
                "scenarioHash": digest,
                "durationSeconds": 1.5,
                "output": {"total": 6},
                "error": None,
            }
        },
        headers=auth(token),
    )
    assert finished.status_code == 204, finished.text

    page = client.get(f"/runs/{run_id}").text
    assert "RPA Python 運行環境 1.0.0（linux-x86_64）" in page
    assert "第一次準備，1234 ms" in page
    assert 'data-produced="outputs/彙總.csv"' in page
    assert "資料預覽：資料" in page
    assert "<td>高雄</td>" in page
    assert "notes/log.txt" in page
    download = client.get(f"/runs/{run_id}/files/outputs/{quote('彙總.csv')}?download=1")
    assert download.status_code == 200
    assert download.content == "分店,金額\n".encode()

    # 步驟時間軸（回看）：章節、腳本那幾行（標出第 7 行）、資料預覽、主控台
    assert 'data-action="timeline"' in page
    timeline = client.get(f"/runs/{run_id}/replay").text
    assert 'data-python-step="1"' in timeline
    assert "步驟時間軸" in timeline
    assert '"focusLine": 7' in timeline
    assert "token ***" in timeline
    # 到這一步為止的主控台：這一步寫的是第 1 行
    assert '"console": {"line": 1, "text": "token ***", "own": [1, 1]}' in timeline
