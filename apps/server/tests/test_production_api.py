"""M4 的 API（不需要瀏覽器）：登入角色與 Secrets、貼上錄製稿、入參出參表單、重新執行。

需要真實瀏覽器的登入、調試流程在 test_production_flow.py。
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import cast

from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_server.models import Role
from rpa_server.services import Services
from rpa_worker import Worker

JsonObject = dict[str, object]

ROLE = {
    "id": "erp-clerk",
    "name": "ERP 職員",
    "loginUrl": "http://127.0.0.1:9/login",
    "checkUrl": "http://127.0.0.1:9/home",
    "check": "{ testId: current-user }",
}

RECORDING = dedent(
    """\
    from playwright.sync_api import Playwright, sync_playwright, expect


    def run(playwright: Playwright) -> None:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("http://127.0.0.1:8765/")
        page.get_by_label("標題").fill("錄製的標題")
        page.get_by_label("數量").fill("2")
        page.get_by_label("Password").fill("top-secret")
        page.get_by_role("button", name="建立紀錄").click()
        page.get_by_text("選單").hover()
        context.close()
        browser.close()
    """
)


def body(response: Response, status: int | None = None) -> JsonObject:
    if status is not None:
        assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response) -> JsonObject:
    data = body(response)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


# ---------------------------------------------------------------- 角色與 Secrets


def test_roles_crud_and_validation(client: Client) -> None:
    created = body(client.post("/api/roles", json=ROLE), 201)
    assert created["status"] == "none"
    assert created["check"] == {"testId": "current-user"}
    assert created["autoLogin"] is None
    assert created["engine"] == "chromium"

    assert error(client.post("/api/roles", json=ROLE))["code"] == "role_exists"
    assert (
        error(client.post("/api/roles", json={**ROLE, "id": "Bad Id"}))["code"] == "role_id_invalid"
    )
    bad_check = client.post("/api/roles", json={**ROLE, "id": "x", "check": "{ role: nope }"})
    assert error(bad_check)["code"] == "role_check_invalid"
    bad_url = client.post("/api/roles", json={**ROLE, "id": "x", "loginUrl": "ftp://a"})
    assert error(bad_url)["code"] == "role_url_invalid"

    steps = (
        "- { id: open, action: goto, url: https://example.com/login }\n"
        "- { id: pw, action: fill, target: { label: 密碼 }, value: '{{ secrets.ERP_PASSWORD }}' }\n"
    )
    updated = body(
        client.patch("/api/roles/erp-clerk", json={"autoLogin": steps, "name": "職員"}), 200
    )
    assert updated["name"] == "職員"
    assert updated["autoLogin"] == steps
    assert updated["loginUrl"] == ROLE["loginUrl"]  # 沒送的欄位不變
    bad_steps = client.patch("/api/roles/erp-clerk", json={"autoLogin": "- { id: x, action: fly }"})
    assert error(bad_steps)["code"] == "role_steps_invalid"
    assert error(bad_steps)["issues"]

    listed = body(client.get("/api/roles"))
    roles = cast("list[JsonObject]", listed["roles"])
    assert [role["id"] for role in roles] == ["erp-clerk"]
    assert listed["display"] is False

    assert body(client.delete("/api/roles/erp-clerk"))["deleted"] == "erp-clerk"
    assert client.get("/api/roles/erp-clerk").status_code == 404


def test_manual_login_needs_a_display(client: Client) -> None:
    body(client.post("/api/roles", json=ROLE), 201)
    response = client.post("/api/roles/erp-clerk/login")
    assert response.status_code == 422
    assert error(response)["code"] == "display_unavailable"
    assert error(client.post("/api/roles/erp-clerk/login/finish"))["code"] == "login_not_active"


def test_secret_values_are_never_returned(app: FastAPI, client: Client) -> None:
    saved = body(client.put("/api/secrets/ERP_PASSWORD", json={"value": "s3cret-value"}), 200)
    assert set(saved) == {"name", "updatedAt"}
    assert "s3cret-value" not in client.get("/api/secrets").text
    assert "s3cret-value" not in client.get("/api/roles").text
    assert "s3cret-value" not in client.get("/roles").text
    store = services(app).storage.secrets
    assert json.loads(store.read_text(encoding="utf-8"))["ERP_PASSWORD"]["value"] == "s3cret-value"
    if os.name != "nt":
        assert store.stat().st_mode & 0o777 == 0o600

    assert (
        error(client.put("/api/secrets/bad-name", json={"value": "x"}))["code"]
        == "secret_name_invalid"
    )
    assert (
        error(client.put("/api/secrets/OK", json={"value": ""}))["code"] == "secret_value_missing"
    )
    assert body(client.delete("/api/secrets/ERP_PASSWORD"))["deleted"] == "ERP_PASSWORD"
    assert client.delete("/api/secrets/ERP_PASSWORD").status_code == 404


def test_roles_from_examples_and_in_use(client: Client) -> None:
    report = body(client.post("/api/scenes/import"))
    assert report["roles"] == ["testsite-user", "testsite-manager"]

    role = body(client.get("/api/roles/testsite-user"))
    assert role["usedBy"] == ["ba-004"]
    assert role["engine"] == "firefox"
    assert error(client.delete("/api/roles/testsite-user"))["code"] == "role_in_use"

    scene = body(client.get("/api/scenes/ba-004"))
    assert scene["needs"] == {
        "role": "testsite-user",
        "roleRegistered": True,
        "roleStatus": "none",
        "secrets": [],
    }
    page = client.get("/roles").text
    assert 'id="role-testsite-user"' in page
    assert "ba-004" in page


def test_run_without_registered_role_fails_before_the_browser(app: FastAPI, client: Client) -> None:
    body(client.post("/api/scenes/import"))
    body(client.delete("/api/roles/testsite-manager"), 409)  # BA-005 還在用
    # 直接刪資料庫列，模擬場景用到、但還沒登記的角色
    with services(app).sessions() as session:
        role = session.get(Role, "testsite-manager")
        assert role is not None
        session.delete(role)
        session.commit()

    queued = body(client.post("/api/scenes/ba-005/revisions/1/validate", json={"inputs": {}}), 202)
    assert cast("Worker", app.state.worker).run_once() is True
    run = body(client.get(f"/api/runs/{queued['id']}"))
    assert run["status"] == "failed"
    assert "testsite-manager" in str(run["error"])
    result = cast("JsonObject", run["result"])
    stages = cast("list[JsonObject]", result["stages"])
    assert [stage["name"] for stage in stages] == [
        "input",
        "login",
        "automation",
        "verify",
        "output",
    ]
    assert stages[1]["status"] == "failed"
    assert stages[2]["status"] == "skipped"

    again = body(client.post(f"/api/runs/{queued['id']}/rerun", json={}), 202)
    assert again["id"] != queued["id"]
    assert (again["purpose"], again["revision"], again["status"]) == ("validation", 1, "queued")


# ---------------------------------------------------------------- 錄製


def test_pasted_recording_becomes_a_new_scene(client: Client) -> None:
    client.post("/api/domains", json={"id": "lab", "name": "實驗"})
    created = body(
        client.post(
            "/api/recordings/import",
            json={
                "source": RECORDING,
                "target": {
                    "sceneId": "rec-001",
                    "new": True,
                    "name": "錄製的範例",
                    "domainId": "lab",
                },
                "engine": "firefox",
            },
        ),
        201,
    )
    assert created["status"] == "done"
    assert created["revision"] == 1
    assert created["source"] == "import"
    warnings = cast("list[JsonObject]", created["warnings"])
    assert [warning["line"] for warning in warnings] == [13]
    files = cast("dict[str, str]", created["files"])
    assert "top-secret" not in files["raw.py"]
    assert 'fill("***")' in files["raw.py"]
    assert "secrets.REC_001_PASSWORD" in files["scenario.yaml"]

    scene = body(client.get("/api/scenes/rec-001"))
    assert (scene["name"], scene["domainId"], scene["latestStatus"]) == (
        "錄製的範例",
        "lab",
        "draft",
    )
    revision = body(client.get("/api/scenes/rec-001/revisions/1"))
    text = cast("dict[str, str]", revision["files"])["scenario.yaml"]
    assert "engine: firefox" in text
    assert "top-secret" not in text
    needs = cast("JsonObject", scene["needs"])
    assert needs["secrets"] == [{"name": "REC_001_PASSWORD", "set": False}]

    listed = cast("list[JsonObject]", body(client.get("/api/recordings"))["recordings"])
    assert [item["id"] for item in listed] == [created["id"]]
    page = client.get(f"/recordings/{created['id']}").text
    assert "top-secret" not in page
    assert "rec-001" in page


def test_pasted_recording_becomes_a_new_revision(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    created = body(
        client.post(
            "/api/recordings/import",
            json={"source": RECORDING, "target": {"sceneId": "ba-001"}, "roleId": "testsite-user"},
        ),
        201,
    )
    assert created["revision"] == 2
    revision = body(client.get("/api/scenes/ba-001/revisions/2"))
    text = cast("dict[str, str]", revision["files"])["scenario.yaml"]
    assert "id: ba-001" in text
    assert "role: testsite-user" in text
    assert revision["note"] == f"由錄製 {created['id']} 轉換"


def test_recording_errors(client: Client) -> None:
    target = {"sceneId": "rec-x", "new": True, "name": "x"}
    empty = client.post("/api/recordings/import", json={"source": " ", "target": target})
    assert error(empty)["code"] == "recording_empty"
    broken = client.post("/api/recordings/import", json={"source": "def (", "target": target})
    assert error(broken)["code"] == "recording_unconvertible"
    unknown = client.post(
        "/api/recordings/import", json={"source": RECORDING, "target": {"sceneId": "nope"}}
    )
    assert error(unknown)["code"] == "scene_not_found"
    no_role = client.post(
        "/api/recordings/import", json={"source": RECORDING, "target": target, "roleId": "ghost"}
    )
    assert error(no_role)["code"] == "role_not_found"
    no_display = client.post(
        "/api/recordings", json={"target": target, "url": "https://example.com"}
    )
    assert error(no_display)["code"] == "display_unavailable"
    assert body(client.get("/api/recordings"))["recordings"] == []


FAKE_CODEGEN = dedent(
    """\
    import sys
    from pathlib import Path

    output = Path(sys.argv[sys.argv.index("--output") + 1])
    output.write_text(sys.argv[-2], encoding="utf-8")
    """
)


def test_recording_on_this_computer_with_a_fake_codegen(
    app: FastAPI, client: Client, tmp_path: Path
) -> None:
    """codegen 換成假的：把錄製稿寫到 --output 後結束（像使用者關掉視窗）。"""
    script = tmp_path / "fake_codegen.py"
    script.write_text(FAKE_CODEGEN, encoding="utf-8")
    seen: list[list[str]] = []

    def launcher(command: list[str], **options: object) -> subprocess.Popen[str]:
        seen.append(command)
        return subprocess.Popen(
            [sys.executable, str(script), *command[3:-1], RECORDING, command[-1]], text=True
        )

    recordings = services(app).recordings
    recordings.display = True
    recordings.launcher = launcher
    started = body(
        client.post(
            "/api/recordings",
            json={
                "target": {"sceneId": "rec-002", "new": True, "name": "現場錄製"},
                "url": "http://127.0.0.1:8765/",
                "engine": "chromium",
            },
        ),
        202,
    )
    assert started["status"] == "recording"
    command = seen[0]
    assert command[1:4] == ["-m", "playwright", "codegen"]
    assert command[-1] == "http://127.0.0.1:8765/"
    assert "--load-storage" not in command

    record: JsonObject = {}
    for _ in range(100):
        record = body(client.get(f"/api/recordings/{started['id']}"))
        if record["status"] != "recording":
            break
        time.sleep(0.1)
    assert record["status"] == "done", record
    folder = services(app).storage.recording_dir(str(started["id"]))
    assert not (folder / ".recording.py").exists()  # 含密碼的暫存原始稿已刪除
    assert "top-secret" not in (folder / "raw.py").read_text(encoding="utf-8")
    assert body(client.get("/api/scenes/rec-002"))["latestRevision"] == 1


# ---------------------------------------------------------------- 入參與出參的表單


def test_contract_form_rewrites_only_the_two_sections(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    before = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])

    saved = body(
        client.put(
            "/api/scenes/ba-001/contract",
            json={
                "baseRevision": 1,
                "inputs": [
                    {
                        "name": "headline",
                        "previous": "title",
                        "type": "string",
                        "default": "新標題",
                        "minLength": 1,
                    },
                    {
                        "name": "quantity",
                        "previous": "quantity",
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 50,
                    },
                ],
                "outputs": [
                    {
                        "name": "recordId",
                        "type": "string",
                        "from": "{{ facts.record.recordId }}",
                        "pattern": "^DEMO-",
                    },
                ],
                "note": "改名",
            },
        ),
        201,
    )
    assert saved["number"] == 2
    assert saved["note"] == "改名"
    after = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/2"))["files"])
    text = after["scenario.yaml"]
    assert "  headline:\n    type: string\n    default: 新標題\n    minLength: 1\n" in text
    assert "maximum: 50" in text
    assert "'{{ inputs.headline }}'" in text
    assert "inputs.title" not in text
    assert text.split("inputs:")[0] == before["scenario.yaml"].split("inputs:")[0]
    assert text.split("\nbrowser:")[1] == before["scenario.yaml"].split("\nbrowser:")[1].replace(
        "inputs.title", "inputs.headline"
    )

    stale = client.put(
        "/api/scenes/ba-001/contract", json={"baseRevision": 1, "inputs": [], "outputs": []}
    )
    assert error(stale)["code"] == "stale_base"
    invalid = client.put(
        "/api/scenes/ba-001/contract",
        json={
            "baseRevision": 2,
            "inputs": [{"name": "x", "type": "integer", "default": "abc"}],
            "outputs": [],
        },
    )
    assert error(invalid)["code"] == "revision_invalid"
    assert error(invalid)["issues"]
    duplicate = client.put(
        "/api/scenes/ba-001/contract",
        json={"baseRevision": 2, "inputs": [{"name": "a"}, {"name": "a"}], "outputs": []},
    )
    assert error(duplicate)["code"] == "contract_duplicate"


def test_scene_and_card_pages_link_to_debugging(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    client.post("/api/domains", json={"id": "lab", "name": "實驗"})
    client.patch("/api/scenes/ba-001", json={"domainId": "lab"})
    scene = client.get("/scenes/ba-001").text
    assert 'href="/scenes/ba-001/debug"' in scene
    assert 'id="contract-editor"' in scene
    assert 'href="/recording?scene=ba-001"' in scene
    script = client.get("/scenes/ba-001-script").text
    assert 'href="/scenes/ba-001-script/debug"' not in script
    debug = client.get("/scenes/ba-001/debug").text
    assert 'id="debug-start"' in debug
    assert client.get("/recording?scene=ba-001").status_code == 200
