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

    # 卡片的「調試」打開逐步調試頁；從那裡驗證最新版本，結果與截圖回到卡片上
    card.locator('[data-action="debug"]').click()
    page.wait_for_url(f"{portal}/scenes/ba-003/debug")
    page.locator('[data-action="validate"]').click()
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

    # 卡片上的「斷言腳本」只打開場景檔的 verify 段；點頁面事實插入到游標的位置
    card.locator("a", has_text="斷言腳本").click()
    page.wait_for_url(re.compile(r"/scenes/ba-003/edit\?part=verify$"))
    area = page.locator('#section-form textarea[name="text"]')
    expect(area).to_have_value(re.compile(r"^verify:"))
    area.evaluate("area => area.setSelectionRange(area.value.length, area.value.length)")
    page.locator("[data-insert]", has_text="facts.").first.click()
    assert area.input_value().rstrip().endswith("}}")
    page.locator('a.active[href$="part=verify"]').wait_for()
    page.locator('a[href$="part=steps"]').click()
    expect(area).to_have_value(re.compile(r"^steps:"))
    assert errors == []


@pytest.mark.parametrize("portal", [DEMO], indirect=True)
def test_playground_chains_published_scenarios(
    portal: str, engine: str, page: Page, site: str
) -> None:
    """M6 驗收：在自由試驗場把 BA-001、BA-002 排成序列，recordId 自動接上，真實執行通過。"""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    api = page.request
    for scene in ("ba-001", "ba-002"):
        assert api.patch(f"{portal}/api/scenes/{scene}", data={"baseUrl": site}).ok

    def validate_and_publish(scene: str, inputs: dict[str, object]) -> dict[str, object]:
        options = {"inputs": inputs, "engine": engine, "headless": True}
        queued = api.post(f"{portal}/api/scenes/{scene}/revisions/1/validate", data=options)
        assert queued.ok, queued.text()
        deadline = time.monotonic() + RUN_TIMEOUT_MS / 1000
        while True:
            run: dict[str, object] = api.get(f"{portal}/api/runs/{queued.json()['id']}").json()
            if run["finished"]:
                break
            assert time.monotonic() < deadline, "驗證沒有結束"
            time.sleep(0.5)
        assert run["status"] == "passed", run["error"]
        assert api.post(f"{portal}/api/scenes/{scene}/revisions/1/publish").ok
        return run

    created = validate_and_publish("ba-001", {})
    output = created["output"]
    assert isinstance(output, dict)
    validate_and_publish("ba-002", {"recordId": output["recordId"]})

    # 新增序列，從場景庫加入兩個場景：BA-002 的 recordId 自動接上 BA-001 的出參
    page.goto(f"{portal}/playground")
    page.locator('[data-action="create-workflow"]').click()
    dialog = page.locator("#dialog")
    dialog.locator('input[name="name"]').fill("建立後查詢")
    dialog.locator("#dialog-action").click()
    page.wait_for_url(re.compile(r"/playground/\d+$"))
    page.locator('[data-add="ba-001"]').click()
    page.locator('[data-add="ba-002"]').click()
    page.locator('[data-out="n1"]').click()
    page.locator('[data-in="n2"]').click()
    expect(page.locator("#node-inputs")).to_contain_text("recordId ← n1.recordId")
    expect(page.locator(".dag-edge")).to_have_count(1)

    # n1 的標題改成固定值
    first = page.locator('#flow-stage [data-index="0"]')
    first.click()
    page.locator('select[data-source="title"]').select_option("value")
    page.locator('input[data-value="title"]').fill("畫面串接")
    expect(page.locator("#node-inputs")).to_contain_text('title = "畫面串接"')
    expect(page.locator("#workflow-problems")).to_be_hidden()

    # 拖動、保存與重新載入；畫布適應只改視角、不改座標或標記髒資料。
    bounds = first.bounding_box()
    assert bounds is not None
    page.mouse.move(bounds["x"] + 70, bounds["y"] + 25)
    page.mouse.down()
    page.mouse.move(bounds["x"] + 110, bounds["y"] + 115, steps=8)
    page.mouse.up()
    save_button = page.locator('[data-action="workflow-save"]')
    with page.expect_response(
        lambda response: response.request.method == "PUT" and "/api/workflows/" in response.url
    ) as saved_response:
        save_button.click()
    assert saved_response.value.ok
    expect(save_button).to_be_disabled()
    workflow_id = page.locator("#workflow").get_attribute("data-workflow")
    saved = api.get(f"{portal}/api/workflows/{workflow_id}").json()
    position = saved["definition"]["nodes"][0]["position"]
    assert position["y"] > 100
    page.reload()
    expect(first).to_have_css("top", str(int(position["y"])) + "px")
    page.locator("[data-fit]").click()
    expect(save_button).to_be_disabled()
    # 反向連線形成循環時即時拒絕；移除連線會清除來源，重新連接後恢復同名匹配。
    page.locator('[data-out="n2"]').click()
    page.locator('[data-in="n1"]').click()
    expect(page.locator(".dag-edge")).to_have_count(1)
    page.locator('#flow-stage [data-node="n2"]').click()
    page.locator('[data-unlink="n1"]').click()
    expect(page.locator(".dag-edge")).to_have_count(0)
    expect(page.locator("#workflow-problems")).to_be_visible()
    page.locator('[data-out="n1"]').click()
    page.locator('[data-in="n2"]').click()
    expect(page.locator("#workflow-problems")).to_be_hidden()

    # 執行序列（先自動存檔），到序列執行頁等結果
    page.locator('[data-action="workflow-run"]').click()
    dialog.locator('select[name="engine"]').select_option(engine)
    dialog.locator('input[name="headless"][value="1"]').check()
    dialog.locator("#dialog-action").click()
    page.wait_for_url(re.compile(r"/playground/runs/"))
    page.wait_for_selector('#workflow-run:not([data-status="running"])', timeout=RUN_TIMEOUT_MS * 2)
    root = page.locator("#workflow-run")
    expect(root).to_have_attribute("data-status", "passed")
    expect(page.locator('tr[data-node="n1"]')).to_contain_text("畫面串接")
    expect(page.locator('tr[data-node="n2"]')).to_contain_text("畫面串接")
    expect(page.locator('tr[data-node="n2"] [data-status="passed"]')).to_be_visible()

    # 組合場景管理卡片與最近一次執行
    page.goto(f"{portal}/composites")
    expect(page.locator("article[data-workflow]")).to_contain_text("ba-001")
    expect(
        page.locator("tr[data-workflow-run]").first.locator('[data-status="passed"]')
    ).to_be_visible()
    page.goto(f"{portal}/playground/{workflow_id}")
    first.click()
    page.locator('input[data-value="title"]').fill("保留未儲存草稿")
    latest = api.get(f"{portal}/api/workflows/{workflow_id}").json()
    assert api.put(
        f"{portal}/api/workflows/{workflow_id}",
        data={"baseVersion": latest["version"], "name": "另一分頁"},
    ).ok
    save_button.click()
    expect(page.locator("#toast")).to_contain_text("已經在別的地方被修改")
    expect(page.locator('input[data-value="title"]')).to_have_value("保留未儲存草稿")
    expect(save_button).to_be_enabled()
    assert errors == []
