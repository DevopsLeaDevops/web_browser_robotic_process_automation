"""/api 與頁面：場景、版本、驗證、發布門檻、執行、取消、報告。

不需要瀏覽器的情境用「缺少 Secret」讓執行停在入參階段；真正操作頁面的流程在 test_flow.py。
"""

import json
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_core.dsl import dynamic
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


@pytest.mark.parametrize("picked", [1, 2])
def test_queue_preserves_dynamic_inputs_until_execution(
    app: FastAPI, client: Client, monkeypatch: pytest.MonkeyPatch, picked: int
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("儲存與排隊不應求值")

    expression = "{{random:1:1001}}"
    source = NEEDS_SECRET.replace(
        "type: integer, minimum: 1, default: 1",
        "type: integer, enum: [1, 3], default: '" + expression + "'",
    )
    with monkeypatch.context() as patch:
        patch.setattr(dynamic, "_local_now", forbidden)
        patch.setattr("rpa_runner.contract.evaluate", forbidden)
        create(client, "needs-secret", source)
        queued = client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}})
        assert queued.status_code == 202, queued.text
    calls: list[tuple[int, int]] = []

    def pick(low: int, high: int) -> int:
        calls.append((low, high))
        return picked

    monkeypatch.setattr("rpa_core.dsl.dynamic.random.randint", pick)
    assert worker(app).run_once()
    detail = body(client.get(f"/api/runs/{queued.json()['id']}"))
    result = cast("JsonObject", detail["result"])
    assert result["input"] == {"count": picked}
    assert ("入參 count 不符合限制：enum" in cast("list[str]", result["problems"])) is (picked == 2)
    assert calls == [(1, 1001)]


def test_large_dynamic_range_can_be_saved_and_queued(client: Client) -> None:
    source = NEEDS_SECRET.replace(
        "type: integer, minimum: 1, default: 1",
        "pattern: '^[0-9]+$', default: '{{random:1:99999999999999999999}}'",
    )
    create(client, "needs-secret", source)
    queued = client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}})
    assert queued.status_code == 202, queued.text


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

    assert sorted(cast("list[str]", first["imported"])) == [
        "ba-001",
        "ba-001-script",
        "ba-002",
        "ba-003",
        "ba-004",
        "ba-005",
    ]
    # BA-004、BA-005 用到的登入角色依 roles.json 一起建立
    assert first["roles"] == ["testsite-user", "testsite-manager"]
    assert second["roles"] == []
    assert second["imported"] == []
    assert len(cast("list[str]", second["skipped"])) == 6
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


def test_dynamic_inputs_are_checked_but_kept_as_written(client: Client) -> None:
    """動態值：排入前只檢查寫法；執行紀錄保存原本的寫法，每次執行時才求值。"""
    client.post("/api/scenes/import")
    url = "/api/scenes/ba-001/revisions/1/validate"

    wrong = client.post(url, json={"inputs": {"title": "{{tody}}", "quantity": "{{random:1:99}}"}})
    queued = client.post(
        url, json={"inputs": {"title": "試驗 {{today}}", "quantity": "{{random:1:30}}"}}
    )

    assert (wrong.status_code, error_code(wrong)) == (422, "inputs_invalid")
    problems = cast("list[JsonObject]", cast("JsonObject", body(wrong)["error"])["problems"])
    assert [problem["name"] for problem in problems] == ["title"]
    assert "{{tody}}" in str(problems[0]["message"])
    assert queued.status_code == 202
    run = body(client.get(f"/api/runs/{body(queued)['id']}"))
    assert run["input"] == {"title": "試驗 {{today}}", "quantity": "{{random:1:30}}"}


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


