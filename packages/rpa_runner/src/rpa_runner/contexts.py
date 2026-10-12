"""開瀏覽器與 BrowserContext：執行、登入檢查、人工登入、調試工作階段共用。

- Firefox 從預熱設定檔的複本啟動（見 profiles.py），避免全新設定檔初始化時卡住；
  做不到就照舊用 Playwright 的全新設定檔。
- 登入狀態（storageState）：一般的 BrowserContext 直接在建立時載入；Firefox 的預熱設定檔是
  持久化 context，不能在建立時載入，改成加入 cookie，再用初始化腳本放回各網站的 localStorage。
- 關閉的動作登記在呼叫端的 ExitStack，離開時依相反順序執行。
"""

import contextlib
import json
from pathlib import Path
from typing import Any, Final, Literal, cast

from playwright.sync_api import Browser, BrowserContext, Playwright, StorageState, ViewportSize
from playwright.sync_api import Error as PlaywrightError

from rpa_runner.profiles import firefox_profile

__all__ = ["Engine", "apply_state", "launch", "open_context", "read_state"]

Engine = Literal["chromium", "firefox", "webkit"]

_RESTORE_STORAGE: Final = """
(origins) => {
  // 只在每個分頁第一次載入該網站時放回，不覆蓋執行中網站自己寫入的值
  const entry = origins.find((item) => item.origin === location.origin);
  if (!entry || sessionStorage.getItem('__rpa_state_restored')) return;
  for (const item of entry.localStorage) localStorage.setItem(item.name, item.value);
  sessionStorage.setItem('__rpa_state_restored', '1');
}
"""


def launch(playwright: Playwright, engine: Engine, *, headed: bool, timeout_ms: int) -> Browser:
    browser_type = {
        "chromium": playwright.chromium,
        "firefox": playwright.firefox,
        "webkit": playwright.webkit,
    }[engine]
    return browser_type.launch(headless=not headed, timeout=max(1, timeout_ms))


def read_state(path: Path | None) -> dict[str, object] | None:
    """讀取 storageState 檔；不存在或內容不對時回傳 None（當作還沒登入）。"""
    if path is None:
        return None
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast("dict[str, object]", data) if isinstance(data, dict) else None


def apply_state(context: BrowserContext, state: dict[str, object]) -> None:
    """把 storageState 放進已經建立的 context（持久化 context 用）。"""
    cookies = state.get("cookies")
    if isinstance(cookies, list) and cookies:
        # storageState 的 cookie 就是 add_cookies 接受的格式
        context.add_cookies(cast("list[Any]", cookies))
    origins = state.get("origins")
    if isinstance(origins, list) and origins:
        script = f"({_RESTORE_STORAGE})({json.dumps(origins, ensure_ascii=False)})"
        context.add_init_script(script=script)


def open_context(
    playwright: Playwright,
    engine: Engine,
    *,
    headed: bool,
    timeout_ms: int,
    budget_seconds: float,
    stack: contextlib.ExitStack,
    viewport: ViewportSize | None = None,
    locale: str | None = None,
    storage_state: Path | None = None,
    persistent: bool = True,
) -> BrowserContext:
    """開瀏覽器與一個 BrowserContext；``storage_state`` 是要載入的登入狀態檔（可以不存在）。

    ``persistent=False`` 時 Firefox 也不用預熱設定檔（持久化 context 在使用者關掉最後一個
    視窗時會一起關閉，人工登入要在那之後讀取登入狀態）。
    """
    state = read_state(storage_state)
    if engine == "firefox" and persistent:
        profile = stack.enter_context(firefox_profile(playwright, budget_seconds=budget_seconds))
        if profile is not None:
            context = playwright.firefox.launch_persistent_context(
                profile,
                headless=not headed,
                timeout=max(1, timeout_ms),
                viewport=viewport,
                locale=locale,
            )
            stack.callback(_close, context)
            if state is not None:
                apply_state(context, state)
            return context
    browser = launch(playwright, engine, headed=headed, timeout_ms=timeout_ms)
    stack.callback(_close, browser)
    context = browser.new_context(
        viewport=viewport,
        locale=locale,
        storage_state=cast("StorageState", state) if state is not None else None,
    )
    return context


def _close(target: Browser | BrowserContext) -> None:
    """關閉瀏覽器；使用者已經把視窗關掉（瀏覽器不在了）時不算錯誤。"""
    with contextlib.suppress(PlaywrightError):
        target.close()
