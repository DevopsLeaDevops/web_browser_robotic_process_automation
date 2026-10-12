"""登入檢查、自動登入、needs_login、兩個角色互不干擾，以及人工登入子程序的命令流程（M4）。

在 Chromium 與 Firefox 各跑一次（Firefox 走預熱設定檔：登入狀態以 cookie 與初始化腳本放回）。
"""

import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.files import LOGIN, LOGIN_SCREENSHOT
from rpa_runner.login import ENV_LOGIN, LoginSettings
from rpa_runner.run import RunResult, execute
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
BA_004 = ROOT / "scenarios" / "demo" / "ba-004.yaml"
BA_005 = ROOT / "scenarios" / "demo" / "ba-005.yaml"


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def role(site: str, state: Path, account: str | None = None) -> LoginSettings:
    """測試網站的角色；給 account 時附上自動登入步驟（密碼用 Secret）。"""
    steps: tuple[dict[str, object], ...] = ()
    names: tuple[str, ...] = ()
    if account is not None:
        steps = (
            {"id": "open", "action": "goto", "url": f"{site}/login"},
            {"id": "user", "action": "fill", "target": {"label": "帳號"}, "value": account},
            {
                "id": "password",
                "action": "fill",
                "target": {"label": "密碼"},
                "value": "{{ secrets.DEMO_PASSWORD }}",
            },
            {"id": "submit", "action": "click", "target": {"role": "button", "name": "登入"}},
            {"id": "wait", "action": "waitFor", "url": "/account"},
        )
        names = ("DEMO_PASSWORD",)
    return LoginSettings(
        role=f"testsite-{account or 'user'}",
        state=state,
        check_url=f"{site}/account",
        check={"testId": "current-user"},
        login_url=f"{site}/login",
        steps=steps,
        secrets=names,
        name="測試帳號",
    )


def run(
    path: Path,
    site: str,
    engine: str,
    tmp: Path,
    *,
    login: LoginSettings | None = None,
    secrets: dict[str, str] | None = None,
) -> RunResult:
    return execute(
        path, {}, out_root=tmp, base_url=site, engine=engine, login=login, secrets=secrets
    )


