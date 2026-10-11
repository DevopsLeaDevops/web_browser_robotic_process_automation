"""頁面渲染：Jinja2 樣板（rpa_server/templates）與共用的導覽、狀態標籤。

不依賴 FastAPI：頁面路由（pages.py）只負責取資料再呼叫 :func:`render`，樣板也能單獨測試。
版面沿用設計系統 v1.0 與 MVP 原型：頂部第一級、左側第二級選單（ADR 0006、0011）。
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from rpa_core.i18n import LOCALES, NATIVE_NAMES, get_locale
from rpa_server import __version__
from rpa_server.i18n import t

__all__ = ["NAV", "TEMPLATES", "NavGroup", "NavPage", "badge_color", "render"]

TEMPLATES: Final = Path(__file__).with_name("templates")


@dataclass(frozen=True, slots=True)
class NavPage:
    id: str
    href: str
    milestone: str | None = None
    """還沒做的頁面標示在哪個里程碑提供。"""


@dataclass(frozen=True, slots=True)
class NavGroup:
    id: str
    en: str
    pages: tuple[NavPage, ...]


NAV: Final = (
    NavGroup("manage", "SCENARIOS", (NavPage("scenes", "/scenes"),)),
    NavGroup(
        "produce",
        "PRODUCTION",
        (
            NavPage("recording", "/recording", "M4"),
            NavPage("runs", "/runs"),
            NavPage("playground", "/playground", "M6"),
        ),
    ),
)
"""選單：與 MVP 原型相同的分組。"""

_BADGES: Final[Mapping[str, str]] = {
    "passed": "green",
    "published": "green",
    "failed": "red",
    "timed_out": "red",
    "cancelled": "amber",
    "draft": "amber",
    "queued": "blue",
    "running": "blue",
    "validating": "blue",
}


def badge_color(status: str) -> str:
    """狀態標籤的顏色；其他狀態（例如略過）是灰色。"""
    return _BADGES.get(status, "")


def _group_of(page: str) -> NavGroup:
    return next((group for group in NAV if any(p.id == page for p in group.pages)), NAV[0])


def _iso(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value is not None else ""


def _display_time(value: datetime | None) -> str:
    """沒有 JavaScript 時顯示的時間（UTC）；頁面載入後換成瀏覽器的當地時間。"""
    return value.strftime("%Y-%m-%d %H:%M:%S UTC") if value is not None else "—"


def _number(value: float) -> str:
    """整數值的 float 不顯示小數點（30.0 → 30）。"""
    return str(int(value)) if value.is_integer() else str(value)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _js_messages() -> dict[str, str]:
    """前端 JavaScript 用到的文字（目前語言）。"""
    keys = (
        "js.saved",
        "js.save_failed",
        "js.network_error",
        "js.confirm",
        "js.cancel",
        "js.imported",
        "js.publish_title",
        "js.publish_body",
        "js.publish_action",
        "js.published",
        "js.cancel_title",
        "js.cancel_body",
        "js.cancel_action",
        "js.cancel_requested",
        "js.stale_base",
        "js.issues",
        "js.problems",
        "js.json_invalid",
        "js.create_title",
        "js.create_action",
    )
    return {key.removeprefix("js."): t(key) for key in keys}


_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
# jinja2 的型別把 globals 限定為內建函式的型別；這裡放的是本專案的函式與資料
cast("dict[str, object]", _env.globals).update(
    t=t,
    nav=NAV,
    badge_color=badge_color,
    iso=_iso,
    display_time=_display_time,
    native_names=NATIVE_NAMES,
    locales=LOCALES,
    version=__version__,
)
_env.filters["pretty_json"] = _pretty_json
_env.filters["num"] = _number
_env.filters["compact_json"] = _compact_json


def render(name: str, *, page: str, title: str, **context: object) -> str:
    """渲染一頁：page 是選單中目前的頁面，title 是頁面標題。"""
    return _env.get_template(name).render(
        page=page,
        group=_group_of(page),
        title=title,
        locale=get_locale(),
        js_messages=_js_messages(),
        **context,
    )
