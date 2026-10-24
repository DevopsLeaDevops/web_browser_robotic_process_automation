"""專案空間（2026-10-23）：專案的管理（像領域管理）、組合場景放進專案、專案頁只列自己的組合場景。

節點的執行換成假的執行器（不開瀏覽器）；不需要真實瀏覽器。
"""

import re
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_runner.contract import check_inputs
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_server.domain import now
from rpa_server.middleware import LANG_COOKIE
from rpa_server.models import Project, Revision, Scene
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]

CHAIN: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "專案"}}},
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
    record_video: bool = False,
) -> RunResult:
    """假的執行器：一律通過，出參取同名的入參。"""
    scenario = validate_file(path).scenario
    assert scenario is not None
    assert run_id is not None
    resolved, problems = check_inputs(scenario, inputs)
    assert problems == []
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
            name: resolved.get(name, "DEMO-1" if spec.type == "string" else 1)
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


def ids(client: Client) -> list[object]:
    return [
        item["id"]
        for item in cast("list[JsonObject]", body(client.get("/api/projects"))["projects"])
    ]


def side(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html.split('id="sidenav"')[1].split("</nav>")[0])


@pytest.fixture
def published(app: FastAPI, client: Client) -> None:
    """範例場景放進「實驗」領域，直接在資料庫把 BA-001 與 BA-002 的第 1 版標成已發布。"""
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    body(client.post("/api/scenes/import", json={"domainId": "lab"}))
    with services(app).sessions() as session:
        for scene_id in ("ba-001", "ba-002"):
            scene = session.get(Scene, scene_id)
            revision = session.scalars(
                select(Revision).where(Revision.scene_id == scene_id, Revision.number == 1)
            ).one()
            assert scene is not None
            revision.status = "passed"
            revision.published_at = now()
            scene.published_number = 1
        session.commit()


# ---------------------------------------------------------------- 專案管理


def test_projects_are_managed_like_domains(client: Client) -> None:
    """新增（代號不能重複、要合規則、要有名稱）、改名稱與說明、調整順序、刪除。"""
    assert ids(client) == []
    created = body(
        client.post("/api/projects", json={"id": "billing", "name": " 帳務 ", "description": ""}),
        201,
    )
    assert (created["id"], created["name"], created["description"]) == ("billing", "帳務", None)
    assert (created["position"], created["compositeCount"]) == (0, 0)
    body(client.post("/api/projects", json={"id": "orders", "name": "訂單"}), 201)
    body(client.post("/api/projects", json={"id": "hr", "name": "人資"}), 201)
    assert ids(client) == ["billing", "orders", "hr"]

    again = client.post("/api/projects", json={"id": "billing", "name": "x"})
    assert error(again, 409)["code"] == "project_exists"
    assert error(client.post("/api/projects", json={"id": "壞", "name": "x"}), 422)["code"] == (
        "project_id_invalid"
    )
    assert error(client.post("/api/projects", json={"id": "ok", "name": " "}), 422)["code"] == (
        "project_name_missing"
    )

    updated = body(
        client.patch("/api/projects/billing", json={"name": "帳務專案", "description": "對帳"})
    )
    assert (updated["name"], updated["description"]) == ("帳務專案", "對帳")
    blank = client.patch("/api/projects/billing", json={"name": ""})
    assert error(blank, 422)["code"] == "project_name_missing"
    assert error(client.patch("/api/projects/nope", json={"name": "x"}), 404)["code"] == (
        "project_not_found"
    )

    reordered = body(client.put("/api/projects/order", json={"ids": ["hr", "billing", "orders"]}))
    projects = cast("list[JsonObject]", reordered["projects"])
    assert [(item["id"], item["position"]) for item in projects] == [
        ("hr", 0),
        ("billing", 1),
        ("orders", 2),
    ]
    for wrong in (["hr", "billing"], ["hr", "billing", "orders", "x"], ["hr", "hr", "billing"]):
        response = client.put("/api/projects/order", json={"ids": wrong})
        assert error(response, 409)["code"] == "project_order_changed"
    assert ids(client) == ["hr", "billing", "orders"]
    # 新增的專案排在最後
    body(client.post("/api/projects", json={"id": "aws", "name": "AWS"}), 201)
    assert ids(client) == ["hr", "billing", "orders", "aws"]

    assert body(client.delete("/api/projects/aws")) == {"deleted": "aws"}
    assert error(client.delete("/api/projects/aws"), 404)["code"] == "project_not_found"
    assert ids(client) == ["hr", "billing", "orders"]


