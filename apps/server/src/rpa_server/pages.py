"""HTML 頁面：取資料、交給樣板（render.py）。寫入操作由頁面上的 JavaScript 呼叫 /api。"""

import json
import mimetypes
import os
import zipfile
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Final, Literal, cast
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from markupsafe import escape
from starlette.background import BackgroundTask

from rpa_core.dsl import ExtractStep, Scenario, validate_text
from rpa_core.dsl.editing import contract_section, section_text
from rpa_core.dsl.files import (
    ATTACHMENT_DIR,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_BYTES,
    FileValueError,
    attachment_names,
    file_values,
    uploaded_ids,
)
from rpa_core.dsl.yaml_writer import flow
from rpa_core.i18n import parse_locale
from rpa_runner.files import REPORT, STEP_SHOTS
from rpa_runner.installed import DISPLAY_NAMES
from rpa_server.agents import SCOPES
from rpa_server.composite_report import build_composite_report, embedded_screenshots
from rpa_server.config import EXAMPLES_DOMAIN
from rpa_server.debugging import IDLE_SECONDS
from rpa_server.domain import ENGINES, TARGETS, DomainRecord, RoleRecord, RunRecord, now
from rpa_server.errors import ServiceError, not_found
from rpa_server.gitsync import GitSource
from rpa_server.i18n import t
from rpa_server.middleware import LANG_COOKIE
from rpa_server.render import (
    composite_run_filters,
    domain_page,
    project_page,
    render,
    replay_messages,
    run_filters,
    workflow_messages,
)
from rpa_server.replay import dumps
from rpa_server.services import Services
from rpa_server.storage import SCENARIO_FILE

__all__ = ["page_router"]

FormPurpose = Literal["validation", "execution"]
"""執行表單的目的（試驗場序列的節點不從表單執行）。"""

_TEXT_TYPES: Final = {
    ".log": "text/plain",
    ".py": "text/plain",
    ".yaml": "text/plain",
    ".json": "application/json",
    ".webm": "video/webm",
}
_UTF8_TYPES: Final = frozenset({"application/json"})
"""不是 text/ 開頭、但內容是文字的類型：一樣標上 UTF-8。

沒標的話，瀏覽器用作業系統語言的預設編碼（簡體中文是 GBK）讀 JSON，中文會變成亂碼。
"""
_RECENT_RUNS: Final = 10
_COMPOSITE_RUNS: Final = 200
"""運行報告的「組合運行」檢視最多列幾次（和場景運行一樣）。"""
_REPORT_CSP: Final = (
    "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"
)
"""執行目錄的檔案的 CSP：報告是單一 HTML 檔，只有內嵌樣式與同目錄的截圖。

media-src 'self'：直接打開 video.webm 時，瀏覽器自己產生的播放頁也受這個 CSP 限制；
沒有它，影片載入會被擋，看起來就是「不能播放、也不能下載」。
"""


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content, headers={"Cache-Control": "no-store"})


_PORTAL_BAR: Final = (
    '<nav style="display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;'
    "padding:9px 16px;background:#eef6ff;border-bottom:1px solid #dfebf8;"
    'font:13px/1.6 system-ui,sans-serif">{links}</nav>'
)


def _with_portal_links(report: str, run: RunRecord) -> str:
    """在 Portal 裡打開 report.html 時，最上面加一列：回到運行詳情、錄影回看（有錄影時）、
    組合運行的匯總報告（組合裡的節點）。

    報告是 Runner 產生的單一檔案，離線開啟時沒有 Portal；這列只在 Portal 送出時加上，檔案本身不改。
    """
    links = [f'<a href="/runs/{escape(run.id)}">{escape(t("report_bar.back"))}</a>']
    video = run.video or {}
    if video.get("url"):
        links.append(
            f'<a href="/runs/{escape(run.id)}/replay"><strong>▶ {escape(t("report_bar.replay"))}'
            "</strong></a>"
        )
    elif video.get("deletedAt"):
        links.append(f"<span>{escape(t('report_bar.replay_deleted'))}</span>")
    if run.workflow_run_id:
        # 組合裡的節點：連到整次組合運行的匯總報告（2026-10-27）
        links.append(
            f'<a href="/playground/runs/{escape(run.workflow_run_id)}">'
            f"{escape(t('report_bar.composite', node=run.node_id or '—'))}</a>"
        )
    bar = _PORTAL_BAR.format(links="".join(links))
    head, separator, rest = report.partition("<body>")
    return head + separator + bar + rest if separator else bar + report


_SCRIPT_FILES: Final = ("automation.py", "assertion.py")
_FOCUS: Final = frozenset({"steps", "verify", "inputs", "outputs"})
_PARTS: Final = ("steps", "verify")
"""DSL 場景分開編輯的兩段：自動化步驟、獨立斷言。"""


def _counts(text: str | None) -> dict[str, int] | None:
    """錄製轉換出來的內容有多少：步驟、入參、出參、斷言、Secret（錄製詳情的重點）。"""
    if not text:
        return None
    scenario = validate_text(text).scenario
    if scenario is None:
        return None
    return {
        "steps": len(scenario.steps or []),
        "inputs": len(scenario.inputs),
        "outputs": len(scenario.outputs),
        "verify": len(scenario.verify or []),
        "secrets": len(scenario.secrets),
    }


