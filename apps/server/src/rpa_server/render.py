"""頁面渲染：Jinja2 樣板（rpa_server/templates）與共用的導覽、狀態標籤。

不依賴 FastAPI：頁面路由（pages.py）只負責取資料再呼叫 :func:`render`，樣板也能單獨測試。
版面沿用設計系統 v1.1 與 MVP 原型：頂部第一級、左側第二級選單（ADR 0006、0011）。
「場景管理」的二級選單是領域（資料庫裡的 domains，依領域管理的順序），接著是「組合場景自動化」，
最後是「登入與憑證」。第一級選單依三段分工：伺服器本機全部顯示；透過錄製端時，叢集管理與管理後台
只在裝置頁替那台打開時才顯示（RECORDER_MENUS）；Worker App 不載入這些頁面。
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from rpa_core.i18n import LOCALES, NATIVE_NAMES, get_locale
from rpa_core.workflow import Workflow
from rpa_server import __version__
from rpa_server.config import COMPOSITES_DOMAIN, RECORDER_MENUS
from rpa_server.context import via_recorder
from rpa_server.domain import PURPOSES, RUN_STATUSES, DomainRecord, SceneRecord
from rpa_server.i18n import page_t, t

__all__ = [
    "NAV",
    "TEMPLATES",
    "FilterMenu",
    "NavGroup",
    "NavPage",
    "SideItem",
    "badge_color",
    "domain_page",
    "js_messages",
    "menu_shown",
    "render",
    "replay_messages",
    "run_filters",
    "visible_nav",
    "workflow_messages",
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
class FilterMenu:
    """執行報告的一個篩選條件：按鈕顯示目前的選擇，點開是可以勾選多項的清單。"""

    name: str
    """查詢參數的名稱，例如 scene。"""
    label: str
    options: tuple[tuple[str, str], ...]
    """（值, 顯示文字）。"""
    selected: tuple[str, ...] = ()
    searchable: bool = False
    """選項很多時在清單上方加搜尋框。"""

    @property
    def picked(self) -> list[str]:
        """已勾選項目的顯示文字，依選項順序；沒勾選代表全部。"""
        return [text for value, text in self.options if value in self.selected]


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
        "/recording",
        (NavPage("recording", "/recording"), NavPage("playground", "/playground")),
    ),
    NavGroup(
        "operate",
        "OPERATIONS",
        "/runs",
        (NavPage("runs", "/runs"), NavPage("replay", "/replay")),
    ),
    NavGroup("cluster", "CLUSTER", "/devices", (NavPage("workers", "/devices"),)),
    NavGroup("admin", "ADMIN", "/domains", (NavPage("domains", "/domains"),)),
)
"""第一級選單（2026-10-22 使用者調整）：場景管理、場景生產、場景運行、叢集管理、管理後台。"""

_BADGES: Final[Mapping[str, str]] = {
    "passed": "green",
    "published": "green",
    "logged_in": "green",
    "done": "green",
    "reused": "green",
    "needs_login": "amber",
    "online": "green",
    "busy": "blue",
    "disabled": "amber",
    "recording": "blue",
    "checking": "blue",
    "login": "blue",
    "starting": "blue",
    "unknown": "red",
    "failed": "red",
    "timed_out": "red",
    "cancelled": "amber",
    "draft": "amber",
    "queued": "blue",
    "running": "blue",
    "validating": "blue",
    # 領域的同步狀態（M11 PR 3）
    "synced": "green",
    "ahead": "blue",
    "behind": "blue",
    "diverged": "amber",
    "empty": "amber",
    "no_directory": "amber",
    "conflict": "red",
    "error": "red",
}


def run_filters(
    *,
    scenes: Sequence[SceneRecord],
    categories: Sequence[str],
    selected: Mapping[str, Sequence[str]],
    locations: Sequence[tuple[str, str]] = (),
) -> list[FilterMenu]:
    """執行報告的篩選條件：分類、場景、結果、目的；每一項都可以複選，沒選代表全部。

    有遠端 worker 時多一個「執行位置」：本機與各台 worker（``locations`` 是（代號, 名稱））。
    """

    def chosen(name: str) -> tuple[str, ...]:
        return tuple(selected.get(name, ()))

    menus = [
        FilterMenu(
            "category",
            t("runs.filter_category"),
            tuple((item, item) for item in categories),
            chosen("category"),
        ),
        FilterMenu(
            "scene",
            t("runs.filter_scene"),
            tuple((scene.id, f"{scene.id} · {scene.name}") for scene in scenes),
            chosen("scene"),
            searchable=len(scenes) > 8,
        ),
        FilterMenu(
            "status",
            t("runs.filter_status"),
            tuple((status, t(f"status.{status}")) for status in RUN_STATUSES),
            chosen("status"),
        ),
        FilterMenu(
            "purpose",
            t("runs.filter_purpose"),
            tuple((purpose, t(f"purpose.{purpose}")) for purpose in PURPOSES),
            chosen("purpose"),
        ),
    ]
    if locations:
        menus.append(
            FilterMenu(
                "worker",
                t("runs.filter_worker"),
                tuple(locations),
                chosen("worker"),
                searchable=len(locations) > 8,
            )
        )
    return menus


def badge_color(status: str) -> str:
    """狀態標籤的顏色；其他狀態（例如略過）是灰色。"""
    return _BADGES.get(status, "")


def _group_of(page: str) -> NavGroup:
    """頁面屬於哪個第一級選單；領域頁（domain:代號）、場景頁、組合場景與登入與憑證屬於場景管理。"""
    return next((group for group in NAV if any(p.id == page for p in group.pages)), NAV[0])


def visible_nav() -> tuple[NavGroup, ...]:
    """目前的請求看得到的第一級選單（三段分工）。

    伺服器本機全部顯示；透過錄製端時，RECORDER_MENUS（叢集管理、管理後台）只顯示裝置頁替那台
    打開的。只是不顯示：錄製端的權杖照樣能打開這些網址（M8 才有使用者權限）。
    """
    via = via_recorder()
    if via is None:
        return NAV
    return tuple(group for group in NAV if group.id not in RECORDER_MENUS or group.id in via.menus)


def menu_shown(group_id: str) -> bool:
    """這個第一級選單目前看得到嗎；看不到時，頁面上通往它的按鈕也不顯示。"""
    return any(group.id == group_id for group in visible_nav())


def domain_page(domain_id: str | None) -> str:
    """場景相關頁面在左側選單上對應的項目：所屬領域；還沒分領域時停在場景管理、不標示任何一項。"""
    return f"domain:{domain_id}" if domain_id else "scenes"


def _side_items(group: NavGroup, domains: Sequence[DomainRecord]) -> list[SideItem]:
    if group.id == "manage":
        items = [
            SideItem(f"domain:{d.id}", d.name, f"/domains/{d.id}")
            for d in domains
            if d.id != COMPOSITES_DOMAIN  # 組合場景在「組合場景自動化」管理
        ]
        return [
            *items,
            SideItem("composites", t("nav.composites"), "/composites"),
            SideItem("roles", t("nav.roles"), "/roles"),
        ]
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


def js_messages() -> dict[str, str]:
    """前端 JavaScript 用到的文字（目前語言）。"""
    keys = (
        "js.saved",
        "js.save_failed",
        "js.network_error",
        "js.confirm",
        "js.cancel",
        "js.imported",
        "js.list_separator",
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
        "js.role_create_title",
        "js.role_edit_title",
        "js.role_delete_title",
        "js.role_delete_body",
        "js.role_delete_action",
        "js.role_clear_title",
        "js.role_clear_body",
        "js.role_clear_action",
        "js.secret_create_title",
        "js.secret_edit_title",
        "js.secret_delete_title",
        "js.secret_delete_body",
        "js.secret_delete_action",
        "js.recording_started",
        "js.converted",
        "js.debug_confirm_title",
        "js.debug_confirm_action",
        "js.debug_close_title",
        "js.debug_close_body",
        "js.debug_close_action",
        "js.working",
        "js.contract_saved",
        "js.contract_unsaved",
        "js.contract_preview_draft",
        "js.contract_preview_invalid",
        "js.contract_required",
        "js.contract_script_output",
        "js.contract_sample_source",
        "js.contract_sample_empty",
        "js.contract_sample_draft",
        "js.contract_saved_next",
        "js.validate_next",
        "js.editor_revision",
        "js.run_published",
        "js.rerun_started",
        "js.section_line",
        "js.worker_create_title",
        "js.worker_create_action",
        "js.worker_invite_title",
        "js.worker_invite_again_title",
        "js.worker_invite_again_body",
        "js.worker_invite_again_action",
        "js.worker_copied",
        "js.worker_delete_title",
        "js.worker_delete_body",
        "js.worker_delete_action",
        "js.worker_disabled",
        "js.worker_enabled",
        "js.sync_pulled",
        "js.sync_pushed",
        "js.sync_push_title",
        "js.sync_push_action",
        "js.sync_changes",
        "js.sync_added",
        "js.sync_modified",
        "js.sync_deleted",
        "js.sync_key_ready",
        "js.sync_disconnect_title",
        "js.sync_disconnect_body",
        "js.sync_disconnect_action",
        "js.sync_resolve_branch_title",
        "js.sync_resolve_branch_body",
        "js.sync_resolve_remote_title",
        "js.sync_resolve_remote_body",
        "js.sync_resolve_action",
        "js.sync_branch_pushed",
        "js.domain_git_title",
        "js.domain_git_action",
        "js.server_rename_title",
        "js.server_name",
        "js.composite_validate_title",
        "js.composite_validate_body",
        "js.composite_validate_action",
    )
    return {key.removeprefix("js."): page_t(key) for key in keys}  # 透過錄製端時換掉用詞


def workflow_preview(workflow: Workflow) -> dict[str, object]:
    """以實際座標與依賴產生卡片縮圖；只計算呈現，不修改或執行定義。"""
    positions = {
        node.id: (node.position.x, node.position.y)
        if node.position
        else (40.0 + (index % 3) * 280, 40.0 + (index // 3) * 160)
        for index, node in enumerate(workflow.nodes)
    }
    nodes = [
        {
            "id": node.id,
            "scene": node.scene_id,
            "revision": node.revision,
            "x": positions[node.id][0],
            "y": positions[node.id][1],
        }
        for node in workflow.nodes
    ]
    edges: list[dict[str, str]] = []
    xs: list[float] = []
    ys: list[float] = []
    for x, y in positions.values():
        xs.extend((x, x + 200))
        ys.extend((y, y + 96))
    for target, sources in workflow.dependencies().items():
        for source in sorted(sources):
            if source not in positions:
                continue
            ax, ay = positions[source]
            bx, by = positions[target]
            x, y, xx, yy = ax + 200, ay + 48, bx, by + 48
            bend = max(50, abs(xx - x) / 2)
            xs.extend((x + bend, xx - bend))
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "path": f"M {x} {y} C {x + bend} {y}, {xx - bend} {yy}, {xx} {yy}",
                }
            )
    left, top = min(xs, default=0) - 24, min(ys, default=0) - 24
    width, height = max(xs, default=240) - left + 24, max(ys, default=120) - top + 24
    return {"nodes": nodes, "edges": edges, "viewbox": f"{left} {top} {width} {height}"}


def replay_messages() -> dict[str, str]:
    """運行回看頁的 JavaScript 用到的文字（replayjs. 開頭的鍵，目前語言；M12）。

    和 workflow_messages 一樣只放在那一頁（#replay-messages），訊息目錄裡寫 ``{{名稱}}``。
    """
    return {
        key.removeprefix("replayjs."): t(key)
        for key in t.messages(get_locale())
        if key.startswith("replayjs.")
    }


def workflow_messages() -> dict[str, str]:
    """自由試驗場頁面的 JavaScript 用到的文字（訊息目錄裡 wfjs. 開頭的鍵，目前語言）。

    放在試驗場頁面的 #workflow-messages，不加進每一頁都有的 js_messages。與 js_messages 相同：
    訊息目錄裡寫 ``{{名稱}}``，取出後是 ``{名稱}``，由 portal.js 代入。
    """
    return {
        key.removeprefix("wfjs."): t(key)
        for key in t.messages(get_locale())
        if key.startswith("wfjs.")
    }


_SINGLE_EXPRESSION: Final = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")


def _expression(text: str) -> Markup:
    """只有一個 ``{{ }}`` 的運算式顯示成裡面的內容（facts.record.recordId），比較短也比較好讀。

    在「.」後面加上斷行點：欄位窄的時候在名稱之間換行，不把名稱從中間切開。
    """
    match = _SINGLE_EXPRESSION.match(text.strip())
    shown = match.group(1) if match else text
    return Markup(".<wbr>").join(escape(part) for part in shown.split("."))


_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
# jinja2 的型別把 globals 限定為內建函式的型別；這裡放的是本專案的函式與資料
cast("dict[str, object]", _env.globals).update(
    t=page_t,
    via_recorder=via_recorder,
    menu_shown=menu_shown,
    composites_domain=COMPOSITES_DOMAIN,
    recorder_menus=RECORDER_MENUS,
    badge_color=badge_color,
    iso=_iso,
    display_time=_display_time,
    native_names=NATIVE_NAMES,
    locales=LOCALES,
    version=__version__,
    workflow_preview=workflow_preview,
)
_env.filters["pretty_json"] = _pretty_json
_env.filters["num"] = _number
_env.filters["compact_json"] = _compact_json
_env.filters["expression"] = _expression


def render(
    name: str,
    *,
    page: str,
    title: str,
    domains: Sequence[DomainRecord] = (),
    **context: object,
) -> str:
    """渲染一頁：page 是選單中目前的頁面，title 是頁面標題，domains 是場景管理的二級選單。

    context 的 worker_names 是 worker 代號 → 名稱（執行報告顯示由哪台執行；M9a），沒給時只有本機。
    here_display 是操作的那台能不能開瀏覽器視窗，沒給時當成可以。
    """
    group = _group_of(page)
    context.setdefault("worker_names", {"local": page_t("worker.local")})
    context.setdefault("here_display", True)
    return _env.get_template(name).render(
        page=page,
        group=group,
        nav=visible_nav(),
        side_items=_side_items(group, domains),
        domains=domains,
        title=title,
        locale=get_locale(),
        js_messages=js_messages(),
        **context,
    )
