"""端到端：「瀏覽器＋Python」組合場景在管理 Portal 驗證、發布、執行（ADR 0020 第 1 節的驗收）。

用 scenarios/examples/browser-python 的三個場景：下載銷售報表（DSL 的 download 步驟）→ 分店彙總
（Python 節點，運行環境模式）→ 上傳分店彙總（DSL 的 upload 步驟）。每個場景先單獨驗證、發布（Python
節點與上傳場景的檔案入參用上傳的檔案），再把三個節點接成組合場景：驗證、發布、正式執行，中間的資料
以出參傳遞（file、number、object），所有節點在同一台（本機的）Worker。

Portal 用 uvicorn 在背景執行緒啟動（含背景 worker），場景用 Chromium 無頭執行；運行環境和
packages/rpa_runner/tests/test_python_nodes.py 一樣用假的（標準函式庫的 venv）。
"""

import json
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import httpx2
import pytest
import uvicorn

from rpa_runner.pyruntime import ENV_RUNTIME, MANIFEST, platform_tag
from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_server.services import Services
from testsite.browsers import require_engine
from testsite.server import export_csv, running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "scenarios" / "examples" / "browser-python"
MONTH = "2026-11"
JsonObject = dict[str, object]


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """假的 RPA Python 運行環境 1.0.0：Portal 的背景 worker 與它開的 Runner 都用它。"""
    root = tmp_path / "runtime"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root)], check=True)
    manifest = {"version": "1.0.0", "platform": platform_tag(), "python": sys.version.split()[0]}
    (root / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(ENV_RUNTIME, str(root))
    monkeypatch.setenv("RPA_CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture
def portal(tmp_path: Path, runtime: None) -> Iterator[str]:
    data = tmp_path / "data"
    settings = Settings(
        data_dir=data, database_url=sqlite_url(data / "rpa.db"), seed_examples=False
    )
    app = create_app(settings)
    # 本機的運行環境（Portal 平常每分鐘問一次；測試直接給，不受其他測試的快取影響）
    cast("Services", app.state.services).queue.runtimes = lambda: ("1.0.0",)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "Portal 沒有啟動"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        sock.close()


def body(response: httpx2.Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def wait_for(client: httpx2.Client, path: str) -> JsonObject:
    deadline = time.monotonic() + 240
    while True:
        data = body(client.get(path))
        if data["finished"]:
            return data
        assert time.monotonic() < deadline, f"{path} 沒有結束"
        time.sleep(0.2)


def create(client: httpx2.Client, scene: str, files: dict[str, Path]) -> None:
    """建立場景、存進範例的檔案（版本 2），再單獨驗證後才發布。"""
    body(client.post("/api/scenes", json={"id": scene, "name": "暫名"}), 201)
    texts = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    saved = client.post(f"/api/scenes/{scene}/revisions", json={"baseRevision": 1, "files": texts})
    assert body(saved, 201)["number"] == 2


def validate_and_publish(client: httpx2.Client, scene: str, inputs: JsonObject) -> JsonObject:
    started = client.post(
        f"/api/scenes/{scene}/revisions/2/validate",
        json={"inputs": inputs, "engine": "chromium", "headless": True},
    )
    run = wait_for(client, f"/api/runs/{body(started, 202)['id']}")
    assert run["status"] == "passed", (scene, run["error"])
    assert client.post(f"/api/scenes/{scene}/revisions/2/publish").status_code < 400
    return run


def upload(client: httpx2.Client, name: str, data: bytes) -> JsonObject:
    created = body(client.post("/api/files", params={"name": name}, content=data), 201)
    return {"file": created["file"]}


def test_browser_and_python_nodes_validate_publish_and_run(portal: str) -> None:
    require_engine("chromium")
    name, report = export_csv(MONTH)
    with running() as site, httpx2.Client(base_url=portal, timeout=30) as client:
        create(client, "download-sales", {"scenario.yaml": EXAMPLE / "download-sales.yaml"})
        create(
            client,
            "summarize-sales",
            {
                "scenario.yaml": EXAMPLE / "summarize-sales" / "scenario.yaml",
                "automation.py": EXAMPLE / "summarize-sales" / "automation.py",
            },
        )
        create(client, "upload-summary", {"scenario.yaml": EXAMPLE / "upload-summary.yaml"})
        for scene in ("download-sales", "upload-summary"):
            client.patch(f"/api/scenes/{scene}", json={"baseUrl": site})

        downloaded = validate_and_publish(client, "download-sales", {"month": MONTH})
        file = cast("JsonObject", cast("JsonObject", downloaded["output"])["report"])
        assert (file["name"], file["size"]) == (name, len(report))
        summarized = validate_and_publish(
            client, "summarize-sales", {"report": upload(client, "sales.csv", report)}
        )
        summary = cast("JsonObject", summarized["output"])
        validate_and_publish(
            client, "upload-summary", {"summary": upload(client, "summary.csv", b"a,b\n")}
        )

        definition = json.loads((EXAMPLE / "workflow.json").read_text(encoding="utf-8"))
        for node in cast("list[JsonObject]", definition["nodes"]):
            node["revision"] = 2
        definition["nodes"][0]["inputs"] = {"month": {"value": MONTH}}
        created = body(
            client.post(
                "/api/workflows", json={"name": "下載、彙總、上傳", "definition": definition}
            ),
            201,
        )
        workflow = created["id"]
        options: JsonObject = {"engine": "chromium", "headless": True}
        for purpose in ("validation", "execution"):
            started = client.post(
                f"/api/workflows/{workflow}/runs", json={**options, "purpose": purpose}
            )
            finished = wait_for(client, f"/api/workflow-runs/{body(started, 202)['id']}")
            assert finished["status"] == "passed", (purpose, finished["error"])
            nodes = {
                str(node["id"]): cast("JsonObject", node["run"])
                for node in cast("list[JsonObject]", finished["nodes"])
            }
            # 同一台 Worker；Python 節點的出參和單獨驗證時相同（同一個月的報表）
            assert {run["workerId"] for run in nodes.values()} == {"local"}
            outputs = cast("JsonObject", nodes["summarize"]["output"])
            assert outputs["total"] == summary["total"]
            assert outputs["byBranch"] == summary["byBranch"]
            uploaded = cast("JsonObject", nodes["upload"]["output"])
            assert uploaded == {"receivedName": "分店彙總.csv"}
            if purpose == "validation":
                published = client.post(f"/api/workflows/{workflow}/revisions/1/publish")
                assert published.status_code < 400, published.text

            # 合併回看：Python 節點是步驟時間軸（三步：讀取、加總、寫出）
            replay = body(client.get(f"/api/workflow-runs/{finished['id']}/replay"))
            segments = cast("list[JsonObject]", cast("JsonObject", replay["composite"])["segments"])
            python = [segment for segment in segments if segment["kind"] == "python"]
            assert [segment["node"] for segment in python] == ["summarize"]
            steps = [
                step
                for step in cast("list[JsonObject]", replay["steps"])
                if step["node"] == "summarize"
            ]
            assert [step["rawId"] for step in steps] == ["read", "sum", "write"]
