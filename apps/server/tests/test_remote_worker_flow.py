"""M9a 驗收：真的 HTTP、真的瀏覽器，執行交給遠端 worker。

管理 Portal 用 uvicorn 在背景執行緒啟動，兩個埠：管理頁面與 Worker API；這台電腦不執行
（local_worker=False），所以每個任務都一定經過 Worker API。遠端 worker 是同一個程序裡的
另一個執行緒（RemoteJobSource + Worker），和 `rpa worker` 用的是同一套程式。

驗證 BA-001 → 發布 → 驗證 BA-002 → 發布 → 試驗場序列 BA-001 → BA-002；
報告與截圖從管理 Portal 看得到，序列的兩個節點都在同一台 worker。Chromium 與 Firefox 各跑一次。
M10.1：worker 用裝置頁的邀請經由 Client API 配對（真的 HTTP），拿到的權杖再用在 Worker API。
"""

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import uvicorn
from httpx2 import Client, Response

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_worker import Worker
from rpa_worker.environment import WorkerInfo, code_fingerprint
from rpa_worker.pairing import pair, parse_invite
from rpa_worker.remote import RemoteJobSource, WorkerClient
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"
JsonObject = dict[str, object]


@dataclass(frozen=True)
class Portal:
    url: str
    worker_api: str


def _socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture
def portal(tmp_path: Path) -> Iterator[Portal]:
    pages, workers = _socket(), _socket()
    worker_port = int(workers.getsockname()[1])
    data = tmp_path / "data"
    settings = Settings(
        data_dir=data,
        database_url=sqlite_url(data / "rpa.db"),
        examples_dir=DEMO,
        seed_examples=False,
        worker_port=worker_port,
        worker_host="127.0.0.1",  # 邀請裡的伺服器網址就是這個埠
        local_worker=False,
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [pages, workers]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "Portal 沒有啟動"
        time.sleep(0.05)
    try:
        yield Portal(
            f"http://127.0.0.1:{pages.getsockname()[1]}", f"http://127.0.0.1:{worker_port}"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        pages.close()
        workers.close()


def body(response: Response) -> JsonObject:
    assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


@pytest.fixture
def remote_worker(portal: Portal, engine: str, tmp_path: Path) -> Iterator[str]:
    """登記一台 worker、用邀請配對，在背景執行緒用 Worker API 領取任務；回傳 worker 代號。"""
    with Client(base_url=portal.url, timeout=30) as client:
        body(client.post("/api/workers", json={"id": "box", "name": "測試機"}))
        invited = cast("JsonObject", body(client.post("/api/workers/box/invite"))["invite"])
    paired = pair(parse_invite(str(invited["line"])), "worker")
    assert (paired.server, paired.device, paired.name) == (portal.worker_api, "box", "測試機")
    token = paired.token
    info = WorkerInfo(name="box", fingerprint=code_fingerprint(), browsers=(engine,), display=False)
    source = RemoteJobSource(
        WorkerClient(portal.worker_api, token),
        info,
        tmp_path / "worker",
        heartbeat_seconds=1,
        claim_wait_seconds=2,
    )
    worker = Worker(source, poll_seconds=0.2)
    source.on_cancel = worker.cancel
    worker.start()
    try:
        yield "box"
    finally:
        worker.stop(timeout=60)
        source.close()


def wait_run(client: Client, run_id: object, timeout: float = 180) -> JsonObject:
    deadline = time.monotonic() + timeout
    while True:
        run = body(client.get(f"/api/runs/{run_id}"))
        if run["finished"]:
            return run
        assert time.monotonic() < deadline, f"{run_id} 沒有結束：{run['status']}"
        time.sleep(0.5)


def wait_workflow(client: Client, run_id: object, timeout: float = 300) -> JsonObject:
    deadline = time.monotonic() + timeout
    while True:
        run = body(client.get(f"/api/workflow-runs/{run_id}"))
        if run["finished"]:
            return run
        assert time.monotonic() < deadline, f"{run_id} 沒有結束：{run['status']}"
        time.sleep(0.5)


def validate_and_publish(client: Client, scene: str, inputs: JsonObject, engine: str) -> JsonObject:
    queued = body(
        client.post(
            f"/api/scenes/{scene}/revisions/1/validate",
            json={"inputs": inputs, "engine": engine, "headless": True, "target": "remote"},
        )
    )
    run = wait_run(client, queued["id"])
    assert run["status"] == "passed", run["error"]
    body(client.post(f"/api/scenes/{scene}/revisions/1/publish"))
    return run


@pytest.mark.parametrize("dag", [False, True])
def test_remote_worker_runs_validation_and_playground(
    portal: Portal, site: str, engine: str, remote_worker: str, dag: bool
) -> None:
    with Client(base_url=portal.url, timeout=30) as client:
        body(client.post("/api/scenes/import"))
        for scene in ("ba-001", "ba-002"):
            body(client.patch(f"/api/scenes/{scene}", json={"baseUrl": site}))

        created = validate_and_publish(client, "ba-001", {"title": "遠端 worker"}, engine)
        assert created["workerId"] == remote_worker
        assert created["target"] == "remote"
        # 報告與截圖從管理 Portal 看得到（worker 上傳的執行目錄）
        report = client.get(f"/runs/{created['id']}/files/report.html")
        assert report.status_code == 200
        assert "遠端 worker" in report.text
        assert client.get(f"/runs/{created['id']}/files/screenshot.png").status_code == 200
        record = cast("JsonObject", created["output"])
        validate_and_publish(client, "ba-002", {"recordId": record["recordId"]}, engine)

        definition: JsonObject = {
            "nodes": [
                {
                    "id": "n1",
                    "sceneId": "ba-001",
                    "revision": 1,
                    "inputs": {"title": {"value": "序列"}},
                },
                {
                    "id": "n2",
                    "sceneId": "ba-002",
                    "revision": 1,
                    "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
                },
            ]
        }
        if dag:
            definition.update(
                {"version": 2, "mode": "dag", "edges": [{"source": "n1", "target": "n2"}]}
            )
            cast("list[JsonObject]", definition["nodes"]).reverse()
        workflow = body(
            client.post("/api/workflows", json={"name": "遠端", "definition": definition})
        )
        started = body(
            client.post(
                f"/api/workflows/{workflow['id']}/runs",
                json={"engine": engine, "headless": True},  # 本機不執行：預設改成任一
            )
        )
        finished = wait_workflow(client, started["id"])
        assert finished["status"] == "passed", finished["error"]
        assert finished["workerId"] == remote_worker
        nodes = cast("list[JsonObject]", finished["nodes"])
        assert [cast("JsonObject", node["run"])["workerId"] for node in nodes] == [
            remote_worker,
            remote_worker,
        ]
        listed = cast("list[JsonObject]", body(client.get("/api/workers"))["workers"])
        assert listed[0]["status"] in ("online", "busy")
        assert listed[0]["sameVersion"] is True


def test_local_target_is_refused_when_this_computer_does_not_run(portal: Portal) -> None:
    with Client(base_url=portal.url, timeout=30) as client:
        body(client.post("/api/scenes/import"))
        refused = client.post(
            "/api/scenes/ba-001/revisions/1/validate",
            json={"inputs": {}, "target": "local", "headless": True},
        )
        assert refused.status_code == 409
        # 也還沒有遠端 worker：預設（任一）沒有人能執行
        nobody = client.post(
            "/api/scenes/ba-001/revisions/1/validate", json={"inputs": {}, "headless": True}
        )
        assert nobody.status_code == 409
        assert cast("JsonObject", nobody.json()["error"])["code"] == "no_remote_worker"
