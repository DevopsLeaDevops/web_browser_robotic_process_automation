"""測試用：確認瀏覽器能不能啟動。

本機缺某種瀏覽器時略過該測試；設定 ``RPA_REQUIRE_BROWSER=1``（CI 與一鍵安裝腳本）時直接失敗，
避免瀏覽器沒裝好卻顯示全部通過。
"""

import os
from functools import cache
from typing import Final

import pytest
from playwright.sync_api import Error, sync_playwright

__all__ = ["ENGINES", "launch_problem", "require_engine"]

ENGINES: Final = ("chromium", "firefox")


@cache
def launch_problem(engine: str) -> str | None:
    """啟動一次瀏覽器；不能啟動時回傳錯誤訊息的第一行。"""
    with sync_playwright() as playwright:
        try:
            getattr(playwright, engine).launch().close()
        except Error as error:
            return error.message.splitlines()[0]
    return None


def require_engine(engine: str) -> str:
    """瀏覽器不能啟動時略過目前的測試（RPA_REQUIRE_BROWSER=1 時改為失敗）。"""
    problem = launch_problem(engine)
    if problem is not None:
        if os.environ.get("RPA_REQUIRE_BROWSER") == "1":
            pytest.fail(f"{engine} 無法啟動：{problem}")
        pytest.skip(f"{engine} 未安裝：{problem}")
    return engine
