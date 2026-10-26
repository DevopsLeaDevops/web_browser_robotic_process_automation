"""M4 的 API（不需要瀏覽器）：登入角色與 Secrets、貼上錄製稿、入參出參表單、重新執行。

需要真實瀏覽器的登入、調試流程在 test_production_flow.py。
"""

import dataclasses
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_server.config import Settings, sqlite_url
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


SCRIPTED_CAPTURE = dedent(
    """\
    import json
    import os
    import sys
    from pathlib import Path

    state = Path(sys.argv[sys.argv.index("--state") + 1])
    reactions = json.loads(os.environ["FAKE_REACTIONS"])
    url = "http://127.0.0.1:9/login?next=/home"

    def emit(event, **details):
        print(json.dumps({"event": event, **details}), flush=True)

    emit("ready")
    for line in sys.stdin:
        if line.strip() == "cancel":
            emit("cancelled")
            sys.exit(2)
        if line.strip() != "finish":
            continue
        reaction = reactions.pop(0)
        if reaction == "legacy":  # 舊版：不確認、直接存
            state.write_text(os.environ["FAKE_STATE"], encoding="utf-8")
            emit("saved")
            sys.exit(0)
        emit("checking")
        if reaction == "saved":
            state.write_text(os.environ["FAKE_STATE"], encoding="utf-8")
            emit("saved", verified=True)
            sys.exit(0)
        if reaction == "refused":
            emit("not_logged_in", url=None, message="打不開 http://127.0.0.1:9/home", closed=False)
            continue
        emit("not_logged_in", url=url, message=None, closed=reaction == "closed")
        if reaction == "closed":
            sys.exit(4)
    """
)
FAKE_STATE = '{"cookies": [{"name": "s", "value": "v", "domain": "x", "path": "/"}], "origins": []}'


def scripted_capture(tmp: Path, *reactions: str) -> Callable[..., subprocess.Popen[str]]:
    """假的人工登入子程序：每次「完成登入」依序照 reactions 回應（不開瀏覽器）。

    not_yet：還沒登入、視窗開著；refused：確認網址打不開；closed：關了視窗還沒登入；
    saved：確認通過後存檔；legacy：舊版，不確認就存檔。
    """
    script = tmp / "scripted_capture.py"
    script.write_text(SCRIPTED_CAPTURE, encoding="utf-8")

    def launcher(
        command: list[str], *, env: dict[str, str], **options: object
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, str(script), *command[3:]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={**env, "FAKE_REACTIONS": json.dumps(reactions), "FAKE_STATE": FAKE_STATE},
        )

    return launcher


def login_state(client: Client, ready: Callable[[JsonObject], bool]) -> JsonObject:
    deadline = time.monotonic() + 30
    while True:
        role = body(client.get("/api/roles/erp-clerk"), 200)
        if ready(role):
            return role
        assert time.monotonic() < deadline, role
        time.sleep(0.05)


def session_of(role: JsonObject) -> JsonObject:
    return cast("JsonObject", role["session"])


def start_scripted_login(app: FastAPI, client: Client, tmp: Path, *reactions: str) -> None:
    body(client.post("/api/roles", json=ROLE), 201)
    roles = services(app).roles
    roles.display = True
    roles.local_engines = lambda: ()  # 伺服器沒有下載瀏覽器：確認一定要在開視窗的那台
    roles.launcher = scripted_capture(tmp, *reactions)
    body(client.post("/api/roles/erp-clerk/login"), 202)
    login_state(client, lambda role: session_of(role)["status"] == "waiting")


