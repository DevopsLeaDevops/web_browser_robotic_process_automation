"""M4 的真實瀏覽器流程：人工登入（假的登入視窗）→ 執行、需要登入、重新執行；自動登入；
錄製稿 → 驗證 → 發布 → 正式執行；逐步調試。

人工登入的瀏覽器視窗在 CI 沒辦法開，換成假的子程序：收到「完成登入」時用 HTTP 登入測試網站，
把 cookie 寫成登入狀態檔。之後的檢查、執行都是真的瀏覽器。
"""

import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from textwrap import dedent
from typing import cast

import pytest
import yaml
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_server.services import Services
from rpa_worker import Worker
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

JsonObject = dict[str, object]

FAKE_CAPTURE = dedent(
    """\
    import http.cookiejar
    import json
    import os
    import sys
    import urllib.request
    from pathlib import Path

    settings = json.loads(os.environ["RPA_LOGIN"])
    state = Path(sys.argv[sys.argv.index("--state") + 1])
    site = settings["loginUrl"].rsplit("/login", 1)[0]
    print(json.dumps({"event": "ready"}), flush=True)
    for line in sys.stdin:
        if line.strip() == "cancel":
            print(json.dumps({"event": "cancelled"}), flush=True)
            sys.exit(2)
        if line.strip() == "finish":
            break
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    account = {"username": os.environ["FAKE_ACCOUNT"], "password": os.environ["FAKE_PASSWORD"]}
    request = urllib.request.Request(
        site + "/api/login",
        data=json.dumps(account).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener.open(request).read()
    cookies = [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": -1,
         "httpOnly": True, "secure": False, "sameSite": "Lax"}
        for c in jar
    ]
    state.write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")
    print(json.dumps({"event": "saved"}), flush=True)
    """
)


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


def body(response: Response, status: int | None = None) -> JsonObject:
    if status is not None:
        assert response.status_code == status, response.text
    else:
        assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def run_next(app: FastAPI, client: Client, run: JsonObject) -> JsonObject:
    assert cast("Worker", app.state.worker).run_once() is True
    return body(client.get(f"/api/runs/{run['id']}"))


def wait_for(
    read: Callable[[], JsonObject], ready: Callable[[JsonObject], bool], seconds: float = 120
) -> JsonObject:
    end = time.monotonic() + seconds
    while True:
        data = read()
        if ready(data):
            return data
        assert time.monotonic() < end, data
        time.sleep(0.2)


def fake_capture(tmp: Path, account: str, password: str) -> Callable[..., subprocess.Popen[str]]:
    script = tmp / "fake_capture.py"
    script.write_text(FAKE_CAPTURE, encoding="utf-8")

    def launcher(
        command: list[str], *, env: dict[str, str], **options: object
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, str(script), *command[3:]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={**env, "FAKE_ACCOUNT": account, "FAKE_PASSWORD": password},
        )

    return launcher


def point_role_at(client: Client, role: str, site: str, engine: str) -> None:
    body(
        client.patch(
            f"/api/roles/{role}",
            json={"loginUrl": f"{site}/login", "checkUrl": f"{site}/account", "engine": engine},
        )
    )


def test_manual_login_needs_login_and_rerun(
    app: FastAPI, client: Client, site: str, engine: str, tmp_path: Path
) -> None:
    body(client.post("/api/scenes/import"))
    point_role_at(client, "testsite-user", site, engine)
    point_role_at(client, "testsite-manager", site, engine)
    options: JsonObject = {"engine": engine, "baseUrl": site, "inputs": {}}

    # 還沒登入：停在需要登入，不執行任何步驟；角色也標成需要登入
    first = run_next(
        app, client, body(client.post("/api/scenes/ba-004/revisions/1/validate", json=options))
    )
    assert first["status"] == "needs_login", first["error"]
    assert "login.png" in cast("list[str]", first["files"])
    assert body(client.get("/api/roles/testsite-user"))["status"] == "needs_login"
    assert body(client.get("/api/scenes/ba-004"))["latestStatus"] == "failed"
    run_page = client.get(f"/runs/{first['id']}").text
    assert 'href="/roles#role-testsite-user"' in run_page
    assert 'data-action="rerun"' in run_page

    # 人工登入（假的登入視窗）：完成後先確認真的登入了，才存成角色的登入狀態
    roles = services(app).roles
    roles.display = True
    roles.launcher = fake_capture(tmp_path, "user", "user-pass")
    started = body(client.post("/api/roles/testsite-user/login"), 202)
    assert started["activity"] == "login"
    wait_for(
        lambda: body(client.get("/api/roles/testsite-user")),
        lambda role: cast("JsonObject", role["session"])["status"] == "waiting",
    )
    assert 'data-action="finish-login" data-role="testsite-user"' in client.get("/roles").text
    body(client.post("/api/roles/testsite-user/login/finish"), 202)
    role = wait_for(
        lambda: body(client.get("/api/roles/testsite-user")), lambda role: not role["activity"]
    )
    assert role["status"] == "logged_in", role
    assert cast("JsonObject", role["session"])["status"] == "done"
    assert role["stateSavedAt"] is not None

    # 同樣的入參再執行一次：通過，而且看到的是一般使用者自己的資料
    again = run_next(app, client, body(client.post(f"/api/runs/{first['id']}/rerun", json={}), 202))
    assert again["status"] == "passed", again["error"]
    assert again["output"] == {"userName": "王小明", "todoCount": 2}

    # 主管還沒登入：不會借用一般使用者的登入狀態
    manager = run_next(
        app, client, body(client.post("/api/scenes/ba-005/revisions/1/validate", json=options))
    )
    assert manager["status"] == "needs_login"

    # 登入失效：檢查與執行都發現需要登入
    request = urllib.request.Request(f"{site}/api/sessions/expire", data=b"", method="POST")
    urllib.request.urlopen(request, timeout=10).read()
    body(client.post("/api/roles/testsite-user/check"), 202)
    role = wait_for(
        lambda: body(client.get("/api/roles/testsite-user")), lambda role: not role["activity"]
    )
    assert role["status"] == "needs_login"

    # 登出：刪除登入狀態
    cleared = body(client.delete("/api/roles/testsite-user/state"))
    assert (cleared["status"], cleared["stateSavedAt"]) == ("none", None)