def _contract_data(scenario: Scenario, source: str | None = None) -> dict[str, object]:
    """入參、出參編輯器的初始資料（DSL 寫法的欄位，camelCase）。

    用 [名稱, 規格] 的清單保留場景檔裡的順序（模板的 tojson 會把物件的鍵排序）。
    """
    data: dict[str, object] = {
        key: [
            [name, spec.model_dump(mode="json", by_alias=True, exclude_none=True)]
            for name, spec in specs.items()
        ]
        for key, specs in (("inputs", scenario.inputs), ("outputs", scenario.outputs))
    }
    data["yaml"] = {
        key: section_text(source, key)
        if source is not None
        else contract_section(
            key,
            {
                name: spec.model_dump(mode="json", by_alias=True, exclude_none=True)
                for name, spec in specs.items()
            },
        )
        for key, specs in (("inputs", scenario.inputs), ("outputs", scenario.outputs))
    }
    return data


def _facts(scenario: Scenario) -> list[tuple[str, list[str]]]:
    """步驟產生的頁面事實：(名稱, 欄位)；斷言與出參的編輯器列出來方便引用。"""
    found: list[tuple[str, list[str]]] = []
    for step in scenario.steps or []:
        if isinstance(step, ExtractStep):
            found.append((step.as_, list(step.fields or {})))
    return found


_AUTO_LOGIN_EXAMPLE: Final = """- { id: open, action: goto, url: https://erp.example.com/login }
- { id: user, action: fill, target: { label: 帳號 }, value: clerk01 }
- { id: password, action: fill, target: { label: 密碼 }, value: '{{ secrets.ERP_PASSWORD }}' }
- { id: submit, action: click, target: { role: button, name: 登入 } }"""
_SHOT_HEADERS: Final = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _check_text(role: RoleRecord) -> str:
    return flow(role.check_locator)


def _role_values(role: RoleRecord) -> dict[str, object]:
    """編輯角色對話框預先填入的值。"""
    return {
        "name": role.name,
        "description": role.description or "",
        "loginUrl": role.login_url,
        "checkUrl": role.check_url or "",
        "check": _check_text(role),
        "engine": role.engine,
        "autoLogin": role.auto_login or "",
        "domainId": role.domain_id or "",
    }


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _size(value: object) -> str:
    """位元組 → 給人看的大小（KB、MB、GB）。"""
    if not isinstance(value, int) or isinstance(value, bool):
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def _no_video_reason(
    finished: bool, video: dict[str, object] | None, result: dict[str, object] | None
) -> str:
    """回看頁沒有影片時的說明（M12）。"""
    if not finished:
        return t("replay.no_video_running")
    if video is not None and video.get("deletedAt"):
        reason = str(video.get("deletedReason") or "expired")
        return t("replay.no_video_deleted", reason=t(f"replay.deleted_{reason}"))
    if video is not None and video.get("error"):
        return t("replay.no_video_failed", error=str(video["error"]))
    if result is not None and result.get("kind") == "script":
        return t("replay.no_video_script")
    return t("replay.no_video_off")


def _location_context(services: Services) -> dict[str, object]:
    """執行表單用：執行位置的選項，以及預設位置能不能有頭模式（display）。"""
    locations = services.locations()
    display = cast("dict[str, bool]", locations["display"])
    return {"locations": locations, "display": display[str(locations["default"])]}


def _scene_attachments(
    services: Services, scene_id: str, number: int, scenario: Scenario | None
) -> list[dict[str, object]]:
    """場景詳情頁的附件區（M7c）：每個附件的大小，以及哪些檔案入參的預設值用到它。"""
    used: dict[str, list[str]] = {}
    inputs = scenario.inputs if scenario is not None else {}
    for name, spec in inputs.items():
        if spec.type == "file" and spec.default is not None:
            for path in attachment_names([spec.default]):
                used.setdefault(path, []).append(name)
    return [
        {
            "path": path,
            "name": path.removeprefix(f"{ATTACHMENT_DIR}/"),
            "size": size,
            "inputs": used.get(path, []),
        }
        for path, size in sorted(services.storage.attachments(scene_id, number).items())
    ]


