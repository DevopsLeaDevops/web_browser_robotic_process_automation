"""iframe 裡的元素（M7a）：定位器的 frame、巢狀 iframe、備用定位器沿用 frame。

用測試網站的 /frames（表單在 iframe 裡，表單裡還有一個 iframe）。每個情境在 Chromium 與
Firefox 各跑一次；本機沒有某種瀏覽器時略過，CI 設定 RPA_REQUIRE_BROWSER=1 時缺瀏覽器直接失敗。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from rpa_core.dsl import Locator
from rpa_core.i18n import use_locale
from rpa_runner.browser import resolve
from rpa_runner.run import execute
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "scenarios" / "examples" / "iframe-form.yaml"


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def test_example_scenario_runs_inside_nested_iframes(
    site: str, engine: str, tmp_path: Path
) -> None:
    result = execute(EXAMPLE, {"title": "第一筆"}, out_root=tmp_path, base_url=site, engine=engine)

    assert result.status == "passed", (result.error, result.problems, result.steps)
    assert result.output == {"status": "已送出：第一筆"}


def test_fallback_without_frame_uses_the_primary_frame(
    site: str, engine: str, tmp_path: Path
) -> None:
    text = EXAMPLE.read_text(encoding="utf-8").replace(
        "target: { role: status, frame: { css: '#form-frame' } }",
        "target: { css: '#gone', frame: { css: '#form-frame' }, "
        "fallback: [{ css: '#frame-status' }] }",
    )
    scenario = tmp_path / "fallback.yaml"
    scenario.write_text(text, encoding="utf-8")

    result = execute(
        scenario, {"title": "備用"}, out_root=tmp_path / "runs", base_url=site, engine=engine
    )

    assert result.status == "passed", (result.error, result.problems, result.steps)
    assert result.output == {"status": "已送出：備用"}


def test_element_outside_the_frame_is_not_found(site: str, engine: str) -> None:
    """沒寫 frame 就只在最外層的頁面找：iframe 裡的欄位找不到，寫了 frame 才找得到。"""
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(f"{site}/frames")
            page.frame_locator("#form-frame").locator("#note-frame").wait_for()

            def count(data: dict[str, object]) -> int:
                return resolve(page, Locator.model_validate(data)).count()

            assert count({"label": "標題"}) == 0
            assert count({"label": "標題", "frame": {"css": "#form-frame"}}) == 1
            assert count({"label": "我已確認", "frame": {"css": "#form-frame"}}) == 0
            nested: dict[str, object] = {"css": "#note-frame", "frame": {"css": "#form-frame"}}
            assert count({"label": "我已確認", "frame": nested}) == 1
            # within 在 iframe 裡的頁面找
            inside: dict[str, object] = {
                "role": "button",
                "within": {"css": "form"},
                "frame": {"css": "#form-frame"},
            }
            assert count(inside) == 1
        finally:
            browser.close()