def test_auto_login_from_secret(app: FastAPI, client: Client, site: str, engine: str) -> None:
    steps = "\n".join(
        [
            f"- {{ id: open, action: goto, url: '{site}/login' }}",
            "- { id: user, action: fill, target: { label: 帳號 }, value: manager }",
            "- { id: pw, action: fill, target: { label: 密碼 },"
            " value: '{{ secrets.TESTSITE_MANAGER_PASSWORD }}' }",
            "- { id: go, action: click, target: { role: button, name: 登入 } }",
            "- { id: wait, action: waitFor, url: /account }",
        ]
    )
    body(
        client.post(
            "/api/roles",
            json={
                "id": "auto-manager",
                "name": "自動登入的主管",
                "loginUrl": f"{site}/login",
                "checkUrl": f"{site}/account",
                "check": "{ testId: current-user }",
                "engine": engine,
                "autoLogin": steps,
            },
        ),
        201,
    )
    page = client.get("/roles").text
    assert "TESTSITE_MANAGER_PASSWORD" in page  # 列在「還沒設定」的 Secrets

    body(client.post("/api/roles/auto-manager/check"), 202)
    role = wait_for(
        lambda: body(client.get("/api/roles/auto-manager")), lambda role: not role["activity"]
    )
    assert role["status"] == "needs_login"  # 沒有密碼，不能自動登入
    assert "TESTSITE_MANAGER_PASSWORD" in str(role["message"])

    body(client.put("/api/secrets/TESTSITE_MANAGER_PASSWORD", json={"value": "manager-pass"}))
    body(client.post("/api/roles/auto-manager/check"), 202)
    role = wait_for(
        lambda: body(client.get("/api/roles/auto-manager")), lambda role: not role["activity"]
    )
    assert role["status"] == "logged_in", role["message"]
    assert role["message"]  # 自動登入過
    assert services(app).storage.role_state("auto-manager").is_file()


RECORDED = dedent(
    """\
    import re
    from playwright.sync_api import Playwright, sync_playwright, expect


    def run(playwright: Playwright) -> None:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("{site}/")
        page.get_by_label("標題", exact=True).click()
        page.get_by_label("標題", exact=True).fill("錄製的紀錄")
        page.get_by_label("數量", exact=True).fill("3")
        page.get_by_role("button", name="建立紀錄").click()
        expect(page.locator("#record-status")).to_contain_text("已建立")

        # ---------------------
        context.close()
        browser.close()


    with sync_playwright() as playwright:
        run(playwright)
    """
)


def test_recording_is_validated_published_and_run(
    app: FastAPI, client: Client, site: str, engine: str
) -> None:
    """路線圖 M4 的驗收：錄製一段操作 → 草稿 → 驗證 → 發布 → 用別的入參正式執行成功。"""
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}))
    recording = body(
        client.post(
            "/api/recordings/import",
            json={
                "source": RECORDED.replace("{site}", site),
                "target": {"sceneId": "rec-e2e", "new": True, "name": "錄製", "domainId": "lab"},
                "engine": engine,
            },
        ),
        201,
    )
    assert recording["status"] == "done"
    assert recording["warnings"] == []
    revision = body(client.get("/api/scenes/rec-e2e/revisions/1"))
    loaded: object = yaml.safe_load(cast("dict[str, str]", revision["files"])["scenario.yaml"])
    inputs = cast("dict[str, JsonObject]", cast("JsonObject", loaded)["inputs"])
    assert [spec["default"] for spec in inputs.values()] == ["錄製的紀錄", "3"]

    options: JsonObject = {"engine": engine, "baseUrl": site, "inputs": {}, "headless": True}
    validated = run_next(
        app, client, body(client.post("/api/scenes/rec-e2e/revisions/1/validate", json=options))
    )
    assert validated["status"] == "passed", validated["error"]
    body(client.post("/api/scenes/rec-e2e/revisions/1/publish"))

    title, quantity = inputs
    production = {**options, "inputs": {title: "正式執行", quantity: "5"}}
    run = run_next(app, client, body(client.post("/api/scenes/rec-e2e/runs", json=production), 202))
    assert run["status"] == "passed", run["error"]
    assert (run["purpose"], run["revision"]) == ("execution", 1)