def _run_file_inputs(
    services: Services,
    record: RunRecord,
    scenario: Scenario | None,
    result: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    """運行詳情頁的檔案入參（M7c）：每個檔案的入參、網頁看到的檔名、大小、sha256、來源與下載連結。

    值以這次執行送出的為準（沒給的用場景預設值）；跑完後大小與 sha256 以執行目錄的 input.json 為準。
    上傳檔過了保留期限只剩紀錄，不給下載連結。
    """
    if scenario is None:
        return []
    executed = result.get("input") if result is not None else None
    empty: dict[str, object] = {}
    meta = cast("Mapping[str, object]", executed) if isinstance(executed, Mapping) else empty
    found = services.uploads.rows(uploaded_ids(record.input.values()))
    rows: list[dict[str, object]] = []
    for name, spec in scenario.inputs.items():
        if spec.type != "file":
            continue
        given = name in record.input
        raw = record.input[name] if given else spec.default
        if raw is None:
            continue
        try:
            items = file_values(raw, multiple=bool(spec.multiple))
        except FileValueError:
            continue
        seen = meta.get(name)
        details = cast("list[object]", seen) if isinstance(seen, list) else [seen]
        for index, item in enumerate(items):
            detail = details[index] if index < len(details) else None
            info = cast("Mapping[str, object]", detail) if isinstance(detail, Mapping) else empty
            row: dict[str, object] = {
                "input": name,
                "source": item.source,
                "name": info.get("name") or item.display_name,
                "size": info.get("size", item.size),
                "sha256": info.get("sha256", item.sha256),
                "default": not given,
                "href": None,
                "gone": False,
            }
            if item.source == "upload":
                upload = found.get(item.ref)
                row["gone"] = upload is None or upload.deleted_at is not None
                if not row["gone"]:
                    row["href"] = f"/api/files/{item.ref}/content"
            elif item.source == "attachment":
                attachment = item.ref.removeprefix(f"{ATTACHMENT_DIR}/")
                row["href"] = (
                    f"/api/scenes/{record.scene_id}/revisions/{record.revision_number}"
                    f"/attachments/{attachment}"
                )
            rows.append(row)
    return rows


def _file_context(
    services: Services, scene_id: str, number: int, scenario: Scenario
) -> dict[str, object]:
    """執行、驗證、調試表單的檔案入參（M7c）：哪些入參是檔案、這個版本有哪些場景附件、單檔上限。"""
    inputs = [(name, spec) for name, spec in scenario.inputs.items() if spec.type == "file"]
    attachments = services.storage.attachments(scene_id, number) if inputs else {}
    return {
        "file_inputs": inputs,
        "attachments": [
            {"path": path, "name": path.removeprefix(f"{ATTACHMENT_DIR}/"), "size": size}
            for path, size in sorted(attachments.items())
        ],
        "upload_limit": services.uploads.limits.max_file,
    }


def page_router(services: Services) -> APIRouter:
    router = APIRouter()

    def page(name: str, *, page: str, title: str, **context: object) -> HTMLResponse:
        """渲染一頁；每一頁都帶著領域清單（場景管理的二級選單）與專案清單（專案空間的二級選單）。

        here_display：操作的那台能不能開瀏覽器視窗（錄製、逐步調試、人工登入）；不能時這些入口變灰，
        滑鼠移上去提示改用錄製端。
        """
        context.setdefault("worker_names", services.workers.names())
        context.setdefault("agent_names", services.agents.names())
        context.setdefault("here_display", services.display_here())
        return _html(
            render(
                name,
                page=page,
                title=title,
                domains=services.list_domains(),
                projects=services.projects.list_projects(),
                **context,
            )
        )

    def domain_of(domain_id: str | None) -> DomainRecord | None:
        return services.get_domain(domain_id) if domain_id else None

    @router.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/scenes", status_code=303)

    @router.get("/lang/{code}", include_in_schema=False)
    def change_language(code: str, next: str = "/scenes") -> RedirectResponse:
        # 只接受站內的相對網址，避免被當成轉址跳板
        parts = urlsplit(next)
        target = next if next.startswith("/") and not parts.netloc and not parts.scheme else "/"
        response = RedirectResponse(target, status_code=303)
        locale = parse_locale(code)
        if locale is not None:
            response.set_cookie(LANG_COOKIE, locale, max_age=365 * 24 * 3600, samesite="lax")
        return response

    @router.get("/scenes", include_in_schema=False)
    def scenes() -> RedirectResponse:
        """場景管理：到第一個領域；還沒有領域時到領域管理。"""
        domains = services.list_domains()
        return RedirectResponse(f"/domains/{domains[0].id}" if domains else "/domains", 303)

    @router.get("/domains", include_in_schema=False)
    def domains() -> HTMLResponse:
        return page(
            "domains.html",
            page="domains",
            title=t("nav.domains"),
            unassigned=services.unassigned_scenes(),
            syncs={item.id: services.git.status(item.id) for item in services.list_domains()},
            server=services.server_info(),
            git_available=services.git.available(),
            dependents=services.workflows.dependents(),
        )

    @router.get("/domains/{domain_id}/sync", include_in_schema=False)
    def domain_sync(domain_id: str) -> HTMLResponse:
        """資料來源與同步（M11 PR 3）：設定、狀態、拉取、推送、衝突。"""
        record = services.get_domain(domain_id)
        sync = services.git.status(domain_id)
        return page(
            "domain_sync.html",
            page=domain_page(domain_id),
            title=t("sync.page_title", name=record.name),
            domain=record,
            sync=sync,
            source=sync.source or GitSource(url="", directory=domain_id),
            server=services.server_info(),
        )

    @router.get("/domains/{domain_id}", include_in_schema=False)
    def domain(domain_id: str) -> HTMLResponse:
        record = services.get_domain(domain_id)
        examples = services.examples_dir
        return page(
            "domain.html",
            page=domain_page(domain_id),
            title=record.name,
            domain=record,
            cards=services.scene_cards(domain_id),
            sync=services.git.status(domain_id),
            can_import=domain_id == EXAMPLES_DOMAIN and examples is not None and examples.is_dir(),
        )

    @router.get("/scenes/{scene_id}", include_in_schema=False)
    def scene(scene_id: str) -> HTMLResponse:
        """場景詳情頁：一個場景的落地頁，由上到下是運行設定、腳本、入參與出參、版本、驗證、最近運行。"""
        record = services.get_scene(scene_id)
        try:
            scenario = services.revision_scenario(scene_id, record.latest_number)
        except ServiceError:
            scenario = None
        files = services.revision_files(scene_id, record.latest_number)
        if scenario is not None and scenario.script is None:
            scripts = {part: section_text(files[SCENARIO_FILE], part) for part in _PARTS}
        else:
            scripts = {name: files[name] for name in _SCRIPT_FILES if name in files}
        return page(
            "scene.html",
            scripts=scripts,
            script_counts={
                "steps": len(scenario.steps or []) if scenario is not None else 0,
                "verify": len(scenario.verify or []) if scenario is not None else 0,
            },
            needs=services.scene_needs(scenario) if scenario is not None else None,
            page=domain_page(record.domain_id),
            title=record.name,
            scene=record,
            domain=domain_of(record.domain_id),
            revisions=services.revisions(scene_id),
            verifications=services.verifications(scene_id),
            scenario=scenario,
            default_base_url=scenario.browser.base_url if scenario else None,
            runs=services.list_runs(scenes=[scene_id], limit=_RECENT_RUNS),
            attachments=_scene_attachments(services, scene_id, record.latest_number, scenario),
            attachment_limits={"file": MAX_ATTACHMENT_BYTES, "total": MAX_ATTACHMENTS_BYTES},
            contract_data=_contract_data(scenario, files[SCENARIO_FILE])
            if scenario is not None
            else {},
            facts=_facts(scenario) if scenario is not None else [],
        )

    @router.get("/scenes/{scene_id}/edit", include_in_schema=False)
    def edit(
        scene_id: str,
        revision: int | None = None,
        file: str = "",
        focus: str = "",
        part: str = "",
        line: int = 0,
    ) -> Response:
        record = services.get_scene(scene_id)
        if part in _PARTS:
            # 自動化腳本、斷言腳本在場景詳情頁的「腳本」區編輯（2026-10-25）；舊網址轉過去
            return RedirectResponse(f"/scenes/{scene_id}#{part}", 303)
        shown = services.get_revision(scene_id, revision)
        files = services.revision_files(scene_id, shown.number)
        # 完整場景檔；Python 腳本場景可以直接打開 automation.py、assertion.py
        selected = file if file in files and file in (*_SCRIPT_FILES, "scenario.yaml") else ""
        return page(
            "edit.html",
            page=domain_page(record.domain_id),
            title=t("edit.title", name=record.name),
            scene=record,
            domain=domain_of(record.domain_id),
            revision=shown,
            files=files,
            selected=selected or next(iter(files)),
            focus=focus if focus in _FOCUS else "",
            line=max(0, line),
        )

    @router.get("/scenes/{scene_id}/run", include_in_schema=False)
    def run_form(
        scene_id: str, purpose: FormPurpose = "execution", revision: int | None = None
    ) -> HTMLResponse:
        record = services.get_scene(scene_id)
        if purpose == "execution":
            if record.published_number is None:
                raise ServiceError(409, "not_published", t("error.not_published", id=scene_id))
            revision = record.published_number
        shown = services.get_revision(scene_id, revision)
        scenario = services.revision_scenario(scene_id, shown.number)
        defaults = {
            name: spec.default for name, spec in scenario.inputs.items() if spec.default is not None
        }
        defaults |= {name: "" for name, spec in scenario.inputs.items() if spec.default is None}
        return page(
            "run_form.html",
            page=domain_page(record.domain_id),
            title=t(f"run_form.title_{purpose}", name=record.name, number=shown.number),
            scene=record,
            domain=domain_of(record.domain_id),
            revision=shown,
            scenario=scenario,
            purpose=purpose,
            defaults=defaults,
            engines=ENGINES,
            base_url=record.base_url or scenario.browser.base_url,
            **_location_context(services),
            **_file_context(services, scene_id, shown.number, scenario),
        )

    @router.get("/runs", include_in_schema=False)
    def runs(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        worker: Annotated[list[str] | None, Query()] = None,
        video: Annotated[list[str] | None, Query()] = None,
        view: str = "",
        project: Annotated[list[str] | None, Query()] = None,
        composite: Annotated[list[str] | None, Query()] = None,
    ) -> HTMLResponse:
        """運行報告：篩選、每一次運行的錄影回看連結；錄影設定也在這頁（原本的運行回看併進來，2026-10-25）。

        ``view=composite`` 是「組合運行」檢視（2026-10-27）：一列一次組合運行，點進去是匯總報告。
        """
        if view == "composite":
            return composite_runs(
                status=status, purpose=purpose, worker=worker, project=project, composite=composite
            )
        selected = {
            "scene": [item for item in scene or [] if item],
            "category": [item for item in category or [] if item],
            "status": [item for item in status or [] if item],
            "purpose": [item for item in purpose or [] if item],
            "worker": [item for item in worker or [] if item],
            "video": [item for item in video or [] if item == "1"],
        }
        return page(
            "runs.html",
            page="runs",
            title=t("nav.runs"),
            view="scene",
            runs=services.list_runs(
                scenes=selected["scene"],
                categories=selected["category"],
                statuses=selected["status"],
                purposes=selected["purpose"],
                workers=selected["worker"],
                with_video=bool(selected["video"]),
            ),
            filters=run_filters(
                scenes=services.list_scenes(include_archived=True),
                categories=services.run_categories(),
                selected=selected,
                locations=services.run_locations(),
            ),
            video_settings=services.video_settings(),
            limit=200,
        )

    def composite_runs(
        *,
        status: list[str] | None,
        purpose: list[str] | None,
        worker: list[str] | None,
        project: list[str] | None,
        composite: list[str] | None,
    ) -> HTMLResponse:
        """運行報告的「組合運行」檢視：專案、組合場景、結果、目的、執行位置的篩選。"""
        selected = {
            "project": [item for item in project or [] if item],
            "composite": [item for item in composite or [] if item.isdigit()],
            "status": [item for item in status or [] if item],
            "purpose": [item for item in purpose or [] if item],
            "worker": [item for item in worker or [] if item],
        }
        records = services.workflows.list_workflows()
        names = {record.id: record.name for record in records}
        project_names = {item.id: item.name for item in services.projects.list_projects()}
        return page(
            "runs.html",
            page="runs",
            title=t("nav.runs"),
            view="composite",
            runs=[],
            composite_runs=services.workflows.list_runs(
                limit=_COMPOSITE_RUNS,
                projects=selected["project"] or None,
                statuses=selected["status"],
                purposes=selected["purpose"],
                workflow_ids=[int(item) for item in selected["composite"]],
                workers=selected["worker"],
            ),
            composite_projects={
                record.id: project_names[record.project_id]
                for record in records
                if record.project_id in project_names
            },
            composite_names=names,
            filters=composite_run_filters(
                projects=services.projects.list_projects(),
                composites=sorted(names.items(), key=lambda item: item[1].casefold()),
                selected=selected,
                locations=services.run_locations(),
            ),
            video_settings=services.video_settings(),
            limit=_COMPOSITE_RUNS,
        )

    @router.get("/replay", include_in_schema=False)
    def replays(request: Request) -> RedirectResponse:
        """原本的「運行回看」清單和運行報告重複，併進運行報告（2026-10-25）：舊網址轉到只看有錄影的運行。"""
        query = [
            (key, value) for key, value in request.query_params.multi_items() if key != "video"
        ]
        return RedirectResponse("/runs?" + urlencode([*query, ("video", "1")]), 303)

    @router.get("/runs/{run_id}/replay", include_in_schema=False)
    def replay(run_id: str) -> HTMLResponse:
        """回看一次運行：影片、縮圖時間軸、和步驟關聯（M12，ADR 0016）。"""
        record = services.get_run(run_id)
        data = services.replay(run_id)
        video = cast("dict[str, object] | None", data["video"])
        playable = bool(video and video.get("playable"))
        result = services.run_result(run_id) if record.finished else None
        return page(
            "replay.html",
            page="runs",
            title=t("replay.title", id=record.id),
            run=record,
            data=data,
            data_json=dumps(data),
            video=video or {},
            playable=playable,
            workflow=data["workflow"],
            engine=(result or {}).get("engine") or record.engine or t("run.engine_scenario"),
            no_video_reason=_no_video_reason(record.finished, video, result),
            started=_parse_time(video.get("startedAt")) if video else None,
            keep_until=_parse_time(video.get("keepUntil")) if video else None,
            size=_size(video.get("bytes")) if video else "",
            replay_messages=replay_messages(),
        )

    @router.get("/runs/{run_id}", include_in_schema=False)
    def run(run_id: str) -> HTMLResponse:
        record = services.get_run(run_id)
        if record.purpose == "validation" and record.status == "passed":
            # 結果剛提交、驗證紀錄還沒寫時先補寫，通過的驗證一打開就有「發布」（2026-10-28）
            services.settle_validations(record.scene_id, record.revision_number)
        revision = services.get_revision(record.scene_id, record.revision_number)
        can_publish = (
            record.purpose == "validation"
            and record.status == "passed"
            and revision.verified
            and revision.problem is None
            and not revision.published
            and record.scenario_hash == revision.content_hash
        )
        try:
            scenario = services.revision_scenario(record.scene_id, record.revision_number)
        except ServiceError:
            scenario = None
        login = scenario.login if scenario is not None else None
        files = services.storage.run_files(run_id) if record.finished else []
        result = services.run_result(run_id) if record.finished else None
        return page(
            "run.html",
            page="runs",
            title=t("run.title", id=record.id),
            role=login.role if login is not None else None,
            run=record,
            revision=revision,
            result=result,
            files=files,
            file_inputs=_run_file_inputs(services, record, scenario, result),
            keep_days=services.uploads.limits.keep_days,
            can_publish=can_publish,
            worker_wait=None if record.finished else services.worker_wait(run_id),
        )

    @router.get("/runs/{run_id}/files/{relative:path}", include_in_schema=False)
    def run_file(run_id: str, relative: str, download: bool = False) -> Response:
        """執行目錄裡的檔案；``download=1`` 時一律下載（不在瀏覽器裡打開）。"""
        path = services.run_file(run_id, relative)
        if path.suffix == ".html" and relative != REPORT:
            media_type = "text/plain"  # 只有執行報告當成網頁顯示
        else:
            media_type = _TEXT_TYPES.get(path.suffix) or mimetypes.guess_type(path.name)[0]
        if media_type and (media_type.startswith("text/") or media_type in _UTF8_TYPES):
            media_type += "; charset=utf-8"
        # 錄影寫完就不會再變（M12）：讓瀏覽器拖曳時不必重抓同一段；每一步的截圖（2026-10-29）也是；
        # 其他檔案每次都重抓
        fixed = path.suffix == ".webm" or relative.startswith(f"{STEP_SHOTS}/")
        headers = {
            "Cache-Control": "private, max-age=86400" if fixed else "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": _REPORT_CSP,
        }
        if download:
            return FileResponse(
                path,
                media_type=media_type,
                headers=headers,
                filename=f"{run_id}-{path.name}",
                content_disposition_type="attachment",
            )
        if relative == REPORT:
            # 在 Portal 裡看報告時，最上面加回到運行詳情與錄影回看的連結（離線開啟的檔案不變）
            text = path.read_text(encoding="utf-8")
            return HTMLResponse(_with_portal_links(text, services.get_run(run_id)), headers=headers)
        return FileResponse(path, media_type=media_type, headers=headers)

    @router.get("/recording", include_in_schema=False)
    def recording(scene: str = "") -> HTMLResponse:
        """自主腳本錄製：在這台電腦錄製或貼上錄製稿，轉成場景草稿。"""
        recordings = services.recordings.list_recordings()
        via = services.recorders.current()
        here = via.id if via is not None else None
        # 每台裝置同一時間各一段錄製：只看操作的這台的
        active = next(
            (item for item in recordings if item.status == "recording" and item.device_id == here),
            None,
        )
        domains = services.list_domains()
        return page(
            "recording.html",
            page="recording",
            title=t("nav.recording"),
            recordings=recordings,
            active=active,
            scenes=services.list_scenes(),
            roles=services.roles.list_roles(),
            engines=ENGINES,
            display=services.display_here(),
            default_domain=domains[0].id if domains else "",
            default_url="",
            selected_scene=scene,
            scene_defaults=services.recording_defaults(),
        )

    @router.get("/recordings/{recording_id}", include_in_schema=False)
    def recording_detail(recording_id: str) -> HTMLResponse:
        item = services.recordings.get_recording(recording_id)
        files = services.recordings.files(recording_id)
        return page(
            "recording_detail.html",
            page="recording",
            title=t("recording.detail_title", id=item.id),
            item=item,
            files=files,
            counts=_counts(files.get(SCENARIO_FILE)),
        )

    # ------------------------------------------------------------ 登入與憑證

    @router.get("/roles", include_in_schema=False)
    def roles() -> HTMLResponse:
        records = services.roles.list_roles()
        secrets = services.roles.list_secrets()
        usage = services.secret_usage()
        stored = {info.name for info in secrets}
        missing = [(name, users) for name, users in sorted(usage.items()) if name not in stored]
        return page(
            "roles.html",
            page="roles",
            title=t("nav.roles"),
            roles=records,
            secrets=secrets,
            usage=usage,
            missing=missing,
            environ={name for name, _ in missing if name in os.environ},
            display=services.display_here(),
            # 「檢查」沒有地方可以跑（伺服器沒有這個瀏覽器、也不是透過錄製端）：按鈕變灰的說明
            check_unavailable={
                engine: t("roles.check_unavailable", browser=DISPLAY_NAMES.get(engine, engine))
                for engine in ENGINES
                if not services.roles.can_check(engine)
            },
            busy=any(role.activity for role in records),
            engines=ENGINES,
            check_text=_check_text,
            role_values=_role_values,
            auto_example=_AUTO_LOGIN_EXAMPLE,
            domain_names={domain.id: domain.name for domain in services.list_domains()},
        )

    # ------------------------------------------------------------ 調試工作階段

    @router.get("/scenes/{scene_id}/debug", include_in_schema=False)
    def debug(scene_id: str, revision: int | None = None) -> HTMLResponse:
        record = services.get_scene(scene_id)
        session = services.debug.for_scene(scene_id)
        shown = session.revision if session is not None else (revision or record.latest_number)
        scenario = services.revision_scenario(scene_id, shown)
        defaults = {n: s.default for n, s in scenario.inputs.items() if s.default is not None}
        defaults |= {n: "" for n, s in scenario.inputs.items() if s.default is None}
        files = services.revision_files(scene_id, shown)
        return page(
            "debug.html",
            page=domain_page(record.domain_id),
            title=t("debug.title", name=record.name),
            scene=record,
            domain=domain_of(record.domain_id),
            session=session,
            scenario=scenario,
            revisions=services.revisions(scene_id),
            shown=shown,
            yaml=files.get("scenario.yaml", ""),
            defaults=defaults,
            needs=services.scene_needs(scenario),
            display=services.display_here(),
            engines=ENGINES,
            base_url=record.base_url or scenario.browser.base_url,
            idle_minutes=int(IDLE_SECONDS // 60),
            **_file_context(services, scene_id, shown, scenario),
        )

    @router.get("/debug/{session_id}/files/{name}", include_in_schema=False)
    def debug_file(session_id: str, name: str) -> Response:
        services.debug.get(session_id)
        path = services.storage.debug_file(session_id, name)
        if path is None:
            raise ServiceError(404, "file_not_found", t("error.file_not_found", path=name))
        return FileResponse(path, media_type="image/png", headers=_SHOT_HEADERS)

    # ------------------------------------------------------------ 自由試驗場（M6）

    workflows = services.workflows

    @router.get("/workers", include_in_schema=False)
    def workers_page() -> RedirectResponse:
        """M10.1 起「遠端 Worker」頁改為「裝置」頁；舊網址轉過去。"""
        return RedirectResponse("/devices", status_code=301)

    @router.get("/devices", include_in_schema=False)
    def devices_page() -> HTMLResponse:
        """裝置：登記、邀請與配對、狀態、預設執行位置（M9a；M10.1 邀請；M10.2 錄製端）。"""
        port = services.worker_port
        api_url = services.external_url()
        records = services.workers.list_workers()
        recorders = services.recorders.list_recorders()
        updates = services.device_updates
        return page(
            "workers.html",
            page="workers",
            title=t("nav.workers"),
            workers=records,
            recorders=recorders,
            device_updates=updates.summary(),
            worker_updates={
                item.id: report
                for item in records
                if (report := updates.report("worker", item.id)) is not None
            },
            recorder_updates={
                item.id: report
                for item in recorders
                if (report := updates.report("recorder", item.id)) is not None
            },
            default_target=services.locations()["default"],
            targets=TARGETS,
            local_worker=services.local_worker,
            worker_port=port,
            api_url=api_url,
            fingerprint=services.workers.fingerprint,
        )

    @router.get("/agents", include_in_schema=False)
    def agents_page(client: str | None = None) -> HTMLResponse:
        """API 用戶端（M14）：登記、權限範圍與限制、停用、重新產生金鑰、稽核紀錄。"""
        return page(
            "agents.html",
            page="agents",
            title=t("nav.agents"),
            agents=services.agents.list_clients(),
            audit=services.agents.list_audit(client_id=client or None, limit=100),
            audit_client=client or None,
            scopes=SCOPES,
            targets=TARGETS,
            recorders=services.recorders.list_recorders(),
            workers=services.workers.list_workers(),
            local_worker=services.local_worker,
            worker_port=services.worker_port,
            api_url=services.external_url(),
            now=now(),
        )

    # ------------------------------------------------------------ 專案空間（2026-10-23）

    projects = services.projects

    @router.get("/workspace", include_in_schema=False)
    def workspace() -> Response:
        """專案空間：到第一個專案；還沒有專案時留在專案空間，說明到專案管理建立。"""
        items = projects.list_projects()
        if items:
            return RedirectResponse(f"/projects/{items[0].id}", 303)
        return page("workspace.html", page="workspace", title=t("nav.workspace"))

    @router.get("/composites", include_in_schema=False)
    def composites() -> RedirectResponse:
        """原本的「組合場景自動化」換成專案空間的專案；舊網址轉過去。"""
        return RedirectResponse("/workspace", 303)

    @router.get("/projects", include_in_schema=False)
    def projects_page() -> HTMLResponse:
        """專案管理（管理後台）：新增、改名、刪除、調整順序；還沒分到專案的組合場景。"""
        return page(
            "projects.html",
            page="projects",
            title=t("nav.projects"),
            unassigned=workflows.unassigned(),
        )

    @router.get("/projects/{project_id}", include_in_schema=False)
    def project(project_id: str) -> HTMLResponse:
        """專案頁：就是一份「組合場景自動化」，只列這個專案的組合場景與它們的執行。"""
        record = projects.get_project(project_id)
        return page(
            "project.html",
            page=project_page(project_id),
            title=record.name,
            project=record,
            data={"engines": list(ENGINES), **_location_context(services)},
            workflows=workflows.list_workflows(project_id=project_id),
            runs=workflows.list_runs(project_id=project_id, limit=_RECENT_RUNS * 2),
            has_published=bool(workflows.library()),
            messages=workflow_messages(),
            domain_names={domain.id: domain.name for domain in services.list_domains()},
        )

    @router.get("/playground", include_in_schema=False)
    def playground() -> HTMLResponse:
        """組合場景的生產入口：建立或繼續編輯畫布。"""
        return page(
            "playground.html",
            page="playground",
            title=t("nav.playground"),
            workflows=workflows.list_workflows(),
            runs=workflows.list_runs(limit=_RECENT_RUNS * 2),
            has_published=bool(workflows.library()),
            messages=workflow_messages(),
        )

    @router.get("/playground/{workflow_id}", include_in_schema=False)
    def workflow(workflow_id: int) -> HTMLResponse:
        """編輯組合場景：場景庫、DAG 畫布、入參與節點設定。"""
        record = workflows.get_workflow(workflow_id)
        data = {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "description": record.description or "",
            "version": record.version,
            "latestRevision": record.version,
            "publishedRevision": record.published_number,
            "definition": record.workflow.to_json(),
            "problems": [problem.to_json() for problem in record.problems],
            "library": workflows.library(),
            "engines": list(ENGINES),
            **_location_context(services),
        }
        return page(
            "workflow.html",
            page=project_page(record.project_id) if record.project_id else "playground",
            title=record.name,
            workflow=record,
            project=projects.get_project(record.project_id) if record.project_id else None,
            data=data,
            messages=workflow_messages(),
            runs=workflows.list_runs(workflow_id=workflow_id, limit=_RECENT_RUNS),
            revisions=workflows.revisions(workflow_id),
            verifications=workflows.verifications(workflow_id),
            dependencies=workflows.dependencies(workflow_id),
        )

    @router.get("/playground/runs/{run_id}", include_in_schema=False)
    def workflow_run(run_id: str) -> HTMLResponse:
        """組合運行的匯總報告（2026-10-27）：結論、數字、流程與時間、每個節點的入參出參、步驟與斷言。"""
        record, definition = workflows.get_run_with_definition(run_id)
        exists = True
        owner = None
        if record.workflow_id is not None:
            try:
                project_id = workflows.get_workflow(record.workflow_id).project_id
            except ServiceError:
                exists = False
            else:
                owner = projects.get_project(project_id) if project_id else None
        role = None
        stopped = next((node for node in record.nodes if node.id == record.failed_node), None)
        if record.status == "needs_login" and stopped is not None:
            try:
                login = services.revision_scenario(stopped.scene_id, stopped.revision).login
            except ServiceError:
                login = None
            role = login.role if login is not None else None
        waiting = None
        if not record.finished:
            queued = (node.run for node in record.nodes if node.run is not None)
            waiting = next(
                (wait for run in queued if (wait := services.worker_wait(run.id)) is not None), None
            )
        return page(
            "workflow_run.html",
            page=project_page(owner.id) if owner is not None else "playground",
            title=t("workflow_run.title", id=record.id),
            run=record,
            report=build_composite_report(record, definition, services.storage),
            definition=definition,
            worker_wait=waiting,
            workflow_exists=exists and record.workflow_id is not None,
            project=owner,
            role=role,
            messages=workflow_messages(),
        )

    @router.get("/playground/runs/{run_id}/replay", include_in_schema=False)
    def workflow_run_replay(run_id: str) -> HTMLResponse:
        """組合運行的合併回看（2026-10-27，ADR 0019）：一個播放器從頭看完整次運行。"""
        record = workflows.get_run(run_id)
        data, report = services.composite_replay(run_id)
        state = services.composite_video(run_id)
        video = cast("dict[str, object] | None", data["video"])
        owner = None
        if record.workflow_id is not None:
            try:
                project_id = workflows.get_workflow(record.workflow_id).project_id
            except ServiceError:
                project_id = None
            owner = projects.get_project(project_id) if project_id else None
        return page(
            "composite_replay.html",
            page=project_page(owner.id) if owner is not None else "playground",
            title=t("creplay.title", id=record.id),
            run=record,
            project=owner,
            data=data,
            data_json=dumps(data),
            video=video or {},
            playable=bool(video and video.get("playable")),
            nodes={
                str(node["id"]): node for node in cast("list[dict[str, object]]", report["nodes"])
            },
            video_state=state,
            keep_until=_parse_time(state.get("keepUntil")),
            size=_size(state.get("bytes")),
            replay_messages=replay_messages(),
        )

    @router.get("/playground/runs/{run_id}/videos.zip", include_in_schema=False)
    def workflow_run_videos(run_id: str) -> Response:
        """下載整次組合運行的錄影：各節點的片段依合併回看的順序編號，
        加上說明順序的 playlist.json。"""
        files = services.composite_video_files(run_id)
        if not files:
            raise not_found("video_not_found", t("creplay.no_video"))
        data, _ = services.composite_replay(run_id)
        playlist = {
            "compositeRun": run_id,
            "files": [name for name, _ in files],
            "segments": cast("dict[str, object]", data["composite"])["segments"],
        }
        target = services.storage.work / f"{run_id}-videos.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, path in files:
                archive.write(path, name)
            archive.writestr("playlist.json", json.dumps(playlist, ensure_ascii=False, indent=2))
        return FileResponse(
            target,
            media_type="application/zip",
            filename=f"{run_id}-videos.zip",
            background=BackgroundTask(target.unlink, missing_ok=True),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.get("/playground/runs/{run_id}/report.html", include_in_schema=False)
    def workflow_run_report(run_id: str) -> HTMLResponse:
        """下載組合運行的匯總報告：單一 HTML、不需要網路，用看的人的語言產生（不另存檔）。

        截圖只嵌入沒通過的節點的（D4）；連到 Portal 的連結都拿掉，離線打開也看得懂。
        """
        record, definition = workflows.get_run_with_definition(run_id)
        report = build_composite_report(record, definition, services.storage)
        content = render(
            "composite_report_file.html",
            page="playground",
            title=t("workflow_run.title", id=record.id),
            run=record,
            report=report,
            images=embedded_screenshots(report, services.storage),
            generated=now(),
        )
        return HTMLResponse(
            content,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": _REPORT_CSP,
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{record.id}-report.html"',
            },
        )

    return router
