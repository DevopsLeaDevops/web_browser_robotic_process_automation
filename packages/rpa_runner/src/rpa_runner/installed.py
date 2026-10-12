"""瀏覽器有沒有下載：找出還沒下載的瀏覽器，並把 Playwright 的英文提示換成怎麼修的說明。

Playwright 的瀏覽器要另外下載（``playwright install``），不會跟著 ``uv sync`` 安裝。
較早用一鍵安裝腳本安裝的環境只下載了 Chromium，``git pull`` 之後執行 Firefox 場景就會失敗，
錯誤是一段英文的「Executable doesn't exist」提示框。

- :func:`missing_browser_hint`：執行失敗時，從錯誤訊息或日誌認出這種情況，換成要執行的命令。
- :func:`missing_browsers`：事先檢查（``rpa serve`` 啟動時），不用真的啟動瀏覽器。
"""

import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from playwright.sync_api import sync_playwright

from rpa_runner.i18n import t

__all__ = [
    "DISPLAY_NAMES",
    "browser_names",
    "install_command",
    "missing_browser_hint",
    "missing_browsers",
]

DISPLAY_NAMES: Final = {"chromium": "Chromium", "firefox": "Firefox", "webkit": "WebKit"}
DEFAULT_ENGINES: Final = ("chromium", "firefox")
"""一鍵安裝腳本下載的瀏覽器。"""

_MISSING: Final = re.compile(r"Executable doesn't exist at (?P<path>[^\r\n]+)")
# Playwright 把每個瀏覽器放在「名稱-版本號」資料夾，例如 firefox-1543、chromium_headless_shell-1200
_FOLDER: Final = re.compile(r"^(?P<engine>chromium|firefox|webkit)\D*-\d+$")


def install_command(engines: Sequence[str]) -> str:
    """下載這些瀏覽器的命令（在專案資料夾執行，才會對應專案用的 Playwright 版本）。"""
    return "uv run playwright install " + " ".join(engines)


def browser_names(engines: Sequence[str]) -> str:
    """給人看的瀏覽器名稱，例如「Chromium、Firefox」。"""
    return t("installed.separator").join(DISPLAY_NAMES.get(engine, engine) for engine in engines)


def _engine_of(path: str) -> str | None:
    """從找不到的執行檔路徑認出是哪個瀏覽器；路徑上其他地方的字（例如使用者名稱）不算。"""
    for part in reversed(re.split(r"[\\/]", path.strip())):
        found = _FOLDER.match(part)
        if found is not None:
            return found["engine"]
    return None


def missing_browser_hint(text: str) -> str | None:
    """text（錯誤訊息或日誌）說瀏覽器還沒下載時，回傳怎麼修的說明；不是這種錯誤時回傳 None。"""
    match = _MISSING.search(text)
    if match is None:
        return None
    engine = _engine_of(match["path"])
    engines = [engine] if engine is not None else list(DEFAULT_ENGINES)
    return t(
        "installed.missing_hint", browser=browser_names(engines), command=install_command(engines)
    )


def missing_browsers(
    engines: Sequence[str] = DEFAULT_ENGINES, *, timeout: float = 15.0
) -> list[str]:
    """還沒下載的瀏覽器（依 Playwright 預期的執行檔位置判斷，不啟動瀏覽器）。

    要啟動 Playwright 的 driver（約一秒），在背景執行緒做；timeout 秒內沒有結果，
    或過程中出錯，都當作沒有缺少，不擋住呼叫的人。
    """
    found: list[str] = []
    done = threading.Event()

    def check() -> None:
        try:
            with sync_playwright() as playwright:
                for engine in engines:
                    if not Path(getattr(playwright, engine).executable_path).exists():
                        found.append(engine)
        except Exception:  # 只是提醒；判斷不了就不提醒
            found.clear()
        finally:
            done.set()

    threading.Thread(target=check, name="browser-check", daemon=True).start()
    return list(found) if done.wait(timeout) else []