def test_step_debugging(app: FastAPI, client: Client, site: str, engine: str) -> None:
    body(client.post("/api/scenes/import"))
    started = body(
        client.post(
            "/api/scenes/ba-001/debug",
            json={
                "engine": engine,
                "baseUrl": site,
                "inputs": {"title": '{{"{{"}}today}}', "quantity": 2},
            },
        ),
        202,
    )
    session = str(started["id"])
    assert started["headless"] is True  # 測試環境沒有圖形介面
    wait_for(
        lambda: body(client.get(f"/api/debug/{session}")), lambda data: data["status"] != "starting"
    )
    page = client.get("/scenes/ba-001/debug").text
    assert f'data-session="{session}"' in page

    # 同一個場景再按開始：回到進行中的工作階段
    assert body(client.post("/api/scenes/ba-001/debug", json={}), 202)["id"] == session

    state: JsonObject = {}
    for index in range(4):
        state = body(client.post(f"/api/debug/{session}/steps/{index}", json={}))
        steps = cast("list[JsonObject]", state["steps"])
        assert steps[index]["status"] == "passed", steps[index]
    assert state["nextIndex"] == 4
    shot = str(state["screenshotUrl"])
    image = client.get(shot)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"

    # 送出按鈕有副作用而且點過了：再點要確認
    again = client.post(f"/api/debug/{session}/steps/3", json={})
    assert cast("JsonObject", body(again, 409)["error"])["code"] == "confirm_required"

    # 「執行到這裡」只執行還沒執行的步驟
    state = body(client.post(f"/api/debug/{session}/run-to/5"))
    record = cast("JsonObject", cast("JsonObject", state["facts"])["record"])
    assert record["title"] == "{{today}}"
    assert client.post(f"/api/debug/{session}/run-to/2").status_code == 409

    located = body(
        client.post(f"/api/debug/{session}/locate", json={"locator": "{ css: '#record-id' }"})
    )
    assert cast("JsonObject", located["located"])["count"] == 1
    bad = client.post(f"/api/debug/{session}/locate", json={"locator": "{ role: nope }"})
    assert bad.status_code == 422

    # 改 YAML 存成新版本，換到新版本繼續：執行過的步驟依 id 保留
    files = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    text = files["scenario.yaml"].replace("name: 讀取畫面上的紀錄詳情", "name: 讀取紀錄")
    text = text.replace(
        "inputs:\n", "inputs:\n  added: { type: integer, default: '{{random:7:7}}' }\n"
    )
    saved = body(
        client.post(
            "/api/scenes/ba-001/revisions",
            json={"baseRevision": 1, "files": {"scenario.yaml": text}},
        ),
        201,
    )
    state = body(client.post(f"/api/debug/{session}/reload", json={"revision": saved["number"]}))
    assert state["revision"] == 2
    assert state["inputs"] == {"title": "{{today}}", "quantity": 2, "added": 7}
    # 再次重載也不重複求值，新增入參的動態預設值仍有補上。
    state = body(client.post(f"/api/debug/{session}/reload", json={"revision": saved["number"]}))
    assert state["inputs"] == {"title": "{{today}}", "quantity": 2, "added": 7}
    steps = cast("list[JsonObject]", state["steps"])
    assert steps[5]["name"] == "讀取紀錄"
    assert steps[5]["status"] == "passed"
    assert state["nextIndex"] == 6

    reset = body(client.post(f"/api/debug/{session}/reset"))
    assert reset["nextIndex"] == 0
    state = body(client.post(f"/api/debug/{session}/run-to/5"))
    record = cast("JsonObject", cast("JsonObject", state["facts"])["record"])
    assert record["title"] == "{{today}}"
    assert body(client.delete(f"/api/debug/{session}"))["closed"] == session
    assert client.get(f"/api/debug/{session}").status_code == 404
    assert not services(app).storage.debug_dir(session).exists()


def test_debug_rejects_script_scenarios(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    response = client.post("/api/scenes/ba-001-script/debug", json={})
    assert response.status_code == 422
