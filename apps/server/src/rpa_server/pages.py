"""HTML 頁面：取資料、交給樣板（render.py）。寫入操作由頁面上的 JavaScript 呼叫 /api。"""

import mimetypes
from typing import Annotated, Final
from urllib.parse import urlsplit

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from rpa_core.i18n import parse_locale
from rpa_runner.files import REPORT
from rpa_server.domain import ENGINES, PURPOSES, RUN_STATUSES, Purpose
from rpa_server.i18n import t
from rpa_server.middleware import LANG_COOKIE
from rpa_server.render import render
from rpa_server.services import ServiceError, Services

__all__ = ["page_router"]

_TEXT_TYPES: Final = {".log": "text/plain", ".py": "text/plain", ".yaml": "text/plain"}
_RECENT_RUNS: Final = 10
_REPORT_CSP: Final = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content, headers={"Cache-Control": "no-store"})


def page_router(services: Services) -> APIRouter:
    router = APIRouter()

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
    def scenes(q: str = "", category: str = "") -> HTMLResponse:
        return _html(
            render(
                "scenes.html",
                page="scenes",
                title=t("nav.scenes"),
                scenes=services.list_scenes(query=q, category=category or None),
                categories=services.categories(),
                stats=services.stats(),
                query=q,
                category=category,
                can_import=services.examples_dir is not None and services.examples_dir.is_dir(),
            )
        )

    @router.get("/scenes/{scene_id}", include_in_schema=False)
    def scene(scene_id: str) -> HTMLResponse:
        record = services.get_scene(scene_id)
        try:
            scenario = services.revision_scenario(scene_id, record.latest_number)
        except ServiceError:
            scenario = None
        return _html(
            render(
                "scene.html",
                page="scenes",
                title=record.name,
                scene=record,
                revisions=services.revisions(scene_id),
                scenario=scenario,
                default_base_url=scenario.browser.base_url if scenario else None,
                runs=services.list_runs(scenes=[scene_id], limit=_RECENT_RUNS),
            )
        )

    @router.get("/scenes/{scene_id}/edit", include_in_schema=False)
    def edit(scene_id: str, revision: int | None = None) -> HTMLResponse:
        record = services.get_scene(scene_id)
        shown = services.get_revision(scene_id, revision)
        return _html(
            render(
                "edit.html",
                page="scenes",
                title=t("edit.title", name=record.name),
                scene=record,
                revision=shown,
                files=services.revision_files(scene_id, shown.number),
            )
        )

    @router.get("/scenes/{scene_id}/run", include_in_schema=False)
    def run_form(
        scene_id: str, purpose: Purpose = "execution", revision: int | None = None
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
        return _html(
            render(
                "run_form.html",
                page="scenes",
                title=t(f"run_form.title_{purpose}", name=record.name, number=shown.number),
                scene=record,
                revision=shown,
                scenario=scenario,
                purpose=purpose,
                defaults=defaults,
                engines=ENGINES,
                base_url=record.base_url or scenario.browser.base_url,
            )
        )

    @router.get("/runs", include_in_schema=False)
    def runs(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
    ) -> HTMLResponse:
        selected = {
            "scene": [item for item in scene or [] if item],
            "category": [item for item in category or [] if item],
            "status": [item for item in status or [] if item],
            "purpose": [item for item in purpose or [] if item],
        }
        return _html(
            render(
                "runs.html",
                page="runs",
                title=t("nav.runs"),
                runs=services.list_runs(
                    scenes=selected["scene"],
                    categories=selected["category"],
                    statuses=selected["status"],
                    purposes=selected["purpose"],
                ),
                scenes=services.list_scenes(include_archived=True),
                categories=services.run_categories(),
                statuses=RUN_STATUSES,
                purposes=PURPOSES,
                selected=selected,
                limit=200,
            )
        )

    @router.get("/runs/{run_id}", include_in_schema=False)
    def run(run_id: str) -> HTMLResponse:
        record = services.get_run(run_id)
        revision = services.get_revision(record.scene_id, record.revision_number)
        can_publish = (
            record.purpose == "validation"
            and record.status == "passed"
            and revision.status == "passed"
            and not revision.published
            and record.scenario_hash == revision.content_hash
        )
        return _html(
            render(
                "run.html",
                page="runs",
                title=t("run.title", id=record.id),
                run=record,
                revision=revision,
                result=services.run_result(run_id) if record.finished else None,
                files=services.storage.run_files(run_id) if record.finished else [],
                can_publish=can_publish,
            )
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
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                # 報告是單一 HTML 檔，只有內嵌樣式與同目錄的截圖
                "Content-Security-Policy": _REPORT_CSP,
            },
        )

    @router.get("/recording", include_in_schema=False)
    def recording() -> HTMLResponse:
        return _html(
            render("placeholder.html", page="recording", title=t("nav.recording"), milestone="M4")
        )

    @router.get("/playground", include_in_schema=False)
    def playground() -> HTMLResponse:
        return _html(
            render("placeholder.html", page="playground", title=t("nav.playground"), milestone="M6")
        )

    return router
