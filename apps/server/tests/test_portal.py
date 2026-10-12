"""端到端：在瀏覽器裡操作管理 Portal。

- 「建立 → 驗證 → 發布 → 執行 → 看報告」（M3 驗收）
- 「測試網站自動化」領域：範例卡片、從卡片調試、結果與截圖回到卡片上

Portal 用 uvicorn 在背景執行緒啟動（含背景 worker）；操作 Portal 的瀏覽器是 Chromium，
場景本身在 Chromium 與 Firefox 各跑一次。
"""

import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import click
import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from rpa_cli.serve import open_listener
from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"
BA_001 = (DEMO / "ba-001.yaml").read_text(encoding="utf-8")
RUN_TIMEOUT_MS = 120_000


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture(params=[None])
def portal(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[str]:
    """啟動 Portal；以 indirect 參數傳入範例資料夾時，會建立「測試網站自動化」並匯入範例。"""
    data = tmp_path / "data"
    examples: Path | None = request.param
    settings = Settings(
        data_dir=data, database_url=sqlite_url(data / "rpa.db"), examples_dir=examples
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
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


@pytest.fixture
def page() -> Iterator[Page]:
    require_engine("chromium")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-TW")
        context.set_default_timeout(15_000)
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()


def test_rpa_serve_recognizes_a_running_portal(portal: str) -> None:
    """rpa serve 遇到已經在執行的 Portal 時，直接告訴使用者網址，不再開第二個。"""
    port = int(portal.rsplit(":", 1)[1])
    with pytest.raises(click.ClickException) as raised:
        open_listener("127.0.0.1", port)
    assert f"http://127.0.0.1:{port}/" in raised.value.message


def wait_for_run(page: Page, status: str = "passed") -> str:
    """在執行頁面等到結束（頁面會自動重新整理），回傳執行編號。"""
    page.wait_for_url("**/runs/*")
    root = page.locator("#run")
    page.wait_for_selector(
        '#run[data-status="passed"], #run[data-status="failed"], '
        '#run[data-status="timed_out"], #run[data-status="cancelled"]',
        timeout=RUN_TIMEOUT_MS,
    )
    actual = root.get_attribute("data-status")
    error = page.locator(".notice.danger")
    assert actual == status, error.all_inner_texts()
    run_id = root.get_attribute("data-run")
    assert run_id
    return run_id


def start_run(page: Page, inputs: dict[str, object], engine: str, site: str) -> None:
    form = page.locator("#run-form")
    form.locator('textarea[name="inputs"]').fill(json.dumps(inputs, ensure_ascii=False))
    form.locator('select[name="engine"]').select_option(engine)
    form.locator('input[name="baseUrl"]').fill(site)
    # 測試一律用無頭模式（CI 沒有圖形介面；有的話也不要在畫面上開視窗）
    form.locator('input[name="headless"][value="1"]').check()
    form.locator('[data-action="submit-run"]').click()


def test_create_validate_publish_run_report(
    portal: str, page: Page, site: str, engine: str
) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    # 建立
    page.goto(f"{portal}/scenes")
    page.locator('[data-action="new-scene"]').click()
    dialog = page.locator("#dialog")
    dialog.locator('input[name="id"]').fill("e2e-demo")
    dialog.locator('input[name="name"]').fill("端到端")
    dialog.locator('input[name="category"]').fill("驗收")
    dialog.locator("#dialog-action").click()
    page.wait_for_url(f"{portal}/scenes/e2e-demo/edit")

    # 編輯：先存一份有錯的內容，看到錯誤位置；再存正確的內容
    editor = page.locator('textarea[name="scenario.yaml"]')
    content = BA_001.replace("id: ba-001", "id: e2e-demo")
    editor.fill(content.replace("action: click", "action: tap"))
    page.locator('[data-action="save-revision"]').click()
    expect(page.locator("#issue-list")).to_contain_text("tap")
    editor.fill(content)
    page.locator('input[name="note"]').fill("改成 BA-001 的步驟")
    page.locator('[data-action="save-revision"]').click()
    page.wait_for_url(f"{portal}/scenes/e2e-demo")
    expect(page.locator('tr[data-revision="2"]')).to_contain_text("改成 BA-001 的步驟")

    # 驗證
    page.locator('#page-actions a[href$="purpose=validation"]').click()
    start_run(page, {"title": "端到端驗證", "quantity": 6}, engine, site)
    wait_for_run(page)

    # 發布
    page.locator('[data-action="publish"]').click()
    page.locator("#dialog-action").click()
    page.wait_for_url(f"{portal}/scenes/e2e-demo")
    expect(page.locator('tr[data-revision="2"] [data-status="published"]')).to_be_visible()

    # 執行
    page.locator('#page-actions a[href$="purpose=execution"]').click()
    start_run(page, {"title": "端到端執行", "quantity": 7}, engine, site)
    run_id = wait_for_run(page)
    expect(page.locator("pre.source").nth(1)).to_contain_text("端到端執行")

    # 看報告：依場景篩選，打開 HTML 報告
    page.goto(f"{portal}/runs")
    scene_menu = page.locator("details.filter-menu", has=page.locator('input[name="scene"]'))
    scene_menu.locator("summary").click()
    scene_menu.locator('input[name="scene"][value="e2e-demo"]').check()
    with page.expect_navigation():
        scene_menu.get_by_role("button", name="套用").click()
    expect(page.locator("tr[data-run]")).to_have_count(2)
    expect(scene_menu.locator("summary")).to_contain_text("e2e-demo")
    # 關閉選單也會套用：再勾「通過」，點選單外面
    status_menu = page.locator("details.filter-menu", has=page.locator('input[name="status"]'))
    status_menu.locator("summary").click()
    status_menu.locator('input[name="status"][value="passed"]').check()
    with page.expect_navigation():
        page.locator("h1").click()
    assert "status=passed" in page.url
    expect(status_menu.locator("summary")).to_contain_text("通過")
    with page.context.expect_page() as opened:
        page.locator(f'tr[data-run="{run_id}"] a[href$="report.html"]').click()
    report = opened.value
    report.wait_for_load_state()
    assert "端到端執行" in report.content()
    assert errors == []


@pytest.mark.parametrize("portal", [DEMO], indirect=True)
def test_testsite_domain_runs_a_real_case_from_its_card(
    portal: str, page: Page, site: str, engine: str
) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    page.goto(f"{portal}/scenes")
    page.wait_for_url(f"{portal}/domains/testsite")
    expect(page.locator("#sidenav a.active")).to_contain_text("測試網站自動化")
    cards = page.locator("article.scene-card")
    expect(cards).to_have_count(6)
    card = page.locator('article.scene-card[data-scene="ba-003"]')
    expect(card).to_contain_text("查詢不存在的紀錄")
    expect(card.locator('[data-status="none"]')).to_be_visible()

    # 從卡片調試（驗證最新版本），結果與截圖回到卡片上
    card.locator('[data-action="debug"]').click()
    start_run(page, {"recordId": "DEMO-NOTFOUND"}, engine, site)
    wait_for_run(page)
    expect(page.locator("pre.source").nth(1)).to_contain_text("查無紀錄")

    page.goto(f"{portal}/domains/testsite")
    card = page.locator('article.scene-card[data-scene="ba-003"]')
    expect(card.locator('[data-status="passed"]')).to_be_visible()
    expect(card.locator("img")).to_have_attribute("src", re.compile(r"/files/screenshot\.png$"))
    # 截圖是延遲載入：捲到卡片，等圖片解碼完再看尺寸（壞圖時 decode 會失敗）
    card.scroll_into_view_if_needed()
    width = card.locator("img").evaluate("image => image.decode().then(() => image.naturalWidth)")
    assert width > 0

    # 卡片上的「斷言腳本」打開編輯頁並跳到 verify
    card.locator("a", has_text="斷言腳本").click()
    page.wait_for_url(re.compile(r"/scenes/ba-003/edit\?focus=verify$"))
    selected = page.locator('textarea[name="scenario.yaml"]').evaluate(
        "area => area.value.slice(area.selectionStart, area.selectionEnd)"
    )
    assert selected == "verify"
    assert errors == []
