"""新分頁（M7b）：步驟的 popup 開出新分頁、page 在那個分頁執行；失敗在新分頁上時的紀錄。

用測試網站的 /popup（連結在新分頁打開商品明細）。每個情境在 Chromium 與 Firefox 各跑一次；
本機沒有某種瀏覽器時略過，CI 設定 RPA_REQUIRE_BROWSER=1 時缺瀏覽器直接失敗。
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.files import DIAGNOSTIC, SCREENSHOT
from rpa_runner.run import execute
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "scenarios" / "examples" / "popup-form.yaml"


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


@pytest.mark.parametrize(
    ("item", "expected"), [("455590002", "455590002"), ("SKU-{{random:7:7}}", "SKU-7")]
)
def test_example_scenario_runs_across_tabs(
    site: str, engine: str, tmp_path: Path, item: str, expected: str
) -> None:
    result = execute(EXAMPLE, {"item": item}, out_root=tmp_path, base_url=site, engine=engine)

    assert result.status == "passed", (result.error, result.problems, result.steps)
    assert result.output == {"status": f"已儲存：{expected}"}
    urls = [step.get("url") for step in result.steps]
    # 開出新分頁的那一步之後到儲存，都在新分頁；最後一步回到一開始的分頁
    assert str(urls[1]).endswith("/popup/items")
    assert str(urls[4]).endswith("/popup/items")
    assert str(urls[6]).endswith("/popup")


def test_failure_on_a_tab_is_recorded_on_that_tab(site: str, engine: str, tmp_path: Path) -> None:
    text = EXAMPLE.read_text(encoding="utf-8").replace(
        "target: { role: button, name: 儲存 }",
        "target: { role: button, name: 不存在 }\n    timeout: 1500",
    )
    scenario = tmp_path / "broken.yaml"
    scenario.write_text(text, encoding="utf-8")

    result = execute(scenario, {}, out_root=tmp_path / "runs", base_url=site, engine=engine)

    assert result.status == "failed"
    failed = [step for step in result.steps if step.get("status") == "failed"]
    assert [step.get("id") for step in failed] == ["save"]
    diagnostic = json.loads((result.directory / DIAGNOSTIC).read_text(encoding="utf-8"))
    assert str(diagnostic["url"]).endswith("/popup/items")
    assert (result.directory / SCREENSHOT).is_file()


def test_popup_that_never_opens_fails_the_step(site: str, engine: str, tmp_path: Path) -> None:
    """寫了 popup 但點擊沒有開出新分頁：這一步逾時失敗，不會在原來的分頁繼續。"""
    text = EXAMPLE.read_text(encoding="utf-8").replace(
        "    target: { role: link, name: 開啟商品明細 }\n    popup: items",
        "    target: { role: heading, name: 訂單 SO-1001 }\n    popup: items\n    timeout: 1500",
    )
    scenario = tmp_path / "no-popup.yaml"
    scenario.write_text(text, encoding="utf-8")

    result = execute(scenario, {}, out_root=tmp_path / "runs", base_url=site, engine=engine)

    assert result.status == "failed"
    failed = [step for step in result.steps if step.get("status") == "failed"]
    assert [step.get("id") for step in failed] == ["open-items"]
