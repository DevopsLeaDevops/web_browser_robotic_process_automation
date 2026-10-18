"""RPA Worker 狀態視窗的頁面（M10.1）：把 ``ui/`` 的樣板、設計系統的 CSS、腳本與訊息組成一份 HTML。

pywebview 以 ``html=`` 載入整份內容，沒有網址可以抓外部檔案，所以 CSS 與 JS 都內嵌。
``ui/portal.css`` 是設計系統 ``docs/design-system/assets/portal.css`` 的原檔（測試確認一致；
要改先改設計系統再複製，和 Portal 的規則相同）。頁面上的文字是訊息目錄裡 ``window.`` 開頭的訊息。
"""

import html
import json
import re
from importlib.resources import files
from typing import Final

from rpa_core.i18n import DEFAULT_LOCALE, Locale
from rpa_desktop.i18n import t

__all__ = ["PAGE_PREFIX", "page_strings", "render_page"]

PAGE_PREFIX: Final = "window."
_MARKER: Final = re.compile(r"__(LANG|TITLE|PORTAL_CSS|WORKER_CSS|STRINGS|WORKER_JS)__")


def _read(name: str) -> str:
    return files("rpa_desktop").joinpath("ui", name).read_text(encoding="utf-8")


def page_strings(locale: Locale) -> dict[str, str]:
    """頁面用的訊息（缺的鍵用繁中補上；測試會確保三種語言一致）。"""
    strings = {
        key: value
        for key, value in t.messages(DEFAULT_LOCALE).items()
        if key.startswith(PAGE_PREFIX)
    }
    strings.update(
        {key: value for key, value in t.messages(locale).items() if key.startswith(PAGE_PREFIX)}
    )
    return strings


def render_page(locale: Locale) -> str:
    """產生整份頁面。"""
    strings = page_strings(locale)
    values = {
        "LANG": locale,
        "TITLE": html.escape(strings["window.title"]),
        "PORTAL_CSS": _read("portal.css"),
        "WORKER_CSS": _read("worker.css"),
        # 放在 <script type="application/json"> 裡：「</」要跳脫，免得提早結束 script
        "STRINGS": json.dumps(strings, ensure_ascii=False).replace("</", "<\\/"),
        "WORKER_JS": _read("worker.js"),
    }
    # 一次取代：插入的內容不會再被當成標記
    return _MARKER.sub(lambda match: values[match.group(1)], _read("worker.html"))