def expire(site: str) -> None:
    request = urllib.request.Request(f"{site}/api/sessions/expire", data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def test_auto_login_then_needs_login_after_expiry(site: str, engine: str, tmp_path: Path) -> None:
    state = tmp_path / "roles" / "user.json"
    first = run(
        BA_004,
        site,
        engine,
        tmp_path,
        login=role(site, state, "user"),
        secrets={"DEMO_PASSWORD": "user-pass"},
    )

    assert first.status == "passed", first.error
    assert [stage.name for stage in first.stages][:3] == ["input", "login", "automation"]
    assert first.stage("login").message is not None  # 自動登入過
    assert first.output == {"userName": "王小明", "todoCount": 2}
    assert state.is_file()
    if os.name != "nt":
        assert state.stat().st_mode & 0o777 == 0o600
    assert first.role == "testsite-user"
    assert first.login is not None
    assert first.login["status"] == "passed"
    # 登入狀態不放進執行目錄
    assert not any(
        "cookies" in path.read_text(errors="ignore") for path in first.directory.rglob("*.json")
    )

    second = run(BA_004, site, engine, tmp_path, login=role(site, state))
    assert second.status == "passed", second.error
    assert second.stage("login").message is None  # 已登入，不必自動登入

    expire(site)
    third = run(BA_004, site, engine, tmp_path, login=role(site, state))
    assert third.status == "needs_login"
    assert third.stage("login").status == "needs_login"
    assert third.stage("automation").status == "skipped"
    assert third.output is None
    assert (third.directory / LOGIN_SCREENSHOT).is_file()
    assert (
        json.loads((third.directory / LOGIN).read_text(encoding="utf-8"))["status"] == "needs_login"
    )
    assert "testsite-user" in (third.error or "") or "測試帳號" in (third.error or "")


def test_two_roles_do_not_mix(site: str, engine: str, tmp_path: Path) -> None:
    user = tmp_path / "user.json"
    manager = tmp_path / "manager.json"
    secrets_user = {"DEMO_PASSWORD": "user-pass"}
    secrets_manager = {"DEMO_PASSWORD": "manager-pass"}

    as_user = run(
        BA_004, site, engine, tmp_path, login=role(site, user, "user"), secrets=secrets_user
    )
    as_manager = run(
        BA_005,
        site,
        engine,
        tmp_path,
        login=role(site, manager, "manager"),
        secrets=secrets_manager,
    )
    assert (as_user.status, as_manager.status) == ("passed", "passed")
    assert as_user.output == {"userName": "王小明", "todoCount": 2}
    assert as_manager.output == {"userName": "林主管", "todoCount": 4}

    # 主管的場景用一般使用者的登入狀態：獨立斷言發現看到的不是主管
    wrong = run(BA_005, site, engine, tmp_path, login=role(site, user))
    assert wrong.status == "failed"
    assert wrong.stage("verify").status == "failed"
    # 再跑一次一般使用者：狀態沒有被主管覆寫
    again = run(BA_004, site, engine, tmp_path, login=role(site, user))
    assert again.output == {"userName": "王小明", "todoCount": 2}


def test_missing_role_or_secret_fails_before_browser(site: str, tmp_path: Path) -> None:
    missing = run(BA_004, site, "chromium", tmp_path)
    assert missing.status == "failed"
    assert missing.stage("login").status == "failed"
    assert "testsite-user" in (missing.error or "")

    no_secret = run(
        BA_004, site, "chromium", tmp_path, login=role(site, tmp_path / "s.json", "user")
    )
    assert no_secret.status == "failed"
    assert "DEMO_PASSWORD" in (no_secret.error or "")


def test_state_file_without_check(site: str, engine: str, tmp_path: Path) -> None:
    state = tmp_path / "user.json"
    run(
        BA_004,
        site,
        engine,
        tmp_path,
        login=role(site, state, "user"),
        secrets={"DEMO_PASSWORD": "user-pass"},
    )

    only_state = LoginSettings(role="testsite-user", state=state)
    result = run(BA_004, site, engine, tmp_path, login=only_state)
    assert result.status == "passed", result.error
    assert result.stage("login").message is not None


def test_check_action(site: str, engine: str, tmp_path: Path) -> None:
    scenario = tmp_path / "check.yaml"
    scenario.write_text(
        "\n".join(
            [
                "schemaVersion: 1",
                "id: check-demo",
                "name: 勾選",
                "steps:",
                f"  - {{ id: open, action: goto, url: '{site}/login' }}",
                "  - { id: on, action: check, target: { label: 記住我 } }",
                "  - { id: on-again, action: check, target: { label: 記住我 } }",
                "  - { id: is-on, action: expect, target: { label: 記住我 }, state: checked }",
                "  - { id: off, action: check, target: { label: 記住我 }, checked: false }",
                "  - { id: is-off, action: expect, target: { label: 記住我 }, state: unchecked }",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = execute(scenario, {}, out_root=tmp_path / "runs", engine=engine)
    assert result.status == "passed", result.error


def capture_process(settings: LoginSettings, state: Path) -> subprocess.Popen[str]:
    env = {**os.environ, ENV_LOGIN: json.dumps(settings.to_json())}
    command = [sys.executable, "-m", "rpa_runner.login", "capture", "--state", str(state)]
    return subprocess.Popen(
        [*command, "--engine", "chromium", "--headless"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )


@pytest.mark.parametrize("command", ["finish", "cancel"])
def test_capture_commands(site: str, tmp_path: Path, command: str) -> None:
    require_engine("chromium")
    state = tmp_path / "candidate.json"
    process = capture_process(role(site, tmp_path / "unused.json"), state)
    assert process.stdin is not None
    assert process.stdout is not None
    assert json.loads(process.stdout.readline())["event"] == "ready"
    process.stdin.write(command + "\n")
    process.stdin.flush()
    event = json.loads(process.stdout.readline())["event"]
    assert process.wait(timeout=60) == (0 if command == "finish" else 2)
    if command == "finish":
        assert event == "saved"
        assert "cookies" in json.loads(state.read_text(encoding="utf-8"))
    else:
        assert event == "cancelled"
        assert not state.exists()
