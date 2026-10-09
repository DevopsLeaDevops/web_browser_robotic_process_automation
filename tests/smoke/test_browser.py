"""瀏覽器冒煙測試：確認 Playwright 與 Chromium 在本機和 CI 都能正常啟動。

本機沒有安裝瀏覽器時略過；CI 設定 RPA_REQUIRE_BROWSER=1，缺瀏覽器直接失敗。
安裝瀏覽器：uv run playwright install chromium
"""

import os

import pytest
from playwright.sync_api import Error, sync_playwright

pytestmark = pytest.mark.browser

PAGE = "data:text/html;charset=utf-8,<title>冒煙測試</title><button>登入</button>"


def test_chromium_launches_and_finds_button_by_role() -> None:
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Error as exc:
            if os.environ.get("RPA_REQUIRE_BROWSER") == "1":
                raise
            pytest.skip(f"Chromium 未安裝：{exc.message.splitlines()[0]}")

        try:
            page = browser.new_page()
            page.goto(PAGE)
            assert page.title() == "冒煙測試"
            assert page.get_by_role("button", name="登入").is_visible()
        finally:
            browser.close()
