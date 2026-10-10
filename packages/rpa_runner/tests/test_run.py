"""真實瀏覽器執行：MVP 原型 test_demo.py 的五個回歸情境，加上 Python 腳本場景與 rpa run。

每個情境在 Chromium 與 Firefox 各跑一次。本機沒有某種瀏覽器時略過；
CI 設定 RPA_REQUIRE_BROWSER=1，缺瀏覽器直接失敗。
"""

import os
import threading
import time
from collections.abc import Iterator
from functools import cache
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner
from playwright.sync_api import Error, sync_playwright

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_core.i18n import use_locale
from rpa_runner.files import FACTS, OUTPUT, REPORT, RESULT, SCREENSHOT
from rpa_runner.run import RunResult, execute
from testsite.server import create_server

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"
BA_002 = ROOT / "scenarios" / "demo" / "ba-002.yaml"
BA_001_SCRIPT = ROOT / "scenarios" / "demo" / "ba-001-script" / "scenario.yaml"


@cache
def _launch_problem(engine: str) -> str | None:
    with sync_playwright() as playwright:
        try:
            getattr(playwright, engine).launch().close()
        except Error as error:
            return error.message.splitlines()[0]
    return None


@pytest.fixture(params=["chromium", "firefox"])
def engine(request: pytest.FixtureRequest) -> str:
    name = str(request.param)
    problem = _launch_problem(name)
    if problem is not None:
        if os.environ.get("RPA_REQUIRE_BROWSER") == "1":
            pytest.fail(f"{name} 無法啟動：{problem}")
        pytest.skip(f"{name} 未安裝：{problem}")
    return name


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    server: ThreadingHTTPServer = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def run(
    path: Path, inputs: dict[str, object], site: str, engine: str, tmp: Path, **kw: int
) -> RunResult:
    return execute(
        path, inputs, out_root=tmp, base_url=site, engine=engine, deadline_ms=kw.get("deadline_ms")
    )


def test_chain_ba001_to_ba002(site: str, engine: str, tmp_path: Path) -> None:
    first = run(BA_001, {"title": "繁體中文鏈路驗證", "quantity": 23}, site, engine, tmp_path)

    assert first.status == "passed", first.error
    assert first.output is not None
    assert first.output["title"] == "繁體中文鏈路驗證"
    assert first.output["quantity"] == 23
    for name in (FACTS, OUTPUT, SCREENSHOT, RESULT, REPORT, "evidence.png"):
        assert (first.directory / name).is_file(), name
    assert all(check.passed for check in first.checks)
    assert [step["status"] for step in first.steps] == ["passed"] * 7

    second = run(BA_002, {"recordId": first.output["recordId"]}, site, engine, tmp_path)

    assert second.status == "passed", second.error
    assert second.output == first.output


def test_invalid_input_never_starts_browser(site: str, engine: str, tmp_path: Path) -> None:
    result = run(BA_001, {"quantity": 100}, site, engine, tmp_path)

    assert result.status == "failed"
    assert result.stage("input").status == "failed"
    assert result.stage("automation").status == "skipped"
    assert "入參 quantity 不符合限制：maximum: 30" in result.problems
    assert not (result.directory / "automation.log").exists()
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / REPORT).is_file()


def test_failed_assertion_never_publishes_output(site: str, engine: str, tmp_path: Path) -> None:
    scenario = tmp_path / "ba-001-wrong.yaml"
    scenario.write_text(
        BA_001.read_text(encoding="utf-8").replace("equals: 已建立", "equals: 已核准"),
        encoding="utf-8",
    )
    result = run(scenario, {"title": "斷言失敗", "quantity": 12}, site, engine, tmp_path / "runs")

    assert result.status == "failed"
    assert result.stage("automation").status == "passed"
    assert result.stage("verify").status == "failed"
    assert [check.passed for check in result.checks] == [True, False, True, True]
    assert result.output is None
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / SCREENSHOT).is_file()


def test_deadline_stops_run_and_never_publishes_output(
    site: str, engine: str, tmp_path: Path
) -> None:
    started = time.monotonic()
    result = run(BA_001, {"title": "逾時", "quantity": 10}, site, engine, tmp_path, deadline_ms=1)

    assert result.status == "timed_out"
    assert time.monotonic() - started < 20
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / REPORT).is_file()


def test_unknown_record_fails_with_evidence(site: str, engine: str, tmp_path: Path) -> None:
    # 查無紀錄時頁面不會出現詳情，等待會耗盡期限。慢的機器（例如 Windows 的 Firefox）
    # 可能還在啟動瀏覽器就逾時，所以只要求「沒有出參、有報告、失敗的步驟只能是等待詳情」。
    result = run(BA_002, {"recordId": "DEMO-MISSING"}, site, engine, tmp_path, deadline_ms=8000)

    assert result.status in ("failed", "timed_out")
    assert result.output is None
    assert result.error
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / REPORT).is_file()
    failed = {step["id"] for step in result.steps if step["status"] == "failed"}
    assert failed <= {"wait-receipt"}


def test_python_script_scenario(site: str, engine: str, tmp_path: Path) -> None:
    result = run(BA_001_SCRIPT, {"title": "腳本場景", "quantity": 5}, site, engine, tmp_path)

    assert result.status == "passed", result.error
    assert result.kind == "script"
    assert result.output is not None
    assert result.output["quantity"] == 5
    assert (result.directory / "scenario" / "automation.py").is_file()


def test_cli_run(site: str, engine: str, tmp_path: Path) -> None:
    args = [
        "run",
        str(BA_001),
        "-i",
        "title=命令列",
        "-i",
        "quantity=3",
        "--base-url",
        site,
        "--browser",
        engine,
        "--out",
        str(tmp_path),
    ]
    with use_locale("zh-Hant"):
        install_click_translations()
        result = CliRunner().invoke(build_cli(), args)

    assert result.exit_code == 0, result.output
    assert "ba-001 建立範例紀錄：通過" in result.output
    assert "report.html" in result.output
