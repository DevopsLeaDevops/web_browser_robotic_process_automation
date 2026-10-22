"""桌面 App 自己的頁面：把 ``ui/`` 的樣板、設計系統的 CSS、腳本與訊息組成一份 HTML。

- ``worker``：RPA Worker 的狀態視窗（M10.1）。pywebview 以 ``html=`` 載入整份內容，沒有網址
  可以抓外部檔案，所以 CSS 與 JS 都內嵌；文字是訊息目錄裡 ``window.`` 開頭的訊息。
- ``recorder``：RPA 錄製端的狀態、配對與設定（M10.2），由本機閘道的 ``/__desktop/`` 提供
  （:mod:`rpa_desktop.recorder_pages`）；文字是 ``recorder.`` 開頭的訊息。

``ui/portal.css`` 是設計系統 ``docs/design-system/assets/portal.css`` 的原檔（測試確認一致；
要改先改設計系統再複製，和 Portal 的規則相同）。
"""

import html
import json
import re
import sys
from importlib.resources import files
from typing import Final, Literal

from rpa_core.i18n import DEFAULT_LOCALE, Locale
from rpa_desktop.i18n import PLATFORM_VARIANT, t

__all__ = ["PAGES", "PAGE_PREFIX", "Page", "page_strings", "read_asset", "render_page"]

Page = Literal["worker", "recorder"]
PAGE_PREFIX: Final = "window."
PAGES: Final[dict[Page, str]] = {"worker": PAGE_PREFIX, "recorder": "recorder."}
"""頁面 → 它的訊息前綴（樣板是 ``ui/<頁面>.html``、腳本是 ``ui/<頁面>.js``）。"""
_MARKER: Final = re.compile(r"__(LANG|TITLE|PORTAL_CSS|WORKER_CSS|STRINGS|WORKER_JS)__")


def read_asset(name: str) -> str:
    """``ui/`` 裡的一個檔案。"""
    return files("rpa_desktop").joinpath("ui", name).read_text(encoding="utf-8")


def page_strings(
    locale: Locale, prefix: str = PAGE_PREFIX, platform: str = sys.platform
) -> dict[str, str]:
    """頁面用的訊息（缺的鍵用繁中補上；測試會確保三種語言一致）。

    macOS 上 ``<前綴>darwin.<名稱>`` 蓋過 ``<前綴><名稱>``（選單列、鑰匙圈、登入 macOS），
    頁面的腳本不必知道是哪個系統。
    """
    strings = {
        key: value for key, value in t.messages(DEFAULT_LOCALE).items() if key.startswith(prefix)
    }
    strings.update(
        {key: value for key, value in t.messages(locale).items() if key.startswith(prefix)}
    )
    if platform == PLATFORM_VARIANT:
        variant = f"{prefix}{PLATFORM_VARIANT}."
        strings.update(
            {
                prefix + key.removeprefix(variant): value
                for key, value in strings.items()
                if key.startswith(variant)
            }
        )
    return strings


def render_page(locale: Locale, page: Page = "worker") -> str:
    """產生整份頁面。"""
    prefix = PAGES[page]
    strings = page_strings(locale, prefix)
    values = {
        "LANG": locale,
        "TITLE": html.escape(strings[prefix + "title"]),
        "PORTAL_CSS": read_asset("portal.css"),
        "WORKER_CSS": read_asset("worker.css"),
        # 放在 <script type="application/json"> 裡：「</」要跳脫，免得提早結束 script
        "STRINGS": json.dumps(strings, ensure_ascii=False).replace("</", "<\\/"),
        "WORKER_JS": read_asset(f"{page}.js"),
    }
    # 一次取代：插入的內容不會再被當成標記
    return _MARKER.sub(lambda match: values[match.group(1)], read_asset(f"{page}.html"))