def test_browser_window_follows_the_display(app: FastAPI, client: Client) -> None:
    """有圖形介面時預設有頭模式；沒有時預設無頭，要求有頭會被拒絕。"""
    client.post("/api/scenes/import")
    url = "/api/scenes/ba-001/revisions/1/validate"

    assert body(client.post(url, json={"inputs": {}}))["headless"] is True
    refused = client.post(url, json={"inputs": {}, "headless": False})
    assert refused.status_code == 422
    assert error_code(refused) == "display_unavailable"

    services(app).display = True
    headed = body(client.post(url, json={"inputs": {}}))
    assert headed["headless"] is False
    assert body(client.post(url, json={"inputs": {}, "headless": True}))["headless"] is True

    job = worker(app).source.claim()  # 依排入順序：第一個是無頭
    assert job is not None
    assert job.headless is True
    job = worker(app).source.claim()
    assert job is not None
    assert job.headless is False
    assert body(client.get(f"/api/runs/{headed['id']}"))["headless"] is False


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
        "沒有設定 Secret RPA_TEST_SECRET_NOT_SET：請在管理 Portal 的「登入與憑證」設定，"
        "或設定同名的環境變數"
    ]
    assert "report.html" in cast("list[str]", detail["files"])
    assert body(client.get("/api/scenes/needs-secret"))["latestStatus"] == "failed"

    report = client.get(f"/runs/{run['id']}/files/report.html")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in report.headers["content-security-policy"]
    # 在 Portal 裡看報告：最上面有回到運行詳情的連結（這次沒有錄影，沒有回看連結）
    assert f'<a href="/runs/{run["id"]}">' in report.text
    assert f"/runs/{run['id']}/replay" not in report.text
    data = client.get(f"/runs/{run['id']}/files/input.json")
    assert json.loads(data.text) == {"count": 1}
    # 標明 UTF-8：沒標的話，簡體中文系統的瀏覽器用 GBK 讀，中文變成亂碼
    assert data.headers["content-type"] == "application/json; charset=utf-8"
    assert data.headers["cache-control"] == "no-store"
    saved = client.get(f"/runs/{run['id']}/files/input.json?download=1")
    assert saved.headers["content-disposition"] == f'attachment; filename="{run["id"]}-input.json"'
    log = client.get(f"/runs/{run['id']}/files/report.html?download=1")
    assert (
        log.content == (services(app).storage.run_dir(str(run["id"])) / "report.html").read_bytes()
    )
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
    services(app).seed_examples_domain()
    create(client, "needs-secret", NEEDS_SECRET)
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))
    worker(app).run_once()

    for url in (
        "/scenes",
        "/domains",
        "/domains/testsite",
        "/scenes/ba-001",
        "/scenes/needs-secret",
        "/scenes/needs-secret/edit?focus=verify",
        "/scenes/ba-001/edit",
        "/scenes/ba-001-script/edit?revision=1",
        "/scenes/ba-001-script/edit?file=assertion.py",
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
    assert client.get("/scenes", follow_redirects=False).headers["location"] == "/domains/testsite"
    assert client.get("/domains/nope").status_code == 404
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


# ---------------------------------------------------------------- 領域


def test_domains_crud(client: Client) -> None:
    assert body(client.get("/api/domains")) == {"domains": []}

    created = client.post(
        "/api/domains", json={"id": "google", "name": "谷歌自動化", "description": "Google"}
    )
    second = client.post("/api/domains", json={"id": "microsoft", "name": "微軟自動化"})
    duplicate = client.post("/api/domains", json={"id": "google", "name": "重複"})
    bad_id = client.post("/api/domains", json={"id": "Google", "name": "大寫"})
    renamed = client.patch("/api/domains/google", json={"name": "Google 自動化"})

    assert created.status_code == 201
    assert (body(created)["position"], body(second)["position"]) == (0, 1)
    assert error_code(duplicate) == "domain_exists"
    assert error_code(bad_id) == "domain_id_invalid"
    assert body(renamed)["name"] == "Google 自動化"
    domains = cast("list[JsonObject]", body(client.get("/api/domains"))["domains"])
    assert [domain["id"] for domain in domains] == ["google", "microsoft"]

    client.post("/api/scenes", json={"id": "g-001", "name": "登入", "domainId": "google"})
    not_empty = client.delete("/api/domains/google")
    assert (not_empty.status_code, error_code(not_empty)) == (409, "domain_not_empty")
    assert body(client.delete("/api/domains/microsoft")) == {"deleted": "microsoft"}
    assert client.get("/api/domains/microsoft").status_code == 404


def test_domains_can_be_reordered(client: Client) -> None:
    """領域管理調整順序：場景管理的領域選單與 /scenes 的第一個領域跟著改（2026-10-22）。"""
    for domain_id, name in (("google", "谷歌自動化"), ("microsoft", "微軟自動化"), ("lab", "實驗")):
        assert client.post("/api/domains", json={"id": domain_id, "name": name}).status_code == 201

    def order() -> list[object]:
        return [
            item["id"]
            for item in cast("list[JsonObject]", body(client.get("/api/domains"))["domains"])
        ]

    response = client.put("/api/domains/order", json={"ids": ["lab", "google", "microsoft"]})
    assert response.status_code == 200, response.text
    reordered = body(response)
    domains = cast("list[JsonObject]", reordered["domains"])
    assert [(item["id"], item["position"]) for item in domains] == [
        ("lab", 0),
        ("google", 1),
        ("microsoft", 2),
    ]
    assert order() == ["lab", "google", "microsoft"]
    assert client.get("/scenes", follow_redirects=False).headers["location"] == "/domains/lab"
    side = client.get("/domains/google").text.split('id="sidenav"')[1].split("</nav>")[0]
    links = ["/domains/lab", "/domains/google", "/domains/microsoft", "/roles"]
    assert [side.index(f'href="{link}"') for link in links] == sorted(
        side.index(f'href="{link}"') for link in links
    )
    # 和伺服器的清單不同（少了、多了、重複）：409，順序不變
    for ids in (
        ["lab", "google"],
        ["lab", "google", "microsoft", "nope"],
        ["lab", "lab", "google"],
    ):
        response = client.put("/api/domains/order", json={"ids": ids})
        assert (response.status_code, error_code(response)) == (409, "domain_order_changed")
    assert order() == ["lab", "google", "microsoft"]
    # 新增的領域排在最後
    assert client.post("/api/domains", json={"id": "aws", "name": "AWS"}).status_code == 201
    assert order() == ["lab", "google", "microsoft", "aws"]
    page = client.get("/domains").text
    assert 'id="domain-order"' in page
    assert page.index('data-domain="lab"') < page.index('data-domain="aws"')


def test_scenes_belong_to_domains(client: Client) -> None:
    client.post("/api/domains", json={"id": "google", "name": "谷歌自動化"})
    client.post("/api/domains", json={"id": "microsoft", "name": "微軟自動化"})

    unknown = client.post("/api/scenes", json={"id": "x-001", "name": "甲", "domainId": "nope"})
    client.post("/api/scenes", json={"id": "g-001", "name": "甲", "domainId": "google"})
    client.post("/api/scenes", json={"id": "loose", "name": "乙"})

    assert error_code(unknown) == "domain_not_found"
    scenes = cast("list[JsonObject]", body(client.get("/api/scenes?domain=google"))["scenes"])
    assert [scene["id"] for scene in scenes] == ["g-001"]
    moved = body(client.patch("/api/scenes/g-001", json={"domainId": "microsoft"}))
    cleared = body(client.patch("/api/scenes/g-001", json={"domainId": None}))
    # 每個場景都在某個領域資料夾裡（M11）：沒指定、清掉領域的都放「未分類」
    assert (moved["domainId"], cleared["domainId"]) == ("microsoft", "unassigned")
    assert body(client.get("/api/scenes/loose"))["domainId"] == "unassigned"
    client.patch("/api/scenes/g-001", json={"domainId": "microsoft"})
    domain = body(client.get("/api/domains/microsoft"))
    assert domain["sceneCount"] == 1
    cards = cast("list[JsonObject]", domain["scenes"])
    assert [(card["id"], card["lastRun"], card["screenshotUrl"]) for card in cards] == [
        ("g-001", None, None)
    ]


def test_seed_creates_testsite_domain_once(app: FastAPI, client: Client) -> None:
    client.post("/api/scenes/import")  # 舊版本匯入的範例：還沒有領域
    client.post("/api/scenes", json={"id": "mine", "name": "自己的場景"})

    report = services(app).seed_examples_domain()

    assert report is not None
    assert report.imported == []  # 範例都已經存在，只是被放進領域
    domain = body(client.get("/api/domains/testsite"))
    assert domain["name"] == "測試網站自動化"
    cards = cast("list[JsonObject]", domain["scenes"])
    assert [card["id"] for card in cards] == [
        "ba-001",
        "ba-001-script",
        "ba-002",
        "ba-003",
        "ba-004",
        "ba-005",
    ]
    assert body(client.get("/api/scenes/mine"))["domainId"] == "unassigned"
    assert services(app).seed_examples_domain() is None


def test_testsite_domain_follows_the_language_until_renamed(app: FastAPI, client: Client) -> None:
    services(app).seed_examples_domain()  # 伺服器語言是繁中，資料庫存的是繁中名稱

    english = body(client.get("/api/domains/testsite?lang=en"))
    assert english["name"] == "Test site automation"
    assert str(english["description"]).startswith("Real cases that run against the local test site")
    assert "Test site automation" in client.get("/domains/testsite?lang=en").text
    assert body(client.get("/api/domains/testsite?lang=zh-Hans"))["name"] == "测试网站自动化"

    client.patch("/api/domains/testsite", json={"name": "我們的測試網站"})
    assert body(client.get("/api/domains/testsite?lang=en"))["name"] == "我們的測試網站"


def test_import_goes_into_the_given_domain(client: Client) -> None:
    client.post("/api/domains", json={"id": "lab", "name": "實驗"})

    report = body(client.post("/api/scenes/import", json={"domainId": "lab"}))

    assert len(cast("list[str]", report["imported"])) == 6
    assert body(client.get("/api/domains/lab"))["sceneCount"] == 6


def test_card_shows_last_run_and_screenshot(app: FastAPI, client: Client) -> None:
    client.post("/api/domains", json={"id": "lab", "name": "實驗"})
    create(client, "needs-secret", NEEDS_SECRET)
    client.patch("/api/scenes/needs-secret", json={"domainId": "lab"})
    run = body(client.post("/api/scenes/needs-secret/revisions/2/validate", json={"inputs": {}}))
    worker(app).run_once()
    # 這次執行停在入參階段沒有截圖；放一張進執行目錄，模擬有截圖的執行
    folder = services(app).storage.run_dir(str(run["id"]))
    (folder / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    (card,) = cast("list[JsonObject]", body(client.get("/api/domains/lab"))["scenes"])

    assert cast("JsonObject", card["lastRun"])["status"] == "failed"
    assert card["screenshotUrl"] == f"/runs/{run['id']}/files/screenshot.png"
    page = client.get("/domains/lab").text
    assert f'src="/runs/{run["id"]}/files/screenshot.png"' in page
    assert 'data-status="failed"' in page


def test_cli_recognizes_the_portal(app: FastAPI) -> None:
    from rpa_cli.serve import PORTAL_TITLE

    assert app.title == PORTAL_TITLE