def test_composites_belong_to_projects(
    app: FastAPI, client: Client, published: None, worker: Worker
) -> None:
    """組合場景新增時放進專案、可以移到其他專案或不屬於任何專案；有組合場景的專案不能刪。"""
    body(client.post("/api/projects", json={"id": "billing", "name": "帳務"}), 201)
    body(client.post("/api/projects", json={"id": "orders", "name": "訂單"}), 201)
    first = body(
        client.post(
            "/api/workflows",
            json={"name": "帳務流程", "definition": CHAIN, "projectId": "billing"},
        ),
        201,
    )
    second = body(
        client.post("/api/workflows", json={"name": "沒有專案", "definition": CHAIN}), 201
    )
    assert (first["projectId"], second["projectId"]) == ("billing", None)
    unknown = client.post("/api/workflows", json={"name": "x", "projectId": "nope"})
    assert error(unknown, 404)["code"] == "project_not_found"

    detail = body(client.get("/api/projects/billing"))
    assert detail["compositeCount"] == 1
    assert [item["id"] for item in cast("list[JsonObject]", detail["workflows"])] == [first["id"]]
    assert error(client.delete("/api/projects/billing"), 409)["code"] == "project_not_empty"

    # 移到其他專案：只改資料庫，資料夾不動；不存在的專案 404
    moved = body(client.patch(f"/api/workflows/{second['id']}", json={"projectId": "orders"}))
    assert moved["projectId"] == "orders"
    bad = client.patch(f"/api/workflows/{second['id']}", json={"projectId": "nope"})
    assert error(bad, 404)["code"] == "project_not_found"
    untouched = body(client.patch(f"/api/workflows/{second['id']}", json={"archived": False}))
    assert untouched["projectId"] == "orders"  # 沒帶 projectId 時不變

    # 重新載入領域資料夾（資料庫是資料夾的索引）不會把專案洗掉
    body(client.post("/api/domains/composites/reload"))
    assert body(client.get(f"/api/workflows/{first['id']}"))["projectId"] == "billing"

    # 專案頁的最近執行只列這個專案的組合場景
    started = body(client.post(f"/api/workflows/{second['id']}/runs", json={"headless": True}), 202)
    while worker.run_once():
        pass
    orders = client.get("/projects/orders").text
    billing = client.get("/projects/billing").text
    assert str(started["id"]) in orders
    assert str(started["id"]) not in billing

    # 空字串：不屬於任何專案；之後專案可以刪除
    loose = body(client.patch(f"/api/workflows/{first['id']}", json={"projectId": ""}))
    assert loose["projectId"] is None
    assert body(client.delete("/api/projects/billing")) == {"deleted": "billing"}
    assert body(client.get(f"/api/workflows/{first['id']}"))["projectId"] is None


def test_project_pages_and_navigation(client: Client, published: None) -> None:
    """專案空間（第一級選單，在叢集管理前面）：二級選單是專案；專案頁就是組合場景自動化。"""
    # 還沒有專案：專案空間轉到專案管理
    assert client.get("/workspace", follow_redirects=False).headers["location"] == "/projects"
    assert client.get("/composites", follow_redirects=False).headers["location"] == "/workspace"
    empty = client.get("/projects").text
    assert 'data-action="new-project"' in empty
    assert "還沒有專案" in empty

    body(client.post("/api/projects", json={"id": "billing", "name": "帳務"}), 201)
    body(client.post("/api/projects", json={"id": "orders", "name": "訂單"}), 201)
    flow = body(
        client.post(
            "/api/workflows", json={"name": "帳務流程", "definition": CHAIN, "projectId": "billing"}
        ),
        201,
    )
    loose = body(client.post("/api/workflows", json={"name": "沒有專案", "definition": CHAIN}), 201)

    # 專案空間轉到第一個專案（依專案管理的順序）
    assert client.get("/workspace", follow_redirects=False).headers["location"] == (
        "/projects/billing"
    )
    body(client.put("/api/projects/order", json={"ids": ["orders", "billing"]}))
    assert client.get("/workspace", follow_redirects=False).headers["location"] == (
        "/projects/orders"
    )

    page = client.get("/projects/billing").text
    top = re.findall(r'href="([^"]+)"', page.split('id="topnav"')[1].split("</nav>")[0])
    assert top == ["/scenes", "/recording", "/runs", "/workspace", "/devices", "/domains"]
    assert 'href="/workspace" class="active"' in page
    assert side(page) == ["/projects/orders", "/projects/billing"]
    assert 'href="/projects/billing" title="帳務" class="active"' in page
    assert f'data-workflow="{flow["id"]}"' in page
    assert f'data-workflow="{loose["id"]}"' not in page  # 只列這個專案的
    assert 'data-project="billing"' in page
    assert 'href="/projects">' in page  # 「管理專案」
    # 新增組合場景的表單預設放進這個專案
    assert '<option value="billing" selected>' in page
    assert "還沒有組合場景" in client.get("/projects/orders").text
    assert client.get("/projects/nope").status_code == 404

    # 專案管理（管理後台）：順序、組合場景數、還沒分到專案的組合場景
    manage = client.get("/projects").text
    assert side(manage) == ["/domains", "/projects"]
    assert 'id="project-order"' in manage
    assert manage.index('data-project="orders"') < manage.index('data-project="billing"')
    assert f'href="/playground/{loose["id"]}#composite-settings"' in manage
    assert f'href="/playground/{flow["id"]}#composite-settings"' not in manage
    # 有組合場景的專案沒有刪除按鈕
    assert 'data-action="delete-project" data-project="billing"' not in manage
    assert 'data-action="delete-project" data-project="orders"' in manage

    # 組合場景頁：設定可以選專案，麵包屑連回專案
    editor = client.get(f"/playground/{flow['id']}").text
    assert '<a href="/projects/billing">帳務</a>' in editor
    settings = editor.split('id="composite-settings"')[1].split("</form>")[0]
    assert '<option value="billing" selected>' in settings
    # 自由試驗場新增時預設第一個專案
    playground = client.get("/playground").text
    assert '<option value="orders" selected>' in playground
    assert 'href="/workspace"' in playground


def test_upgraded_project_name_follows_the_language(app: FastAPI, client: Client) -> None:
    """升級時建立的專案「組合場景自動化」：沒改過名稱時跟著介面語言，改過就照改的內容。"""
    with services(app).sessions() as session:
        session.add(
            Project(
                id="composites",
                name="組合場景自動化",
                description="升級時自動建立，原本的組合場景都放在這裡。",
                position=0,
                created_at=now(),
            )
        )
        session.commit()
    client.cookies.set(LANG_COOKIE, "en")
    english = body(client.get("/api/projects/composites"))
    assert english["name"] == "Composite automation"
    assert str(english["description"]).startswith("Created automatically")
    body(client.patch("/api/projects/composites", json={"name": "主專案"}))
    assert body(client.get("/api/projects/composites"))["name"] == "主專案"
