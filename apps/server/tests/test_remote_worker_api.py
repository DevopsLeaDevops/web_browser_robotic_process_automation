"""M9a 遠端 worker：登記與權杖、兩個埠分開、上線、領取的配對、心跳與取消、上傳產物、結果、
租約過期、序列固定同一台 worker、登入狀態傳回、重新啟動。不需要瀏覽器。

Worker API 用 TestClient 打到 Worker API 的埠（base_url 帶 :8081）；真的 HTTP 與遠端 worker 的
完整流程在 test_remote_worker_flow.py。
"""

import base64
import io
import json
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_server.domain import now
from rpa_server.models import Revision, Run, Scene
from rpa_server.services import Services
from rpa_server.storage import SCENARIO_FILE
from rpa_worker import Worker
from rpa_worker.environment import PROTOCOL

JsonObject = dict[str, object]
WORKER_PORT = 8081
API = "/worker-api/v1"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT)


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    """打到 Worker API 埠的用戶端（伺服器已經由 client 啟動）。"""
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


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


def register(client: Client, worker_id: str = "win-01", name: str = "Windows 機器") -> str:
    created = body(client.post("/api/workers", json={"id": worker_id, "name": name}), 201)
    return str(created["token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


INFO: JsonObject = {
    "name": "WIN-01",
    "protocol": PROTOCOL,
    "fingerprint": "x",
    "os": "Windows 11",
    "python": "3.13.1",
    "host": "WIN-01",
    "browsers": ["chromium", "firefox"],
    "display": True,
}


def hello(remote: Client, token: str, **changes: object) -> JsonObject:
    return body(remote.post(f"{API}/hello", json={**INFO, **changes}, headers=auth(token)), 200)


def claim(remote: Client, token: str) -> JsonObject | None:
    response = remote.post(f"{API}/claim", json={"waitSeconds": 0}, headers=auth(token))
    if response.status_code == 204:
        return None
    return body(response, 200)


def publish(app: FastAPI, scene_id: str, number: int = 1) -> None:
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


def validate(client: Client, scene: str = "ba-001", **options: object) -> JsonObject:
    payload: JsonObject = {"inputs": {}, "headless": True, **options}
    return body(client.post(f"/api/scenes/{scene}/revisions/1/validate", json=payload), 202)


def run_row(app: FastAPI, run_id: object) -> Run:
    with services(app).sessions() as session:
        run = session.get(Run, str(run_id))
        assert run is not None
        return run


def zipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def result_json(run_id: object, status: str = "passed", **changes: object) -> JsonObject:
    return {
        "runId": run_id,
        "status": status,
        "scenarioHash": "0" * 64,
        "durationSeconds": 1.5,
        "output": {"recordId": "DEMO-1"} if status == "passed" else None,
        "error": None if status == "passed" else "失敗",
        "role": None,
        "login": None,
        **changes,
    }


# ---------------------------------------------------------------- 登記與權杖


def test_register_rotate_disable_and_delete(client: Client, remote: Client) -> None:
    token = register(client)
    listed = body(client.get("/api/workers"))
    assert listed["defaultTarget"] == "local"
    assert listed["localWorker"] is True
    workers = cast("list[JsonObject]", listed["workers"])
    assert [(w["id"], w["name"], w["status"]) for w in workers] == [
        ("win-01", "Windows 機器", "offline")
    ]
    assert token not in json.dumps(listed)

    assert error(client.post("/api/workers", json={"id": "win-01"}), 409)["code"] == "worker_exists"
    assert error(client.post("/api/workers", json={"id": "Bad Id"}), 422)["code"] == (
        "worker_id_invalid"
    )
    assert error(client.post("/api/workers", json={"id": "local"}), 422)["code"] == (
        "worker_id_invalid"
    )

    assert hello(remote, token)["worker"] == "win-01"
    assert body(client.get("/api/workers/win-01"))["status"] == "online"

    rotated = body(client.post("/api/workers/win-01/token"))
    new_token = str(rotated["token"])
    assert error(remote.post(f"{API}/hello", json=INFO, headers=auth(token)), 401)["code"] == (
        "worker_unauthorized"
    )
    hello(remote, new_token)

    disabled = body(client.patch("/api/workers/win-01", json={"disabled": True}))
    assert disabled["status"] == "disabled"
    assert remote.post(f"{API}/hello", json=INFO, headers=auth(new_token)).status_code == 401
    body(client.patch("/api/workers/win-01", json={"disabled": False, "name": "新名稱"}))

    assert body(client.delete("/api/workers/win-01")) == {"deleted": "win-01"}
    assert error(client.get("/api/workers/win-01"), 404)["code"] == "worker_not_found"


def test_worker_api_needs_a_token(client: Client, remote: Client) -> None:
    register(client)
    assert remote.post(f"{API}/hello", json=INFO).status_code == 401
    assert remote.post(f"{API}/hello", json=INFO, headers=auth("wrong")).status_code == 401
    assert remote.post(
        f"{API}/claim", json={}, headers={"Authorization": "Basic x"}
    ).status_code == (401)


def test_ports_are_kept_apart(client: Client, remote: Client) -> None:
    token = register(client)
    # Worker API 不在管理頁面的埠
    assert client.post(f"{API}/hello", json=INFO, headers=auth(token)).status_code == 404
    # 管理頁面與 /api 不在 Worker API 的埠；M10.2 起只給錄製端的權杖（worker 的權杖也不行）
    assert remote.get("/api/workers").status_code == 401
    assert remote.get("/scenes").status_code == 401
    assert remote.get("/static/portal.css").status_code == 401
    assert remote.get("/scenes", headers=auth(token)).status_code == 401


def test_worker_api_is_closed_without_a_worker_port(tmp_path: Path) -> None:
    data = tmp_path / "plain"
    app = create_app(
        Settings(data_dir=data, database_url=sqlite_url(data / "rpa.db"), start_worker=False)
    )
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        assert other.post(f"{API}/hello", json=INFO).status_code == 404


def test_hello_checks_the_protocol_and_records_the_machine(client: Client, remote: Client) -> None:
    token = register(client)
    mismatch = remote.post(f"{API}/hello", json={**INFO, "protocol": 99}, headers=auth(token))
    assert error(mismatch, 409)["code"] == "protocol_mismatch"

    reply = hello(remote, token)
    assert reply["protocol"] == PROTOCOL
    assert isinstance(reply["fingerprint"], str)
    worker = body(client.get("/api/workers/win-01"))
    assert worker["os"] == "Windows 11"
    assert worker["browsers"] == ["chromium", "firefox"]
    assert worker["display"] is True
    assert worker["sameVersion"] is False  # 指紋 x 和管理 Portal 不同

    hello(remote, token, fingerprint=reply["fingerprint"])
    assert body(client.get("/api/workers/win-01"))["sameVersion"] is True


# ---------------------------------------------------------------- 執行位置與領取


def test_target_needs_a_registered_worker_and_default_can_change(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    refused = client.post(
        "/api/scenes/ba-001/revisions/1/validate", json={"inputs": {}, "target": "remote"}
    )
    assert error(refused, 409)["code"] == "no_remote_worker"
    bad = client.put("/api/settings/default-target", json={"target": "moon"})
    assert bad.status_code == 422

    register(client)
    changed = body(client.put("/api/settings/default-target", json={"target": "remote"}))
    assert changed["defaultTarget"] == "remote"
    queued = validate(client)
    assert (queued["target"], queued["workerId"]) == ("remote", None)


def test_claim_matches_target_browser_and_display(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)  # 還沒上線過：先當作能顯示視窗
    local = validate(client, target="local", engine="chromium")
    headed = validate(client, target="remote", engine="chromium", headless=False)
    firefox = validate(client, target="remote")  # BA-001 預設 Firefox
    hello(remote, token, browsers=["chromium"], display=False)
    assert claim(remote, token) is None

    anywhere = validate(client, target="any", engine="chromium")
    job = claim(remote, token)
    assert job is not None
    assert job["runId"] == anywhere["id"]
    row = run_row(app, anywhere["id"])
    assert (row.status, row.worker_id) == ("running", "win-01")
    assert row.lease_until is not None

    # 本機 worker 只領 local 與 any，不碰 remote
    local_source = cast("Worker", app.state.worker).source
    local_job = local_source.claim()
    assert local_job is not None
    assert local_job.run_id == local["id"]
    assert local_source.claim() is None
    assert run_row(app, headed["id"]).status == "queued"
    assert run_row(app, firefox["id"]).status == "queued"

    # 換成能顯示視窗、有 Firefox 的 worker：依建立順序領到
    hello(remote, token, browsers=["chromium", "firefox"], display=True)
    assert cast("JsonObject", claim(remote, token))["runId"] == headed["id"]
    assert cast("JsonObject", claim(remote, token))["runId"] == firefox["id"]
    assert body(client.get("/api/workers/win-01"))["status"] == "busy"


def test_job_carries_exact_files_inputs_locale_and_secrets(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(
        client, target="remote", inputs={"title": "遠端", "quantity": 3}, baseUrl="http://h:1/"
    )

    job = claim(remote, token)
    assert job is not None
    files = cast("dict[str, str]", job["files"])
    stored = services(app).storage.scenario_path("ba-001", 1).read_bytes()
    assert base64.b64decode(files[SCENARIO_FILE]) == stored
    assert job["runId"] == queued["id"]
    assert job["inputs"] == {"title": "遠端", "quantity": 3}
    assert (job["baseUrl"], job["headless"], job["locale"]) == ("http://h:1/", True, "zh-Hant")
    assert job["login"] is None
    assert job["secrets"] == {}


# ---------------------------------------------------------------- 心跳、取消、結果


def test_heartbeat_extends_lease_and_relays_cancel(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    other = register(client, "win-02")
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)
    before = run_row(app, queued["id"]).lease_until
    assert before is not None

    beat = body(
        remote.post(
            f"{API}/runs/{queued['id']}/heartbeat",
            json={"stage": "automation"},
            headers=auth(token),
        )
    )
    assert beat == {"cancel": False}
    row = run_row(app, queued["id"])
    assert row.stage == "automation"
    assert row.lease_until is not None
    assert row.lease_until >= before

    stranger = remote.post(f"{API}/runs/{queued['id']}/heartbeat", json={}, headers=auth(other))
    assert error(stranger, 409)["code"] == "run_not_assigned"

    body(client.post(f"/api/runs/{queued['id']}/cancel"), 202)
    beat = body(remote.post(f"{API}/runs/{queued['id']}/heartbeat", json={}, headers=auth(token)))
    assert beat == {"cancel": True}


def test_artifacts_and_result_complete_the_run(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)
    run_id = queued["id"]

    archive = zipped(
        {
            "result.json": b"{}",
            "report.html": "<html>報告</html>".encode(),
            "scenario/scenario.yaml": b"id: ba-001\n",
        }
    )
    uploaded = remote.put(
        f"{API}/runs/{run_id}/artifacts",
        content=archive,
        headers={**auth(token), "Content-Type": "application/zip"},
    )
    assert uploaded.status_code == 204, uploaded.text
    # 重送（例如回應遺失）覆蓋上一次的
    again = remote.put(f"{API}/runs/{run_id}/artifacts", content=archive, headers=auth(token))
    assert again.status_code == 204

    revision_hash = services(app).get_revision("ba-001", 1).content_hash
    finished = remote.post(
        f"{API}/runs/{run_id}/finish",
        json={"result": result_json(run_id, scenarioHash=revision_hash)},
        headers=auth(token),
    )
    assert finished.status_code == 204, finished.text

    run = body(client.get(f"/api/runs/{run_id}"))
    assert (run["status"], run["workerId"], run["output"]) == (
        "passed",
        "win-01",
        {"recordId": "DEMO-1"},
    )
    assert body(client.get("/api/scenes/ba-001/revisions/1"))["status"] == "passed"
    report = client.get(f"/runs/{run_id}/files/report.html")
    assert report.status_code == 200
    assert "報告" in report.text
    assert body(client.get("/api/workers/win-01"))["status"] == "online"

    late = remote.post(
        f"{API}/runs/{run_id}/finish", json={"result": result_json(run_id)}, headers=auth(token)
    )
    assert error(late, 409)["code"] == "run_not_assigned"


def test_validation_hash_mismatch_fails(app: FastAPI, client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)

    remote.post(
        f"{API}/runs/{queued['id']}/finish",
        json={"result": result_json(queued["id"], scenarioHash="f" * 64)},
        headers=auth(token),
    )

    run = body(client.get(f"/api/runs/{queued['id']}"))
    assert run["status"] == "failed"
    assert body(client.get("/api/scenes/ba-001/revisions/1"))["status"] == "failed"


def test_unsafe_or_bad_uploads_are_refused(client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)
    run_id = queued["id"]

    unsafe = remote.put(
        f"{API}/runs/{run_id}/artifacts", content=zipped({"../x.txt": b"x"}), headers=auth(token)
    )
    assert error(unsafe, 422)["code"] == "artifacts_invalid"
    junk = remote.put(f"{API}/runs/{run_id}/artifacts", content=b"nope", headers=auth(token))
    assert error(junk, 422)["code"] == "artifacts_invalid"
    bad = remote.post(
        f"{API}/runs/{run_id}/finish", json={"result": {"status": "great"}}, headers=auth(token)
    )
    assert error(bad, 422)["code"] == "result_invalid"
    no_login = remote.put(f"{API}/runs/{run_id}/role-state", content=b"{}", headers=auth(token))
    assert error(no_login, 409)["code"] == "run_without_login"


def test_fail_reports_why_the_run_could_not_start(client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)

    failed = remote.post(
        f"{API}/runs/{queued['id']}/fail",
        json={"kind": "scenario_invalid", "detail": "2"},
        headers=auth(token),
    )
    assert failed.status_code == 204

    run = body(client.get(f"/api/runs/{queued['id']}"))
    assert run["status"] == "failed"
    assert "2" in str(run["error"])


def test_expired_lease_marks_the_run_lost(app: FastAPI, client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)
    with services(app).sessions() as session:
        row = session.get(Run, str(queued["id"]))
        assert row is not None
        row.lease_until = now() - timedelta(seconds=1)
        session.commit()

    assert services(app).workers.expire_leases() == 1

    run = body(client.get(f"/api/runs/{queued['id']}"))
    assert run["status"] == "failed"
    assert "Windows 機器" in str(run["error"])
    assert body(client.get("/api/workers/win-01"))["currentRun"] is None
    beat = remote.post(f"{API}/runs/{queued['id']}/heartbeat", json={}, headers=auth(token))
    assert beat.status_code == 409


def test_restart_keeps_remote_runs_but_fails_local_ones(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    far = validate(client, target="remote")
    near = validate(client, target="local")
    claim(remote, token)
    assert cast("Worker", app.state.worker).source.claim() is not None

    assert services(app).recover() == 1

    assert run_row(app, near["id"]).status == "failed"
    assert run_row(app, far["id"]).status == "running"
    beat = remote.post(f"{API}/runs/{far['id']}/heartbeat", json={}, headers=auth(token))
    assert beat.status_code == 200


def test_delete_busy_worker_is_refused_and_pinned_runs_fail(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    token = register(client)
    hello(remote, token)
    queued = validate(client, target="remote")
    claim(remote, token)
    assert error(client.delete("/api/workers/win-01"), 409)["code"] == "worker_busy"

    remote.post(
        f"{API}/runs/{queued['id']}/finish",
        json={"result": result_json(queued["id"], "failed")},
        headers=auth(token),
    )
    pinned = services(app).request_run(
        "ba-001", purpose="validation", target="remote", required_worker="win-01", headless=True
    )
    body(client.delete("/api/workers/win-01"))
    assert run_row(app, pinned.id).status == "failed"


# ---------------------------------------------------------------- 序列與登入


CHAIN: JsonObject = {
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "遠端"}}},
        {
            "id": "n2",
            "sceneId": "ba-002",
            "revision": 1,
            "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
        },
    ]
}


def test_workflow_nodes_stay_on_the_first_worker(
    app: FastAPI, client: Client, remote: Client
) -> None:
    body(client.post("/api/scenes/import"))
    publish(app, "ba-001")
    publish(app, "ba-002")
    first, second = register(client, "win-01"), register(client, "win-02")
    hello(remote, first)
    hello(remote, second)
    created = body(client.post("/api/workflows", json={"name": "遠端序列", "definition": CHAIN}))
    started = body(
        client.post(
            f"/api/workflows/{created['id']}/runs", json={"target": "any", "headless": True}
        ),
        202,
    )
    assert started["target"] == "any"

    job = claim(remote, first)
    assert job is not None
    remote.post(
        f"{API}/runs/{job['runId']}/finish",
        json={"result": result_json(job["runId"])},
        headers=auth(first),
    )
    flow = body(client.get(f"/api/workflow-runs/{started['id']}"))
    assert flow["workerId"] == "win-01"

    # 第二個節點只給 win-01：本機與 win-02 都領不到
    assert cast("Worker", app.state.worker).source.claim() is None
    assert claim(remote, second) is None
    job = claim(remote, first)
    assert job is not None
    assert cast("JsonObject", job["inputs"])["recordId"] == "DEMO-1"
    remote.post(
        f"{API}/runs/{job['runId']}/finish",
        json={"result": result_json(job["runId"], output={"title": "遠端", "quantity": 1})},
        headers=auth(first),
    )
    assert body(client.get(f"/api/workflow-runs/{started['id']}"))["status"] == "passed"


def test_login_state_travels_and_comes_back(app: FastAPI, client: Client, remote: Client) -> None:
    body(client.post("/api/scenes/import"))
    state = services(app).storage.role_state("testsite-user")
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    token = register(client)
    hello(remote, token)
    queued = validate(client, "ba-004", target="remote")

    job = claim(remote, token)
    assert job is not None
    login = cast("JsonObject", job["login"])
    assert login["role"] == "testsite-user"
    assert "state" not in login
    assert base64.b64decode(str(job["loginState"])) == state.read_bytes()

    fresh = b'{"cookies": [{"name": "sid"}], "origins": []}'
    sent = remote.put(f"{API}/runs/{queued['id']}/role-state", content=fresh, headers=auth(token))
    assert sent.status_code == 204, sent.text
    assert state.read_bytes() == fresh
    broken = remote.put(f"{API}/runs/{queued['id']}/role-state", content=b"[]", headers=auth(token))
    assert error(broken, 422)["code"] == "role_state_invalid"

    remote.post(
        f"{API}/runs/{queued['id']}/finish",
        json={
            "result": result_json(
                queued["id"], role="testsite-user", login={"status": "passed", "role": "x"}
            )
        },
        headers=auth(token),
    )
    assert body(client.get("/api/roles/testsite-user"))["status"] == "logged_in"


# ---------------------------------------------------------------- M9a 收尾（M10.1）


def test_waiting_hint_location_filter_and_options(
    app: FastAPI, client: Client, remote: Client
) -> None:
    """排隊中而沒有線上的遠端 worker：執行頁說明在等什麼；執行報告可以依執行位置篩選。"""
    body(client.post("/api/scenes/import"))
    local_only = validate(client, target="local", engine="chromium")
    portal = services(app)
    assert portal.run_locations() == []  # 還沒有遠端 worker：不顯示這個篩選

    token = register(client)
    waiting = validate(client, target="remote", engine="chromium")
    assert portal.worker_wait(str(waiting["id"])) == {"worker": None}
    assert "目前沒有線上的遠端 worker" in client.get(f"/runs/{waiting['id']}").text
    assert portal.worker_wait(str(local_only["id"])) is None
    anywhere = validate(client, target="any", engine="chromium")
    assert portal.worker_wait(str(anywhere["id"])) is None  # 本機會執行

    hello(remote, token, browsers=["chromium"])
    assert portal.worker_wait(str(waiting["id"])) is None
    assert "data-worker-wait" not in client.get(f"/runs/{waiting['id']}").text
    job = claim(remote, token)
    assert job is not None
    assert job["runId"] == waiting["id"]

    assert portal.run_locations() == [("local", "本機"), ("win-01", "Windows 機器")]
    runs = cast("list[JsonObject]", body(client.get("/api/runs?worker=win-01"))["runs"])
    assert [run["id"] for run in runs] == [waiting["id"]]
    local_runs = cast("list[JsonObject]", body(client.get("/api/runs?worker=local"))["runs"])
    assert {run["id"] for run in local_runs} == {local_only["id"]}  # 「任一」還沒有人領取
    page = client.get("/runs?worker=win-01").text
    assert 'name="worker" value="win-01" checked' in page


def test_pinned_worker_offline_is_named(app: FastAPI, client: Client) -> None:
    """序列固定在某台 worker（required_worker），那台離線時提示寫出它的名稱。"""
    body(client.post("/api/scenes/import"))
    register(client)
    queued = validate(client, target="remote", engine="chromium")
    with services(app).sessions() as session:
        run = session.get(Run, str(queued["id"]))
        assert run is not None
        run.required_worker = "win-01"
        session.commit()
    assert services(app).worker_wait(str(queued["id"])) == {"worker": "Windows 機器"}
