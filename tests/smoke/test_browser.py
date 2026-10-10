"""瀏覽器冒煙測試：確認 Playwright 能啟動 Chromium 與 Firefox，本機和 CI 都一樣。

本機沒有安裝瀏覽器時略過；CI 設定 RPA_REQUIRE_BROWSER=1，缺瀏覽器直接失敗。
安裝瀏覽器：uv run playwright install chromium firefox
"""

import os
from typing import Literal

import pytest
from playwright.sync_api import Error, sync_playwright

pytestmark = pytest.mark.browser

PAGE = "data:text/html;charset=utf-8,<title>冒煙測試</title><button>登入</button>"


@pytest.mark.parametrize("engine", ["chromium", "firefox"])
def test_browser_launches_and_finds_button_by_role(engine: Literal["chromium", "firefox"]) -> None:
    with sync_playwright() as pw:
        try:
            launcher = pw.chromium if engine == "chromium" else pw.firefox
            browser = launcher.launch()
        except Error as exc:
            if os.environ.get("RPA_REQUIRE_BROWSER") == "1":
                raise
            pytest.skip(f"{engine} 未安裝：{exc.message.splitlines()[0]}")

        try:
            page = browser.new_page()
            page.goto(PAGE)
            assert page.title() == "冒煙測試"
            assert page.get_by_role("button", name="登入").is_visible()
        finally:
            browser.close()
