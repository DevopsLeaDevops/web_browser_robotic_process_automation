"""/api 與頁面：場景、版本、驗證、發布門檻、執行、取消、報告。

不需要瀏覽器的情境用「缺少 Secret」讓執行停在入參階段；真正操作頁面的流程在 test_flow.py。
"""

import json
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_server.services import Services
from rpa_worker import Worker

ROOT = Path(__file__).resolve().parents[3]
BA_001 = (ROOT / "scenarios" / "demo" / "ba-001.yaml").read_text(encoding="utf-8")

# 需要一個不存在的 Secret：執行停在入參階段，不會啟動瀏覽器
NEEDS_SECRET = """\
schemaVersion: 1
id: needs-secret
name: 缺少機密
category: 測試
secrets: [RPA_TEST_SECRET_NOT_SET]
inputs:
  count: { type: integer, minimum: 1, default: 1 }
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
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error_code(response: Response) -> str:
    error = body(response)["error"]
    assert isinstance(error, dict)
    return str(cast("JsonObject", error)["code"])


def worker(app: FastAPI) -> Worker:
    return cast("Worker", app.state.worker)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def create(client: Client, scene_id: str, yaml_text: str) -> None:
    """建立場景，並把 v2 存成指定的內容。"""
    assert client.post("/api/scenes", json={"id": scene_id, "name": "暫名"}).status_code == 201
    files = {"scenario.yaml": yaml_text}
    response = client.post(
        f"/api/scenes/{scene_id}/revisions", json={"baseRevision": 1, "files": files}
    )
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------- 場景與版本


def test_create_scene_makes_a_valid_draft(client: Client) -> None:
    assert body(client.get("/api/scenes")) == {"scenes": []}

    response = client.post("/api/scenes", json={"id": "demo-x", "name": "示範", "category": "測試"})

    assert response.status_code == 201
    scene = body(response)
    assert scene["latestRevision"] == 1
    assert scene["latestStatus"] == "draft"
    assert scene["publishedRevision"] is None
    detail = body(client.get("/api/scenes/demo-x"))
    revisions = cast("list[JsonObject]", detail["revisions"])
    assert [revision["number"] for revision in revisions] == [1]
    files = body(client.get("/api/scenes/demo-x/revisions/1"))["files"]
    assert "id: demo-x" in cast("dict[str, str]", files)["scenario.yaml"]


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"id": "Demo", "name": "大寫"}, 422, "scene_id_invalid"),
        ({"id": "demo-x", "name": "  "}, 422, "scene_name_missing"),
        ({"id": "demo-x", "name": "重複"}, 409, "scene_exists"),
    ],
)
def test_create_scene_errors(client: Client, payload: JsonObject, status: int, code: str) -> None:
    client.post("/api/scenes", json={"id": "demo-x", "name": "已存在"})

    response = client.post("/api/scenes", json=payload)

    assert response.status_code == status
    assert error_code(response) == code


def test_save_revision_checks_base_and_content(client: Client) -> None:
    client.post("/api/scenes", json={"id": "ba-001", "name": "暫名"})
    url = "/api/scenes/ba-001/revisions"

    stale = client.post(url, json={"baseRevision": 0, "files": {"scenario.yaml": BA_001}})
    broken = client.post(
        url,
        json={
            "baseRevision": 1,
            "files": {"scenario.yaml": BA_001.replace("action: click", "action: tap")},
        },
    )
    other_id = client.post(
        url,
        json={
            "baseRevision": 1,
            "files": {"scenario.yaml": BA_001.replace("id: ba-001", "id: ba-009")},
        },
    )
    saved = client.post(
        url, json={"baseRevision": 1, "files": {"scenario.yaml": BA_001}, "note": "換成 BA-001"}
    )

    assert (stale.status_code, error_code(stale)) == (409, "stale_base")
    assert (broken.status_code, error_code(broken)) == (422, "revision_invalid")
    issues = cast("list[JsonObject]", cast("JsonObject", body(broken)["error"])["issues"])
    assert issues[0]["line"] is not None
    assert issues[0]["step"] == 4
    assert error_code(other_id) == "revision_invalid"
    assert saved.status_code == 201
    assert body(saved)["number"] == 2
    scene = body(client.get("/api/scenes/ba-001"))
    assert (scene["name"], scene["category"], scene["latestRevision"]) == (
        "建立範例紀錄",
        "範例資料",
        2,
    )


def test_import_examples_once(client: Client) -> None:
    first = body(client.post("/api/scenes/import"))
    second = body(client.post("/api/scenes/import"))

    assert sorted(cast("list[str]", first["imported"])) == ["ba-001", "ba-001-script", "ba-002"]
    assert second["imported"] == []
    assert len(cast("list[str]", second["skipped"])) == 3
    script = body(client.get("/api/scenes/ba-001-script"))
    assert script["kind"] == "script"
    files = cast(
        "dict[str, str]", body(client.get("/api/scenes/ba-001-script/revisions/1"))["files"]
    )
    assert sorted(files) == ["assertion.py", "automation.py", "scenario.yaml"]


def test_update_scene_base_url(client: Client) -> None:
    client.post("/api/scenes", json={"id": "demo-x", "name": "示範"})

    bad = client.patch("/api/scenes/demo-x", json={"baseUrl": "ftp://x"})
    good = client.patch("/api/scenes/demo-x", json={"baseUrl": "http://127.0.0.1:8765"})
    cleared = client.patch("/api/scenes/demo-x", json={"baseUrl": None})

    assert error_code(bad) == "base_url_invalid"
    assert body(good)["baseUrl"] == "http://127.0.0.1:8765"
    assert body(cleared)["baseUrl"] is None


# ---------------------------------------------------------------- 執行


def test_run_requests_are_checked_before_queueing(client: Client) -> None:
    client.post("/api/scenes/import")

    not_published = client.post("/api/scenes/ba-001/runs", json={"inputs": {}})
    bad_inputs = client.post(
        "/api/scenes/ba-001/revisions/1/validate", json={"inputs": {"quantity": 31, "x": 1}}
    )
    publish_early = client.post("/api/scenes/ba-001/revisions/1/publish")

    assert (not_published.status_code, error_code(not_published)) == (409, "not_published")
    assert (bad_inputs.status_code, error_code(bad_inputs)) == (422, "inputs_invalid")
    problems = cast("list[JsonObject]", cast("JsonObject", body(bad_inputs)["error"])["problems"])
    assert [problem["name"] for problem in problems] == ["x", "quantity"]
    assert (publish_early.status_code, error_code(publish_early)) == (409, "not_validated")
    assert body(client.get("/api/runs")) == {"runs": []}


def test_validation_is_queued_once_per_idempotency_key(client: Client) -> None:
    client.post("/api/scenes/import")
    request = {"inputs": {"title": "甲"}, "engine": "chromium", "idempotencyKey": "k-1"}

    first = client.post("/api/scenes/ba-001/revisions/1/validate", json=request)
    again = client.post("/api/scenes/ba-001/revisions/1/validate", json=request)

    assert first.status_code == 202
    run = body(first)
    assert (run["status"], run["purpose"], run["revision"]) == ("queued", "validation", 1)
    assert body(again)["id"] == run["id"]
    assert len(cast("list[object]", body(client.get("/api/runs"))["runs"])) == 1
    assert body(client.get("/api/scenes/ba-001"))["latestStatus"] == "validating"


def test_cancel_queued_validation(app: FastAPI, client: Client) -> None:
    client.post("/api/scenes/import")
    run = body(client.post("/api/scenes/ba-001/revisions/1/validate", json={"inputs": {}}))

    cancelled = body(client.post(f"/api/runs/{run['id']}/cancel"))

    assert cancelled["status"] == "cancelled"
    assert body(client.get("/api/scenes/ba-001"))["latestStatus"] == "failed"
    assert worker(app).run_once() is False


def test_failed_run_keeps_evidence_and_reports(app: FastAPI, client: Client) -> None:
    create(client, "needs-secret", NEEDS_SECRET)
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))

    assert worker(app).run_once() is True

    detail = body(client.get(f"/api/runs/{run['id']}"))
    assert detail["status"] == "failed"
    assert detail["output"] is None
    assert detail["error"] == "入參有 1 個問題，沒有啟動瀏覽器"
    result = cast("JsonObject", detail["result"])
    assert result["problems"] == [
        "沒有設定 Secret RPA_TEST_SECRET_NOT_SET（環境變數 RPA_TEST_SECRET_NOT_SET）"
    ]
    assert "report.html" in cast("list[str]", detail["files"])
    assert body(client.get("/api/scenes/needs-secret"))["latestStatus"] == "failed"

    report = client.get(f"/runs/{run['id']}/files/report.html")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in report.headers["content-security-policy"]
    data = client.get(f"/runs/{run['id']}/files/input.json")
    assert json.loads(data.text) == {"count": 1}
    assert client.get(f"/runs/{run['id']}/files/%2E%2E/%2E%2E/rpa.db").status_code == 404
    assert client.get(f"/runs/{run['id']}/files/missing.png").status_code == 404


def test_run_list_filters(client: Client) -> None:
    client.post("/api/scenes/import")
    create(client, "needs-secret", NEEDS_SECRET)
    client.post("/api/scenes/ba-001/revisions/1/validate", json={"inputs": {}})
    client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}})

    def ids(query: str) -> list[str]:
        runs = cast("list[JsonObject]", body(client.get(f"/api/runs?{query}"))["runs"])
        return [str(run["sceneId"]) for run in runs]

    assert ids("") == ["needs-secret", "ba-001"]
    assert ids("scene=ba-001") == ["ba-001"]
    assert ids("category=測試&category=範例資料") == ["needs-secret", "ba-001"]
    assert ids("status=passed") == []
    assert ids("purpose=execution") == []


def test_recover_marks_interrupted_runs(app: FastAPI, client: Client) -> None:
    create(client, "needs-secret", NEEDS_SECRET)
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))
    job = worker(app).source.claim()
    assert job is not None

    assert services(app).recover() == 1

    detail = body(client.get(f"/api/runs/{run['id']}"))
    assert detail["status"] == "failed"
    assert "中斷" in str(detail["error"])
    assert body(client.get("/api/scenes/needs-secret"))["latestStatus"] == "failed"


# ---------------------------------------------------------------- 頁面與安全


def test_pages_render(app: FastAPI, client: Client) -> None:
    client.post("/api/scenes/import")
    create(client, "needs-secret", NEEDS_SECRET)
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))
    worker(app).run_once()

    for url in (
        "/scenes",
        "/scenes?q=ba&category=範例資料",
        "/scenes/ba-001",
        "/scenes/ba-001/edit",
        "/scenes/ba-001-script/edit?revision=1",
        "/scenes/ba-001/run?purpose=validation",
        "/runs",
        "/runs?scene=ba-001&scene=needs-secret&status=failed",
        f"/runs/{run['id']}",
        "/recording",
        "/playground",
    ):
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.headers["content-type"].startswith("text/html"), url

    assert client.get("/", follow_redirects=False).headers["location"] == "/scenes"
    missing = client.get("/scenes/nope")
    assert missing.status_code == 404
    assert "找不到場景 nope" in missing.text
    assert client.get("/scenes/ba-001/run?purpose=execution").status_code == 409


def test_language(client: Client) -> None:
    switched = client.get("/lang/en?next=/runs", follow_redirects=False)
    assert switched.headers["location"] == "/runs"
    assert "rpa_lang=en" in switched.headers["set-cookie"]
    assert '<html lang="en">' in client.get("/scenes").text  # Cookie 已經存起來
    assert (
        client.get("/lang/en?next=https://evil.example", follow_redirects=False).headers["location"]
        == "/"
    )
    english = client.get("/api/scenes/nope?lang=en")
    assert cast("JsonObject", body(english)["error"])["message"] == "Scenario nope not found"


def test_cross_site_writes_are_blocked(client: Client) -> None:
    response = client.post(
        "/api/scenes",
        json={"id": "demo-x", "name": "跨站"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert body(client.get("/api/scenes")) == {"scenes": []}
