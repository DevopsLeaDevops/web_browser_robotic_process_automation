"""頁面渲染：Jinja2 樣板（rpa_server/templates）與共用的導覽、狀態標籤。

不依賴 FastAPI：頁面路由（pages.py）只負責取資料再呼叫 :func:`render`，樣板也能單獨測試。
版面沿用設計系統 v1.0 與 MVP 原型：頂部第一級、左側第二級選單（ADR 0006、0011）。
「場景管理」的二級選單是領域（資料庫裡的 domains），最後一項是「領域管理」。
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from rpa_core.i18n import LOCALES, NATIVE_NAMES, get_locale
from rpa_server import __version__
from rpa_server.domain import DomainRecord
from rpa_server.i18n import t

__all__ = [
    "NAV",
    "TEMPLATES",
    "NavGroup",
    "NavPage",
    "SideItem",
    "badge_color",
    "domain_page",
    "render",
]

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
    href: str
    """頂部選單連到哪裡。"""
    pages: tuple[NavPage, ...]


@dataclass(frozen=True, slots=True)
class SideItem:
    """左側選單的一項。"""

    id: str
    label: str
    href: str
    milestone: str | None = None


NAV: Final = (
    # 場景管理的二級選單由領域決定（_side_items）
    NavGroup("manage", "SCENARIOS", "/scenes", ()),
    NavGroup(
        "produce",
        "PRODUCTION",
        "/runs",
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
    """頁面屬於哪個第一級選單；領域頁（domain:代號）與領域管理（domains）屬於場景管理。"""
    return next((group for group in NAV if any(p.id == page for p in group.pages)), NAV[0])


def domain_page(domain_id: str | None) -> str:
    """場景相關頁面在左側選單上對應的項目：所屬領域；還沒分領域時是領域管理。"""
    return f"domain:{domain_id}" if domain_id else "domains"


def _side_items(group: NavGroup, domains: Sequence[DomainRecord]) -> list[SideItem]:
    if group.id == "manage":
        items = [SideItem(f"domain:{d.id}", d.name, f"/domains/{d.id}") for d in domains]
        return [*items, SideItem("domains", t("nav.domains"), "/domains")]
    return [SideItem(p.id, t("nav." + p.id), p.href, p.milestone) for p in group.pages]


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
        "js.save",
        "js.domain_create_title",
        "js.domain_edit_title",
        "js.domain_delete_title",
        "js.domain_delete_body",
        "js.domain_delete_action",
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


def render(
    name: str,
    *,
    page: str,
    title: str,
    domains: Sequence[DomainRecord] = (),
    **context: object,
) -> str:
    """渲染一頁：page 是選單中目前的頁面，title 是頁面標題，domains 是場景管理的二級選單。"""
    group = _group_of(page)
    return _env.get_template(name).render(
        page=page,
        group=group,
        side_items=_side_items(group, domains),
        domains=domains,
        title=title,
        locale=get_locale(),
        js_messages=_js_messages(),
        **context,
    )