def test_manual_login_is_confirmed_where_the_window_opens(
    app: FastAPI, client: Client, tmp_path: Path
) -> None:
    """開視窗的那台確認過才存；還沒登入就按「完成登入」時說明、視窗不關，可以繼續登入。"""
    start_scripted_login(app, client, tmp_path, "not_yet", "refused", "saved")
    state = services(app).storage.role_state("erp-clerk")

    body(client.post("/api/roles/erp-clerk/login/finish"), 202)
    role = login_state(client, lambda role: bool(session_of(role)["message"]))
    assert role["activity"] == "login"
    assert session_of(role)["status"] == "waiting"
    assert "還沒登入" in str(session_of(role)["message"])
    assert "http://127.0.0.1:9/login?next=/home" in str(session_of(role)["message"])
    assert not state.exists()
    page = client.get("/roles").text
    assert "還沒登入：確認網址停在" in page
    assert 'data-action="finish-login" data-role="erp-clerk"' in page

    body(client.post("/api/roles/erp-clerk/login/finish"), 202)
    role = login_state(client, lambda role: "打不開" in str(session_of(role)["message"]))
    assert "還不能確認是否已登入" in str(session_of(role)["message"])

    body(client.post("/api/roles/erp-clerk/login/finish"), 202)
    role = login_state(client, lambda role: not role["activity"])
    assert role["status"] == "logged_in"
    assert session_of(role)["status"] == "done"
    assert state.read_text(encoding="utf-8") == FAKE_STATE
    if os.name != "nt":
        assert state.stat().st_mode & 0o777 == 0o600
    assert not (state.parent / "candidate.json").exists()


@pytest.mark.parametrize(
    ("reaction", "expected"),
    [
        ("closed", "關掉視窗時還沒登入"),
        ("legacy", "這台錄製端的版本較舊"),  # 舊版不確認，伺服器又沒有瀏覽器可以代為確認
    ],
)
def test_manual_login_that_cannot_be_confirmed_keeps_the_old_state(
    app: FastAPI, client: Client, tmp_path: Path, reaction: str, expected: str
) -> None:
    start_scripted_login(app, client, tmp_path, reaction)
    state = services(app).storage.role_state("erp-clerk")
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    body(client.post("/api/roles/erp-clerk/login/finish"), 202)
    role = login_state(client, lambda role: not role["activity"])
    assert session_of(role)["status"] == "failed"
    assert expected in str(session_of(role)["message"])
    assert state.read_text(encoding="utf-8") == '{"cookies": [], "origins": []}'
    assert not (state.parent / "candidate.json").exists()


def test_check_needs_a_browser_here_or_a_recorder(app: FastAPI, client: Client) -> None:
    """伺服器沒有下載角色用的瀏覽器、也不是透過錄製端：「檢查」變灰並說明，角色的狀態不變。"""
    body(client.post("/api/roles", json={**ROLE, "engine": "firefox"}), 201)
    services(app).roles.local_engines = lambda: ("chromium",)
    refused = client.post("/api/roles/erp-clerk/check")
    assert refused.status_code == 422
    problem = error(refused)
    assert problem["code"] == "role_check_unavailable"
    assert "伺服器沒有下載 Firefox" in str(problem["message"])
    role = body(client.get("/api/roles/erp-clerk"))
    assert (role["status"], role["activity"], role["message"]) == ("none", None, None)
    page = client.get("/roles").text
    assert 'title="伺服器沒有下載 Firefox：透過 RPA 錄製端打開管理 Portal 時在錄製端檢查' in page
    assert 'data-action="check-role" data-role="erp-clerk" disabled>' in page
    english = client.get("/roles?lang=en").text
    assert 'title="The server has not downloaded Firefox: open the Portal through' in english


def test_role_status_is_never_stale_when_a_check_ends(app: FastAPI, client: Client) -> None:
    """背景檢查剛好在讀取時結束：不能讀到舊的狀態卻同時顯示「沒有在檢查」。

    之前 CI 的 macOS 偶爾發生：先讀資料庫再看是否檢查中，中間檢查結束，就拿到舊狀態。
    這裡在讀完資料庫之後（看登入狀態檔的時間時）讓檢查結束，重現那個時間點。
    """
    body(client.post("/api/roles", json=ROLE), 201)
    roles = services(app).roles
    original = roles._state_time  # pyright: ignore[reportPrivateUsage]
    finished = False

    def state_time(role_id: str) -> datetime | None:
        nonlocal finished
        if not finished:
            finished = True
            # 背景檢查正好在這時結束：先寫入結果，再清掉「檢查中」
            with roles.sessions() as session:
                role = session.get(Role, role_id)
                assert role is not None
                role.status = "needs_login"
                session.commit()
            roles._checking.discard(role_id)  # pyright: ignore[reportPrivateUsage]
        return original(role_id)

    roles._checking.add("erp-clerk")  # pyright: ignore[reportPrivateUsage]
    roles._state_time = state_time  # pyright: ignore[reportPrivateUsage]
    first = body(client.get("/api/roles/erp-clerk"), 200)
    # 讀到舊狀態時一定還標示檢查中，呼叫端會繼續等
    assert first["activity"] == "checking" or first["status"] == "needs_login", first
    second = body(client.get("/api/roles/erp-clerk"), 200)
    assert (second["activity"], second["status"]) == (None, "needs_login")


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


