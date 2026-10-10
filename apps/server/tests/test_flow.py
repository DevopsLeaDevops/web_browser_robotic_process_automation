"""真實瀏覽器：匯入 → 驗證 → 發布 → 執行 → BA-001 的出參交給 BA-002。

每個情境在 Chromium 與 Firefox 各跑一次（場景本身的瀏覽器）；佇列由測試呼叫 worker.run_once() 執行。
"""

import stat
from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import Client, Response

from rpa_server.services import Services
from rpa_worker import Worker
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

JsonObject = dict[str, object]


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with running() as url:
        yield url


def body(response: Response) -> JsonObject:
    assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def run_next(app: FastAPI, client: Client, run: JsonObject) -> JsonObject:
    """執行佇列裡的下一個任務，回傳它的結果。"""
    assert cast("Worker", app.state.worker).run_once() is True
    return body(client.get(f"/api/runs/{run['id']}"))


def test_validate_publish_run_and_chain(
    app: FastAPI, client: Client, site: str, engine: str
) -> None:
    body(client.post("/api/scenes/import"))
    options = {"engine": engine, "baseUrl": site}

    queued = body(
        client.post(
            "/api/scenes/ba-001/revisions/1/validate",
            json={"inputs": {"title": "Portal 驗證", "quantity": 4}, **options},
        )
    )
    validated = run_next(app, client, queued)

    assert validated["status"] == "passed", validated["error"]
    revision = body(client.get("/api/scenes/ba-001/revisions/1"))
    assert validated["scenarioHash"] == revision["contentHash"]
    assert revision["status"] == "passed"

    scene = body(client.post("/api/scenes/ba-001/revisions/1/publish"))
    assert scene["publishedRevision"] == 1

    executed = run_next(
        app,
        client,
        body(
            client.post(
                "/api/scenes/ba-001/runs",
                json={"inputs": {"title": "正式執行", "quantity": 5}, **options},
            )
        ),
    )
    assert executed["status"] == "passed", executed["error"]
    assert executed["purpose"] == "execution"
    output = cast("JsonObject", executed["output"])
    assert (output["title"], output["quantity"]) == ("正式執行", 5)

    # 上游的出參交給下游當入參（M6 會自動串接）
    chained = run_next(
        app,
        client,
        body(
            client.post(
                "/api/scenes/ba-002/revisions/1/validate",
                json={"inputs": {"recordId": output["recordId"]}, **options},
            )
        ),
    )
    assert chained["status"] == "passed", chained["error"]
    assert chained["output"] == output

    # 新版本是草稿：正式執行仍然用已發布的 v1
    files = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    saved = body(
        client.post(
            "/api/scenes/ba-001/revisions",
            json={"baseRevision": 1, "files": {"scenario.yaml": files["scenario.yaml"] + "\n"}},
        )
    )
    assert saved["number"] == 2
    again = body(client.post("/api/scenes/ba-001/runs", json={"inputs": {}, **options}))
    assert again["revision"] == 1
    assert body(client.get("/api/scenes/ba-001"))["latestStatus"] == "draft"


def test_publish_refuses_content_changed_on_disk(app: FastAPI, client: Client, site: str) -> None:
    engine = require_engine("chromium")
    body(client.post("/api/scenes/import"))
    queued = body(
        client.post(
            "/api/scenes/ba-001/revisions/1/validate",
            json={"inputs": {}, "engine": engine, "baseUrl": site},
        )
    )
    assert run_next(app, client, queued)["status"] == "passed"

    path = cast("Services", app.state.services).storage.scenario_path("ba-001", 1)
    path.chmod(stat.S_IWUSR | stat.S_IRUSR)
    path.write_text(path.read_text(encoding="utf-8") + "# 被改過\n", encoding="utf-8")

    response = client.post("/api/scenes/ba-001/revisions/1/publish")
    assert response.status_code == 409
    error = cast("JsonObject", body_of_error(response))
    assert error["code"] == "content_changed"


def body_of_error(response: Response) -> object:
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)["error"]
