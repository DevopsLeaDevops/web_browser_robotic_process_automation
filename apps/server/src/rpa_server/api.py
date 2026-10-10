"""JSON API（/api）：管理介面的頁面與其他工具都透過這裡操作。

欄位名稱用 camelCase，與場景 DSL、result.json 一致。錯誤一律是
``{"error": {"code": …, "message": …, …}}``，HTTP 狀態碼：404 找不到、409 狀態衝突、422 內容有問題。
"""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from rpa_server.domain import Engine
from rpa_server.services import Services

__all__ = ["api_router"]


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SceneCreate(_Body):
    id: str = Field(max_length=64)
    name: str = Field(max_length=200)
    category: str | None = Field(default=None, max_length=100)


class SceneUpdate(_Body):
    base_url: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None


class RevisionCreate(_Body):
    base_revision: int = Field(ge=0)
    files: dict[str, str]
    note: str | None = Field(default=None, max_length=500)


class RunCreate(_Body):
    inputs: dict[str, object] = Field(default_factory=dict[str, object])
    engine: Engine | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)


def api_router(services: Services) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------ 場景

    @router.get("/scenes")
    def list_scenes(q: str = "", category: str | None = None) -> dict[str, object]:
        scenes = services.list_scenes(query=q, category=category)
        return {"scenes": [scene.to_json() for scene in scenes]}

    @router.post("/scenes", status_code=201)
    def create_scene(body: SceneCreate) -> dict[str, object]:
        return services.create_scene(body.id, body.name, body.category).to_json()

    @router.post("/scenes/import")
    def import_examples() -> dict[str, object]:
        return services.import_examples().to_json()

    @router.get("/scenes/{scene_id}")
    def get_scene(scene_id: str) -> dict[str, object]:
        scene = services.get_scene(scene_id)
        revisions = services.revisions(scene_id)
        return {**scene.to_json(), "revisions": [revision.to_json() for revision in revisions]}

    @router.patch("/scenes/{scene_id}")
    def update_scene(scene_id: str, body: SceneUpdate) -> dict[str, object]:
        fields = body.model_fields_set
        scene = services.update_scene(
            scene_id,
            base_url=body.base_url if "base_url" in fields else None,
            clear_base_url="base_url" in fields and not body.base_url,
            archived=body.archived if "archived" in fields else None,
        )
        return scene.to_json()

    # ------------------------------------------------------------ 版本

    @router.get("/scenes/{scene_id}/revisions/{number}")
    def get_revision(scene_id: str, number: int) -> dict[str, object]:
        revision = services.get_revision(scene_id, number)
        files = services.revision_files(scene_id, number)
        return {**revision.to_json(), "files": files}

    @router.post("/scenes/{scene_id}/revisions", status_code=201)
    def save_revision(scene_id: str, body: RevisionCreate) -> dict[str, object]:
        revision = services.save_revision(
            scene_id, base=body.base_revision, files=body.files, note=body.note
        )
        return revision.to_json()

    @router.post("/scenes/{scene_id}/revisions/{number}/validate", status_code=202)
    def validate_revision(scene_id: str, number: int, body: RunCreate) -> dict[str, object]:
        run = services.request_run(
            scene_id,
            purpose="validation",
            number=number,
            inputs=body.inputs,
            engine=body.engine,
            base_url=body.base_url,
            idempotency_key=body.idempotency_key,
        )
        return run.to_json()

    @router.post("/scenes/{scene_id}/revisions/{number}/publish")
    def publish_revision(scene_id: str, number: int) -> dict[str, object]:
        return services.publish(scene_id, number).to_json()

    # ------------------------------------------------------------ 執行

    @router.post("/scenes/{scene_id}/runs", status_code=202)
    def run_scene(scene_id: str, body: RunCreate) -> dict[str, object]:
        run = services.request_run(
            scene_id,
            purpose="execution",
            inputs=body.inputs,
            engine=body.engine,
            base_url=body.base_url,
            idempotency_key=body.idempotency_key,
        )
        return run.to_json()

    @router.get("/runs")
    def list_runs(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> dict[str, object]:
        runs = services.list_runs(
            scenes=scene or [],
            categories=category or [],
            statuses=status or [],
            purposes=purpose or [],
            limit=limit,
        )
        return {"runs": [run.to_json() for run in runs]}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        run = services.get_run(run_id)
        return {
            **run.to_json(),
            "result": services.run_result(run_id) if run.finished else None,
            "files": services.storage.run_files(run_id) if run.finished else [],
        }

    @router.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str) -> dict[str, object]:
        return services.cancel_run(run_id).to_json()

    return router