def test_pasted_recording_replaces_an_existing_scene(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    created = body(
        client.post(
            "/api/recordings/import",
            json={
                "source": RECORDING,
                "target": {"sceneId": "ba-001", "mode": "replace"},
                "roleId": "testsite-user",
            },
        ),
        201,
    )
    assert (created["revision"], created["mode"]) == (2, "replace")
    revision = body(client.get("/api/scenes/ba-001/revisions/2"))
    text = cast("dict[str, str]", revision["files"])["scenario.yaml"]
    assert "id: ba-001" in text
    assert "role: testsite-user" in text
    assert "建立範例紀錄" in text  # 名稱沿用
    assert revision["note"] == f"由錄製 {created['id']} 轉換"


CONTINUED = dedent(
    """\
    def run(playwright: Playwright) -> None:
        page.get_by_role("link", name="查詢紀錄").click()
        page.locator("#lookup-id").fill("DEMO-1")
        expect(page.locator("#lookup-status")).to_contain_text("已建立")
        page.close()
    """
)


def test_pasted_recording_continues_an_existing_scene(client: Client) -> None:
    """接著既有場景：轉換結果接在最後，原有內容（包含註解）一字不動。"""
    body(client.post("/api/scenes/import"))
    before = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    created = body(
        client.post(
            "/api/recordings/import",
            json={"source": CONTINUED, "target": {"sceneId": "ba-001"}},
        ),
        201,
    )
    assert (created["revision"], created["mode"], created["baseRevision"]) == (2, "continue", 1)
    after = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/2"))["files"])
    old, new = before["scenario.yaml"], after["scenario.yaml"]
    assert all(line in new.splitlines() for line in old.splitlines())
    assert "as: lookupStatus" in new
    assert "lookupStatus:" in new.split("outputs:", 1)[1]
    assert "lookup_id:" in new.split("inputs:", 1)[1]
    assert new.index("id: evidence") < new.index("id: click-")


FAKE_RECORDER = dedent(
    """\
    import json
    import sys
    from pathlib import Path

    args = sys.argv
    output = Path(args[args.index("--output") + 1])
    inputs = json.loads(Path(args[args.index("--input") + 1]).read_text(encoding="utf-8"))
    print(json.dumps({"event": "replaying", "inputs": inputs}), flush=True)
    if "--fail" in args:
        print(json.dumps({"event": "error", "step": "submit", "message": "逾時"}), flush=True)
        sys.exit(3)
    output.write_text(Path(args[-1]).read_text(encoding="utf-8"), encoding="utf-8")
    """
)


def _fake_recorder(
    tmp_path: Path, seen: list[list[str]], fail: list[bool]
) -> "Callable[..., subprocess.Popen[str]]":
    script = tmp_path / "fake_recorder.py"
    script.write_text(FAKE_RECORDER, encoding="utf-8")
    source = tmp_path / "continued.py"
    source.write_text(CONTINUED, encoding="utf-8")

    def launcher(command: list[str], **options: object) -> subprocess.Popen[str]:
        seen.append(command)
        log = cast("Path", options["log"])
        with log.open("ab") as handle:
            return subprocess.Popen(
                [
                    sys.executable,
                    str(script),
                    *command[3:],
                    *(["--fail"] if fail[0] else []),
                    str(source),
                ],
                text=True,
                stdout=handle,
                cwd=cast("Path", options["cwd"]),
            )

    return launcher


def _wait_recording(client: Client, recording_id: object) -> JsonObject:
    record: JsonObject = {}
    for _ in range(100):
        record = body(client.get(f"/api/recordings/{recording_id}"))
        if record["status"] != "recording":
            break
        time.sleep(0.1)
    return record


def test_recording_continues_after_the_existing_steps(
    app: FastAPI, client: Client, tmp_path: Path
) -> None:
    """接著錄製：子程序先執行目前版本的步驟（入參用預設值），錄到的內容接在最後。"""
    body(client.post("/api/scenes/import"))
    recordings = services(app).recordings
    recordings.display = True
    seen: list[list[str]] = []
    fail = [False]
    recordings.launcher = _fake_recorder(tmp_path, seen, fail)

    started = body(
        client.post(
            "/api/recordings",
            json={"target": {"sceneId": "ba-001"}, "engine": "firefox"},
        ),
        202,
    )
    assert (started["mode"], started["baseRevision"]) == ("continue", 1)
    command = seen[0]
    assert command[1:3] == ["-m", "rpa_runner.record"]
    assert Path(command[command.index("--scenario") + 1]).name == "base.yaml"
    assert command[command.index("--engine") + 1] == "firefox"
    record = _wait_recording(client, started["id"])
    assert record["status"] == "done", record
    files = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/2"))["files"])
    assert "as: lookupStatus" in files["scenario.yaml"]

    # 現有步驟執行失敗：不建立新版本，說明是哪一步
    fail[0] = True
    failed = body(client.post("/api/recordings", json={"target": {"sceneId": "ba-001"}}), 202)
    record = _wait_recording(client, failed["id"])
    assert record["status"] == "failed"
    assert "submit" in str(record["error"])
    assert "逾時" in str(record["error"])
    assert body(client.get("/api/scenes/ba-001"))["latestRevision"] == 2


def test_recording_continue_needs_input_defaults(app: FastAPI, client: Client) -> None:
    body(client.post("/api/scenes/import"))
    services(app).recordings.display = True
    # BA-002 的 recordId 沒有預設值：不能先執行現有步驟
    problem = error(
        client.post(
            "/api/recordings",
            json={"target": {"sceneId": "ba-002"}, "engine": "chromium"},
        )
    )
    assert problem["code"] == "recording_continue_needs"
    assert "recordId" in str(problem["message"])
    # Python 腳本場景只能重新錄製
    script = error(client.post("/api/recordings", json={"target": {"sceneId": "ba-001-script"}}))
    assert script["code"] == "recording_script"


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


@pytest.fixture
def relative_app(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[FastAPI, Client]]:
    """資料目錄用相對路徑（像 ``rpa serve --data data-m4``）的伺服器。"""
    from fastapi.testclient import TestClient

    from rpa_server.app import create_app

    monkeypatch.chdir(tmp_path)
    relative = dataclasses.replace(
        settings, data_dir=Path("data"), database_url=sqlite_url(Path("data") / "rpa.db")
    )
    app = create_app(relative)
    with TestClient(app) as client:
        yield app, client


def test_recording_on_this_computer_with_a_fake_codegen(
    relative_app: tuple[FastAPI, Client], tmp_path: Path
) -> None:
    """codegen 換成假的：把錄製稿寫到 --output 後結束（像使用者關掉視窗）。

    資料目錄是相對路徑、codegen 在錄製資料夾裡執行：之前 --output 也是相對路徑而寫錯地方，
    錄製一開始就失敗（使用者在 Mac 上遇到）。
    """
    app, client = relative_app
    script = tmp_path / "fake_codegen.py"
    script.write_text(FAKE_CODEGEN, encoding="utf-8")
    seen: list[list[str]] = []

    def launcher(command: list[str], **options: object) -> subprocess.Popen[str]:
        seen.append(command)
        # 跟真的一樣在錄製資料夾裡執行：--output 是相對路徑時會寫錯地方
        return subprocess.Popen(
            [sys.executable, str(script), *command[3:-1], RECORDING, command[-1]],
            text=True,
            cwd=cast("Path", options["cwd"]),
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
    assert Path(command[command.index("--output") + 1]).is_absolute()

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
    # 測試的伺服器沒有畫面：「逐步調試」是灰的、不是連結，滑鼠移上去提示改用錄製端
    # （有畫面時是連結，見 test_no_display.py）
    assert 'href="/scenes/ba-001/debug"' not in scene
    assert 'class="disabled-hint" title="這台伺服器沒有畫面' in scene
    assert 'id="contract-inputs"' in scene
    assert 'id="contract-outputs"' in scene
    assert '<option value="{{ facts.record.recordId }}">' in scene  # 出參取值可以選頁面事實
    data = json.loads(scene.split('id="contract-data">')[1].split("</script>")[0])
    # 編輯器的列和場景檔的順序一樣（不是依名稱排序）
    assert [name for name, _ in data["inputs"]] == ["title", "quantity"]
    assert [name for name, _ in data["outputs"]] == ["recordId", "title", "quantity"]
    domain = client.get("/domains/lab").text
    # 卡片的五個連結都跳到場景詳情頁的區域，依序：自動化腳本、斷言腳本、入參、出參、運行報告
    links = [
        f'href="/scenes/ba-001#{part}"' for part in ("steps", "verify", "inputs", "outputs", "runs")
    ]
    positions = [domain.index(link) for link in links]
    assert positions == sorted(positions)
    assert "/edit?part=" not in domain
    assert 'href="/runs?scene=ba-001"' not in domain
    assert 'href="/recording?scene=ba-001"' in scene
    script = client.get("/scenes/ba-001-script").text
    assert 'href="/scenes/ba-001-script/debug"' not in script
    debug = client.get("/scenes/ba-001/debug").text
    assert 'id="debug-start"' in debug
    assert client.get("/recording?scene=ba-001").status_code == 200


FAKE_DEBUGGER = dedent(
    """\
    import sys

    print('{"event": "ready"}', flush=True)
    for _ in sys.stdin:
        pass
    """
)


def test_idle_debug_sessions_are_closed(app: FastAPI, client: Client, tmp_path: Path) -> None:
    """閒置太久的調試工作階段自動結束（背景執行緒定期呼叫 reap），截圖目錄一起刪除。

    調試子程序換成假的：印出 ready 後等標準輸入關閉，不開瀏覽器。
    """
    from rpa_server.processes import launch

    body(client.post("/api/scenes/import"))
    script = tmp_path / "fake_debugger.py"
    script.write_text(FAKE_DEBUGGER, encoding="utf-8")
    manager = services(app).debug

    def launcher(command: list[str], **options: object) -> subprocess.Popen[str]:
        assert command[1:3] == ["-m", "rpa_runner.debug"]
        env = cast("dict[str, str]", options["env"])
        return launch([sys.executable, str(script)], env=env, log=cast("Path", options["log"]))

    manager.launcher = launcher
    session = str(body(client.post("/api/scenes/ba-001/debug", json={}), 202)["id"])
    state: JsonObject = {}
    for _ in range(100):
        state = body(client.get(f"/api/debug/{session}"))
        if state["status"] != "starting":
            break
        time.sleep(0.1)
    assert state["status"] == "ready", state
    assert manager.reap() == 0  # 剛開始，還沒閒置

    manager.idle_seconds = 0
    time.sleep(0.01)
    assert manager.reap() == 1
    assert client.get(f"/api/debug/{session}").status_code == 404
    assert not services(app).storage.debug_dir(session).exists()
    # 同一個場景可以再開新的工作階段
    again = str(body(client.post("/api/scenes/ba-001/debug", json={}), 202)["id"])
    assert again != session
    assert body(client.delete(f"/api/debug/{again}"))["closed"] == again


# ---------------------------------------------------------------- 只編輯一段


def test_automation_and_assertion_are_edited_separately(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    original = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    verify = body(client.get("/api/scenes/ba-001/sections/verify"))
    assert str(verify["text"]).startswith("verify:")

    # 兩段腳本在場景詳情頁的「腳本」區編輯；舊的網址轉到詳情頁的區域
    page = client.get("/scenes/ba-001").text
    assert 'id="script-form"' in page
    assert "facts.record" in page  # 列出可以引用的頁面事實
    assert '<textarea class="code-editor" name="verify"' in page
    moved = client.get("/scenes/ba-001/edit?part=verify", follow_redirects=False)
    assert moved.status_code == 303
    assert moved.headers["location"] == "/scenes/ba-001#verify"
    # 完整場景檔另開視窗（外部連結），不和兩段腳本混在一起
    assert 'class="text-btn external-link" href="/scenes/ba-001/edit" target="_blank"' in page

    text = (
        str(verify["text"])
        + "\n  - name: 狀態有值\n    value: '{{ facts.record.status }}'\n    notEmpty: true"
    )
    saved = body(
        client.put(
            "/api/scenes/ba-001/sections/verify",
            json={"baseRevision": 1, "text": text, "note": None},
        ),
        201,
    )
    assert saved["number"] == 2
    after = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/2"))["files"])
    # 只有 verify 這一段改變，其他行（含註解）一字不動
    before_lines = original["scenario.yaml"].split("verify:")[0]
    assert after["scenario.yaml"].startswith(before_lines)
    assert "狀態有值" in after["scenario.yaml"]
    assert "編輯斷言腳本" in str(body(client.get("/api/scenes/ba-001/revisions/2"))["note"])

    # 校驗問題附上段落裡的行號
    broken = client.put(
        "/api/scenes/ba-001/sections/verify",
        json={
            "baseRevision": 2,
            "text": "verify:\n  - value: '{{ facts.nope }}'\n    notEmpty: true",
        },
    )
    problem = error(broken)
    issues = cast("list[JsonObject]", problem["issues"])
    assert any(issue.get("sectionLine") == 2 for issue in issues), issues
    # 只能改這一段
    other = client.put(
        "/api/scenes/ba-001/sections/verify",
        json={"baseRevision": 2, "text": "verify: []\nname: 改名"},
    )
    assert error(other)["code"] == "section_key"
    script = client.put(
        "/api/scenes/ba-001-script/sections/steps", json={"baseRevision": 1, "text": "steps: []"}
    )
    assert error(script)["code"] == "section_script"


def test_automation_and_assertion_saved_together(client: Client) -> None:
    """場景詳情頁一次存兩段：一起校驗、建立一個新版本；問題標出在哪一段的第幾行。"""
    body(client.post("/api/scenes/import"))
    steps = str(body(client.get("/api/scenes/ba-001/sections/steps"))["text"])
    verify = str(body(client.get("/api/scenes/ba-001/sections/verify"))["text"])
    # 步驟把 extract 改名、斷言跟著改：分開存的話中間的版本會校驗失敗，一起存就可以
    renamed_steps = steps.replace("as: record", "as: created")
    renamed_verify = verify.replace("facts.record", "facts.created")
    assert renamed_steps != steps
    assert renamed_verify != verify
    half = client.put(
        "/api/scenes/ba-001/sections/steps", json={"baseRevision": 1, "text": renamed_steps}
    )
    assert error(half)["code"] == "revision_invalid"
    outputs = str(body(client.get("/api/scenes/ba-001/sections/outputs"))["text"])
    saved = body(
        client.put(
            "/api/scenes/ba-001/sections",
            json={
                "baseRevision": 1,
                "sections": {
                    "steps": renamed_steps,
                    "verify": renamed_verify,
                    "outputs": outputs.replace("facts.record", "facts.created"),
                },
            },
        ),
        201,
    )
    assert saved["number"] == 2
    note = str(body(client.get("/api/scenes/ba-001/revisions/2"))["note"])
    assert note == "編輯自動化腳本、斷言腳本、出參"

    broken = client.put(
        "/api/scenes/ba-001/sections",
        json={
            "baseRevision": 2,
            "sections": {"verify": "verify:\n  - value: '{{ facts.nope }}'\n    notEmpty: true"},
        },
    )
    issues = cast("list[JsonObject]", error(broken)["issues"])
    assert any(
        issue.get("section") == "verify" and issue.get("sectionLine") == 2 for issue in issues
    ), issues
    stale = client.put(
        "/api/scenes/ba-001/sections", json={"baseRevision": 1, "sections": {"steps": steps}}
    )
    assert stale.status_code == 409
    empty = client.put("/api/scenes/ba-001/sections", json={"baseRevision": 2, "sections": {}})
    assert error(empty)["code"] == "section_none"
    script = client.put(
        "/api/scenes/ba-001-script/sections",
        json={"baseRevision": 1, "sections": {"steps": "steps: []"}},
    )
    assert error(script)["code"] == "section_script"


def test_input_table_and_yaml_views(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    # 表格 → YAML：伺服器產生和存檔相同的寫法
    rendered = body(
        client.post(
            "/api/contract/render",
            json={
                "key": "inputs",
                "items": [
                    {"name": "title", "type": "string", "default": "標題", "minLength": 1},
                    {"name": "quantity", "type": "integer", "default": 3},
                ],
            },
        )
    )
    assert rendered["text"] == (
        "inputs:\n  title:\n    type: string\n    default: 標題\n    minLength: 1\n"
        "  quantity:\n    type: integer\n    default: 3"
    )
    # YAML → 表格：先校驗（不存檔），回傳表格用的資料
    preview = body(
        client.post(
            "/api/scenes/ba-001/sections/inputs/preview",
            json={"baseRevision": 1, "text": rendered["text"]},
        )
    )
    items = cast("dict[str, JsonObject]", preview["items"])
    assert items["quantity"] == {"type": "integer", "default": 3}
    assert body(client.get("/api/scenes/ba-001"))["latestRevision"] == 1
    bad = client.post(
        "/api/scenes/ba-001/sections/inputs/preview",
        json={"baseRevision": 1, "text": "inputs:\n  title: { type: string, default: 3 }"},
    )
    assert error(bad)["code"] == "revision_invalid"

    # 只存入參：出參不動
    saved = body(
        client.put(
            "/api/scenes/ba-001/contract",
            json={
                "baseRevision": 1,
                "inputs": [
                    {"name": "title", "previous": "title", "type": "string", "default": "x"},
                    {"name": "quantity", "previous": "quantity", "type": "integer", "default": 2},
                ],
            },
        ),
        201,
    )
    files = cast(
        "dict[str, str]",
        body(client.get(f"/api/scenes/ba-001/revisions/{saved['number']}"))["files"],
    )
    assert "recordId:" in files["scenario.yaml"].split("outputs:", 1)[1]


def test_contract_yaml_saves_both_sections_atomically(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    url = "/api/scenes/ba-001/contract-yaml"
    original = body(client.get("/api/scenes/ba-001/contract-workspace"))
    yaml = cast("dict[str, str]", original["yaml"])
    before = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/1"))["files"])
    payload = {
        "baseRevision": 1,
        "inputs": yaml["inputs"].replace("default: 12", "default: 9")
        + "\n  extra: { type: string, default: example }\n",
        "outputs": yaml["outputs"].replace("facts.record.title", "inputs.extra"),
    }
    preview = client.post(url + "/preview", json=payload)
    assert preview.status_code == 200, preview.text
    assert body(client.get("/api/scenes/ba-001"))["latestRevision"] == 1
    assert body(client.put(url, json=payload), 201)["number"] == 2
    after = cast("dict[str, str]", body(client.get("/api/scenes/ba-001/revisions/2"))["files"])
    assert "default: 9" in after["scenario.yaml"]
    assert "inputs.extra" in after["scenario.yaml"]
    assert (
        after["scenario.yaml"].split("\nbrowser:")[1]
        == before["scenario.yaml"].split("\nbrowser:")[1]
    )
    assert error(client.put(url, json=payload))["code"] == "stale_base"
    bad = {
        **payload,
        "baseRevision": 2,
        "outputs": str(payload["outputs"]).replace("type: string", "type: nope"),
    }
    invalid = client.put(url, json=bad)
    assert invalid.status_code == 422
    assert "outputs" in invalid.text
    assert "sectionLine" in invalid.text
    assert body(client.get("/api/scenes/ba-001"))["latestRevision"] == 2
    assert (
        error(client.put(url, json={**payload, "baseRevision": 2, "inputs": "name: sneaky"}))[
            "code"
        ]
        == "section_key"
    )
    client.patch("/api/scenes/ba-001", json={"archived": True})
    assert error(client.put(url, json={**payload, "baseRevision": 2}))["code"] == "scene_archived"


def test_contract_sample_uses_successful_run_of_requested_revision(
    client: Client, app: FastAPI
) -> None:
    from rpa_server.models import Run

    body(client.post("/api/scenes/import"))
    svc = cast("Services", app.state.services)
    first = svc.request_run("ba-001", purpose="validation", number=1)
    with svc.sessions() as session:
        row = session.get(Run, first.id)
        assert row is not None
        row.status = "passed"
        row.output = {"recordId": "DEMO-EXAMPLE"}
        session.commit()
    second = svc.request_run("ba-001", purpose="validation", number=1)
    with svc.sessions() as session:
        row = session.get(Run, second.id)
        assert row is not None
        row.status = "failed"
        session.commit()
    preview = body(client.get("/api/scenes/ba-001/contract-workspace?revision=1"))
    assert preview["sample"] == {"runId": first.id, "values": {"recordId": "DEMO-EXAMPLE"}}
    files = svc.revision_files("ba-001", 1)
    svc.save_revision("ba-001", base=1, files=files)
    assert body(client.get("/api/scenes/ba-001/contract-workspace"))["sample"] is None
    assert (
        body(client.get("/api/scenes/ba-001/contract-workspace?revision=1"))["sample"]
        == preview["sample"]
    )
