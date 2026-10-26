"""HTML 頁面：取資料、交給樣板（render.py）。寫入操作由頁面上的 JavaScript 呼叫 /api。"""

import mimetypes
import os
from datetime import datetime
from typing import Annotated, Final, Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from rpa_core.dsl import ExtractStep, Scenario, validate_text
from rpa_core.dsl.editing import contract_section, section_text
from rpa_core.dsl.yaml_writer import flow
from rpa_core.i18n import parse_locale
from rpa_runner.files import REPORT
from rpa_runner.installed import DISPLAY_NAMES
from rpa_runner.video import video_files
from rpa_server.agents import SCOPES
from rpa_server.config import EXAMPLES_DOMAIN
from rpa_server.debugging import IDLE_SECONDS
from rpa_server.domain import ENGINES, TARGETS, DomainRecord, RoleRecord, now
from rpa_server.errors import ServiceError
from rpa_server.gitsync import GitSource
from rpa_server.i18n import t
from rpa_server.middleware import LANG_COOKIE
from rpa_server.render import (
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
    ".webm": "video/webm",
}
_RECENT_RUNS: Final = 10
_REPORT_CSP: Final = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content, headers={"Cache-Control": "no-store"})


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
        record = services.get_scene(scene_id)
        try:
            scenario = services.revision_scenario(scene_id, record.latest_number)
        except ServiceError:
            scenario = None
        return page(
            "scene.html",
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
            contract_data=_contract_data(
                scenario, services.revision_files(scene_id, record.latest_number)[SCENARIO_FILE]
            )
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
    ) -> HTMLResponse:
        record = services.get_scene(scene_id)
        shown = services.get_revision(scene_id, revision)
        files = services.revision_files(scene_id, shown.number)
        scenario = services.revision_scenario(scene_id, shown.number)
        if part in _PARTS and scenario.script is None:
            # DSL 場景的「自動化腳本」「斷言腳本」：只顯示、只改寫場景檔的那一段
            return page(
                "section.html",
                page=domain_page(record.domain_id),
                title=t(f"section.title_{part}", name=record.name),
                scene=record,
                domain=domain_of(record.domain_id),
                revision=shown,
                part=part,
                text=section_text(files[SCENARIO_FILE], part),
                scenario=scenario,
                facts=_facts(scenario),
            )
        # 卡片上的「自動化腳本」「斷言腳本」直接打開對應的檔案或段落
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
        )

    @router.get("/runs", include_in_schema=False)
    def runs(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        worker: Annotated[list[str] | None, Query()] = None,
    ) -> HTMLResponse:
        selected = {
            "scene": [item for item in scene or [] if item],
            "category": [item for item in category or [] if item],
            "status": [item for item in status or [] if item],
            "purpose": [item for item in purpose or [] if item],
            "worker": [item for item in worker or [] if item],
        }
        return page(
            "runs.html",
            page="runs",
            title=t("nav.runs"),
            runs=services.list_runs(
                scenes=selected["scene"],
                categories=selected["category"],
                statuses=selected["status"],
                purposes=selected["purpose"],
                workers=selected["worker"],
            ),
            filters=run_filters(
                scenes=services.list_scenes(include_archived=True),
                categories=services.run_categories(),
                selected=selected,
                locations=services.run_locations(),
            ),
            limit=200,
        )

    @router.get("/replay", include_in_schema=False)
    def replays(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        worker: Annotated[list[str] | None, Query()] = None,
    ) -> HTMLResponse:
        """運行回看（M12）：還有錄影的運行，篩選與運行報告相同；錄影設定也在這頁。"""
        selected = {
            "scene": [item for item in scene or [] if item],
            "category": [item for item in category or [] if item],
            "status": [item for item in status or [] if item],
            "purpose": [item for item in purpose or [] if item],
            "worker": [item for item in worker or [] if item],
        }
        return page(
            "replays.html",
            page="replay",
            title=t("nav.replay"),
            runs=services.list_runs(
                scenes=selected["scene"],
                categories=selected["category"],
                statuses=selected["status"],
                purposes=selected["purpose"],
                workers=selected["worker"],
                with_video=True,
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
            page="replay",
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
            login = services.revision_scenario(record.scene_id, record.revision_number).login
        except ServiceError:
            login = None
        return page(
            "run.html",
            page="runs",
            title=t("run.title", id=record.id),
            role=login.role if login is not None else None,
            run=record,
            revision=revision,
            result=services.run_result(run_id) if record.finished else None,
            files=services.storage.run_files(run_id) if record.finished else [],
            can_publish=can_publish,
            worker_wait=None if record.finished else services.worker_wait(run_id),
        )

    @router.get("/runs/{run_id}/files/{relative:path}", include_in_schema=False)
    def run_file(run_id: str, relative: str) -> Response:
        path = services.run_file(run_id, relative)
        if path.suffix == ".html" and relative != REPORT:
            media_type = "text/plain"  # 只有執行報告當成網頁顯示
        else:
            media_type = _TEXT_TYPES.get(path.suffix) or mimetypes.guess_type(path.name)[0]
        if media_type and media_type.startswith("text/"):
            media_type += "; charset=utf-8"
        return FileResponse(
            path,
            media_type=media_type,
            headers={
                # 錄影寫完就不會再變（M12）：讓瀏覽器拖曳時不必重抓同一段
                "Cache-Control": "private, max-age=86400"
                if relative in video_files({"file": relative})
                else "no-store",
                "X-Content-Type-Options": "nosniff",
                # 報告是單一 HTML 檔，只有內嵌樣式與同目錄的截圖
                "Content-Security-Policy": _REPORT_CSP,
            },
        )

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
    def workspace() -> RedirectResponse:
        """專案空間：到第一個專案；還沒有專案時到專案管理。"""
        items = projects.list_projects()
        return RedirectResponse(f"/projects/{items[0].id}" if items else "/projects", 303)

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
            page="playground",
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
        """一次序列的執行：每個節點的狀態、入參的值與來源、出參、那次執行的報告。"""
        record = workflows.get_run(run_id)
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
            page="playground",
            title=t("workflow_run.title", id=record.id),
            run=record,
            worker_wait=waiting,
            workflow_exists=exists and record.workflow_id is not None,
            project=owner,
            role=role,
            messages=workflow_messages(),
        )

    return router
