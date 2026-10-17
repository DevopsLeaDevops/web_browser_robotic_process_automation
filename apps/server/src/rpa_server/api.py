"""JSON API（/api）：管理介面的頁面與其他工具都透過這裡操作。

欄位名稱用 camelCase，與場景 DSL、result.json 一致。錯誤一律是
``{"error": {"code": …, "message": …, …}}``，HTTP 狀態碼：404 找不到、409 狀態衝突、422 內容有問題。

M4：登入角色與 Secrets（/api/roles、/api/secrets）、錄製（/api/recordings）、
調試工作階段（/api/scenes/{id}/debug、/api/debug/{工作階段}）、入參與出參的表單存檔
（/api/scenes/{id}/contract）、重新執行（/api/runs/{id}/rerun）。Secrets 的值只寫入、永遠不回傳。

M6：自由試驗場的序列（/api/workflows）與序列的執行（/api/workflow-runs）。

M9a：遠端 worker 的登記（/api/workers）與預設執行位置（/api/settings/default-target）；
執行、驗證、序列的執行可以指定執行位置 target（local、remote、any）。
Worker 自己用的 API 在 /worker-api/v1（worker_api.py）。
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from rpa_core.dsl import validate_text
from rpa_core.dsl.editing import SECTION_KEYS, section_text
from rpa_server.domain import Engine, Target
from rpa_server.errors import ServiceError
from rpa_server.i18n import t
from rpa_server.recordings import RecordingTarget
from rpa_server.services import Services, render_contract
from rpa_server.storage import SCENARIO_FILE

__all__ = ["api_router"]


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class DomainCreate(_Body):
    id: str = Field(max_length=64)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class DomainUpdate(_Body):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class SceneCreate(_Body):
    id: str = Field(max_length=64)
    name: str = Field(max_length=200)
    category: str | None = Field(default=None, max_length=100)
    domain_id: str | None = Field(default=None, max_length=64)


class SceneUpdate(_Body):
    base_url: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None
    domain_id: str | None = Field(default=None, max_length=64)


class ImportRequest(_Body):
    domain_id: str | None = Field(default=None, max_length=64)


class RevisionCreate(_Body):
    base_revision: int = Field(ge=0)
    files: dict[str, str]
    note: str | None = Field(default=None, max_length=500)


class RunCreate(_Body):
    inputs: dict[str, object] = Field(default_factory=dict[str, object])
    engine: Engine | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)
    headless: bool | None = None
    """無頭模式；沒指定時能顯示瀏覽器視窗就用有頭模式。"""
    target: Target | None = None
    """執行位置（M9a）；沒指定時用預設執行位置。"""


class ContractItem(_Body):
    """入參或出參表單的一列；previous 是改名前的名稱。"""

    name: str = Field(max_length=64)
    previous: str | None = Field(default=None, max_length=64)
    type: str = Field(default="string", max_length=20)
    description: str | None = Field(default=None, max_length=500)
    default: object = None
    enum: list[object] | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = Field(default=None, max_length=500)
    minimum: float | int | None = None
    maximum: float | int | None = None
    from_: str | None = Field(default=None, alias="from", max_length=500)


class ContractSave(_Body):
    base_revision: int = Field(ge=1)
    inputs: list[ContractItem] | None = None
    """None：入參不動（只編輯出參時）。"""
    outputs: list[ContractItem] | None = None
    note: str | None = Field(default=None, max_length=500)


class ContractRender(_Body):
    key: Literal["inputs", "outputs"]
    items: list[ContractItem] = Field(default_factory=list[ContractItem])


class ContractYaml(_Body):
    base_revision: int = Field(ge=1)
    inputs: str = Field(max_length=200_000)
    outputs: str = Field(max_length=200_000)
    note: str | None = Field(default=None, max_length=500)
    renames: dict[str, str] = Field(default_factory=dict[str, str])


class SectionSave(_Body):
    base_revision: int = Field(ge=1)
    text: str = Field(max_length=200_000)
    note: str | None = Field(default=None, max_length=500)


class RerunRequest(_Body):
    idempotency_key: str | None = Field(default=None, max_length=100)


class RoleBody(_Body):
    id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    login_url: str | None = Field(default=None, max_length=2000)
    check_url: str | None = Field(default=None, max_length=2000)
    check: str | dict[str, object] | None = None
    engine: str | None = Field(default=None, max_length=20)
    auto_login: str | None = Field(default=None, max_length=20_000)


class SecretValue(_Body):
    value: str = Field(max_length=10_000)


class TargetBody(_Body):
    scene_id: str = Field(max_length=64)
    new: bool = False
    name: str | None = Field(default=None, max_length=200)
    domain_id: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=100)
    mode: Literal["continue", "replace"] = "continue"
    """既有場景：continue 先執行既有步驟再接著錄製，replace 整份換成錄製的草稿。"""

    def target(self) -> RecordingTarget:
        return RecordingTarget(
            self.scene_id, self.new, self.name, self.domain_id, self.category, self.mode
        )


class RecordingStart(_Body):
    target: TargetBody
    url: str | None = Field(default=None, max_length=2000)
    engine: Engine = "chromium"
    role_id: str | None = Field(default=None, max_length=64)


class RecordingImport(RecordingStart):
    source: str = Field(max_length=1_000_000)


class DebugStart(_Body):
    revision: int | None = Field(default=None, ge=1)
    inputs: dict[str, object] | None = None
    engine: Engine | None = None
    headless: bool | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    restart: bool = False


class DebugStep(_Body):
    force: bool = False


class DebugLocate(_Body):
    locator: str | dict[str, object]


class DebugReload(_Body):
    revision: int = Field(ge=1)


class WorkflowCreate(_Body):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    definition: dict[str, object] | None = None
    """序列的定義（匯出的 JSON）；沒帶就是空的序列。"""


class WorkflowUpdate(_Body):
    base_version: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    definition: dict[str, object] | None = None


class WorkflowCheck(_Body):
    definition: dict[str, object]


class WorkflowRunCreate(_Body):
    engine: Engine | None = None
    headless: bool | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)
    target: Target | None = None


class WorkerCreate(_Body):
    id: str = Field(max_length=64)
    name: str | None = Field(default=None, max_length=100)


class WorkerUpdate(_Body):
    name: str | None = Field(default=None, max_length=100)
    disabled: bool | None = None


class TargetSetting(_Body):
    target: Target


class WorkflowRerun(_Body):
    resume: bool = False
    """True：從停下的節點繼續，沿用前面節點的出參；False：從頭再執行一次。"""
    idempotency_key: str | None = Field(default=None, max_length=100)


def _values(body: RoleBody) -> dict[str, object]:
    """只有使用者送來的欄位（PATCH 沒送的欄位不改）。"""
    sent = body.model_dump(by_alias=True, exclude_unset=True)
    return {key: value for key, value in sent.items() if key != "id"}


def api_router(services: Services) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------ 領域

    @router.get("/domains")
    def list_domains() -> dict[str, object]:
        return {"domains": [domain.to_json() for domain in services.list_domains()]}

    @router.post("/domains", status_code=201)
    def create_domain(body: DomainCreate) -> dict[str, object]:
        return services.create_domain(body.id, body.name, body.description).to_json()

    @router.get("/domains/{domain_id}")
    def get_domain(domain_id: str) -> dict[str, object]:
        domain = services.get_domain(domain_id)
        cards = services.scene_cards(domain_id)
        return {**domain.to_json(), "scenes": [card.to_json() for card in cards]}

    @router.patch("/domains/{domain_id}")
    def update_domain(domain_id: str, body: DomainUpdate) -> dict[str, object]:
        domain = services.update_domain(domain_id, name=body.name, description=body.description)
        return domain.to_json()

    @router.delete("/domains/{domain_id}")
    def delete_domain(domain_id: str) -> dict[str, object]:
        services.delete_domain(domain_id)
        return {"deleted": domain_id}

    # ------------------------------------------------------------ 場景

    @router.get("/scenes")
    def list_scenes(
        q: str = "", category: str | None = None, domain: str | None = None
    ) -> dict[str, object]:
        scenes = services.list_scenes(query=q, category=category, domain=domain)
        return {"scenes": [scene.to_json() for scene in scenes]}

    @router.post("/scenes", status_code=201)
    def create_scene(body: SceneCreate) -> dict[str, object]:
        scene = services.create_scene(body.id, body.name, body.category, domain_id=body.domain_id)
        return scene.to_json()

    @router.post("/scenes/import")
    def import_examples(body: ImportRequest | None = None) -> dict[str, object]:
        return services.import_examples(body.domain_id if body else None).to_json()

    @router.get("/scenes/{scene_id}")
    def get_scene(scene_id: str) -> dict[str, object]:
        scene = services.get_scene(scene_id)
        revisions = services.revisions(scene_id)
        try:
            needs = services.scene_needs(
                services.revision_scenario(scene_id, scene.latest_number)
            ).to_json()
        except ServiceError:
            needs = None
        return {
            **scene.to_json(),
            "revisions": [revision.to_json() for revision in revisions],
            "needs": needs,
        }

    @router.patch("/scenes/{scene_id}")
    def update_scene(scene_id: str, body: SceneUpdate) -> dict[str, object]:
        fields = body.model_fields_set
        scene = services.update_scene(
            scene_id,
            base_url=body.base_url if "base_url" in fields else None,
            clear_base_url="base_url" in fields and not body.base_url,
            archived=body.archived if "archived" in fields else None,
            domain_id=body.domain_id if "domain_id" in fields else None,
            clear_domain="domain_id" in fields and not body.domain_id,
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
            headless=body.headless,
            target=body.target,
        )
        return run.to_json()

    @router.post("/scenes/{scene_id}/revisions/{number}/publish")
    def publish_revision(scene_id: str, number: int) -> dict[str, object]:
        return services.publish(scene_id, number).to_json()

    @router.put("/scenes/{scene_id}/contract", status_code=201)
    def save_contract(scene_id: str, body: ContractSave) -> dict[str, object]:
        """入參與出參的表單：只改寫場景檔的 inputs、outputs 兩段，存成新版本。"""

        def items(rows: list[ContractItem] | None) -> list[dict[str, object]] | None:
            return None if rows is None else [row.model_dump(by_alias=True) for row in rows]

        revision = services.save_contract(
            scene_id,
            base=body.base_revision,
            inputs=items(body.inputs),
            outputs=items(body.outputs),
            note=body.note,
        )
        return revision.to_json()

    @router.get("/scenes/{scene_id}/contract-workspace")
    def contract_workspace(scene_id: str, revision: int | None = None) -> dict[str, object]:
        shown = services.get_revision(scene_id, revision)
        source = services.revision_files(scene_id, shown.number)[SCENARIO_FILE]
        scenario = services.revision_scenario(scene_id, shown.number)
        runs = services.list_runs(
            scenes=[scene_id], statuses=["passed"], revision=shown.number, limit=1
        )
        return {
            "revision": shown.number,
            "yaml": {key: section_text(source, key) for key in ("inputs", "outputs")},
            "script": scenario.script is not None,
            "sample": {"runId": runs[0].id, "values": runs[0].output} if runs else None,
        }

    @router.post("/scenes/{scene_id}/contract-yaml/preview")
    def preview_contract_yaml(scene_id: str, body: ContractYaml) -> dict[str, object]:
        files = services.contract_yaml_files(
            scene_id,
            base=body.base_revision,
            inputs=body.inputs,
            outputs=body.outputs,
            renames=body.renames,
        )
        scenario = validate_text(files[SCENARIO_FILE]).scenario
        assert scenario is not None
        return {
            key: [
                [name, spec.model_dump(mode="json", by_alias=True, exclude_none=True)]
                for name, spec in specs.items()
            ]
            for key, specs in (("inputs", scenario.inputs), ("outputs", scenario.outputs))
        }

    @router.put("/scenes/{scene_id}/contract-yaml", status_code=201)
    def save_contract_yaml(scene_id: str, body: ContractYaml) -> dict[str, object]:
        files = services.contract_yaml_files(
            scene_id,
            base=body.base_revision,
            inputs=body.inputs,
            outputs=body.outputs,
            renames=body.renames,
        )
        return services.save_revision(
            scene_id,
            base=body.base_revision,
            files=files,
            note=body.note or t("revision.note_contract"),
        ).to_json()

    @router.post("/contract/render")
    def contract_render(body: ContractRender) -> dict[str, object]:
        """入參或出參的表格 → 段落的 YAML 原文（表格切換成 YAML 時用；不存檔）。"""
        items = [row.model_dump(by_alias=True) for row in body.items]
        return {"key": body.key, "text": render_contract(body.key, items)}

    @router.get("/scenes/{scene_id}/sections/{key}")
    def section(scene_id: str, key: str, revision: int | None = None) -> dict[str, object]:
        """場景檔一段的原文（steps、verify、inputs、outputs）。"""
        shown = services.get_revision(scene_id, revision)
        text = services.revision_files(scene_id, shown.number)[SCENARIO_FILE]
        if key not in SECTION_KEYS:
            raise ServiceError(404, "section_unknown", t("error.section_unknown", key=key))
        return {"key": key, "revision": shown.number, "text": section_text(text, key)}

    @router.put("/scenes/{scene_id}/sections/{key}", status_code=201)
    def save_section(scene_id: str, key: str, body: SectionSave) -> dict[str, object]:
        """直接編輯一段的原文：只換掉這一段，存成新版本。"""
        revision = services.save_section(
            scene_id, key, base=body.base_revision, text=body.text, note=body.note
        )
        return revision.to_json()

    @router.post("/scenes/{scene_id}/sections/{key}/preview")
    def preview_section(scene_id: str, key: str, body: SectionSave) -> dict[str, object]:
        """換掉一段之後校驗（不存檔）；入參、出參回傳表格用的資料（原文切換回表格時用）。"""
        scenario = services.preview_section(scene_id, key, base=body.base_revision, text=body.text)
        specs = {"inputs": scenario.inputs, "outputs": scenario.outputs}.get(key, {})
        items = {
            name: spec.model_dump(mode="json", by_alias=True, exclude_none=True)
            for name, spec in specs.items()
        }
        return {"key": key, "ok": True, "items": items}

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
            headless=body.headless,
            target=body.target,
        )
        return run.to_json()

    @router.get("/runs")
    def list_runs(
        scene: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        worker: Annotated[list[str] | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> dict[str, object]:
        runs = services.list_runs(
            scenes=scene or [],
            categories=category or [],
            statuses=status or [],
            purposes=purpose or [],
            workers=worker or [],
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

    @router.post("/runs/{run_id}/rerun", status_code=202)
    def rerun(run_id: str, body: RerunRequest | None = None) -> dict[str, object]:
        """同樣的入參與選項再執行一次（例如需要登入的執行，登入之後）。"""
        key = body.idempotency_key if body is not None else None
        return services.rerun(run_id, idempotency_key=key).to_json()

    # ------------------------------------------------------------ 登入角色與 Secrets

    roles = services.roles

    @router.get("/roles")
    def list_roles() -> dict[str, object]:
        return {
            "roles": [role.to_json() for role in roles.list_roles()],
            "secrets": [info.to_json() for info in roles.list_secrets()],
            "display": services.display,
        }

    @router.post("/roles", status_code=201)
    def create_role(body: RoleBody) -> dict[str, object]:
        return roles.create_role(body.id or "", _values(body)).to_json()

    @router.get("/roles/{role_id}")
    def get_role(role_id: str) -> dict[str, object]:
        return roles.get_role(role_id).to_json()

    @router.patch("/roles/{role_id}")
    def update_role(role_id: str, body: RoleBody) -> dict[str, object]:
        return roles.update_role(role_id, _values(body)).to_json()

    @router.delete("/roles/{role_id}")
    def delete_role(role_id: str) -> dict[str, object]:
        roles.delete_role(role_id)
        return {"deleted": role_id}

    @router.delete("/roles/{role_id}/state")
    def clear_role_state(role_id: str) -> dict[str, object]:
        """登出：刪除這個角色的登入狀態。"""
        return roles.clear_state(role_id).to_json()

    @router.post("/roles/{role_id}/check", status_code=202)
    def check_role(role_id: str) -> dict[str, object]:
        return roles.check(role_id).to_json()

    @router.post("/roles/{role_id}/login", status_code=202)
    def start_login(role_id: str) -> dict[str, object]:
        """人工登入：在執行 Portal 的電腦上開瀏覽器視窗到登入網址。"""
        return roles.start_login(role_id).to_json()

    @router.post("/roles/{role_id}/login/finish", status_code=202)
    def finish_login(role_id: str) -> dict[str, object]:
        return roles.finish_login(role_id).to_json()

    @router.post("/roles/{role_id}/login/cancel")
    def cancel_login(role_id: str) -> dict[str, object]:
        roles.cancel_login(role_id)
        return roles.get_role(role_id).to_json()

    @router.get("/secrets")
    def list_secrets() -> dict[str, object]:
        return {"secrets": [info.to_json() for info in roles.list_secrets()]}

    @router.put("/secrets/{name}")
    def set_secret(name: str, body: SecretValue) -> dict[str, object]:
        return roles.set_secret(name, body.value).to_json()

    @router.delete("/secrets/{name}")
    def delete_secret(name: str) -> dict[str, object]:
        roles.delete_secret(name)
        return {"deleted": name}

    # ------------------------------------------------------------ 錄製

    recordings = services.recordings

    @router.get("/recordings")
    def list_recordings() -> dict[str, object]:
        return {
            "recordings": [item.to_json() for item in recordings.list_recordings()],
            "display": services.display,
        }

    @router.post("/recordings", status_code=202)
    def start_recording(body: RecordingStart) -> dict[str, object]:
        """在執行 Portal 的電腦上開瀏覽器錄製；關掉視窗後轉換成草稿。"""
        record = recordings.start(
            body.target.target(), url=body.url, engine=body.engine, role_id=body.role_id
        )
        return record.to_json()

    @router.post("/recordings/import", status_code=201)
    def import_recording(body: RecordingImport) -> dict[str, object]:
        """貼上 codegen 的原始錄製稿，直接轉換成草稿。"""
        record = recordings.import_source(
            body.source,
            body.target.target(),
            url=body.url,
            engine=body.engine,
            role_id=body.role_id,
        )
        return {**record.to_json(), "files": recordings.files(record.id)}

    @router.get("/recordings/{recording_id}")
    def get_recording(recording_id: str) -> dict[str, object]:
        record = recordings.get_recording(recording_id)
        return {**record.to_json(), "files": recordings.files(recording_id)}

    @router.post("/recordings/{recording_id}/cancel")
    def cancel_recording(recording_id: str) -> dict[str, object]:
        return recordings.cancel(recording_id).to_json()

    # ------------------------------------------------------------ 調試工作階段

    debug = services.debug

    @router.post("/scenes/{scene_id}/debug", status_code=202)
    def start_debug(scene_id: str, body: DebugStart) -> dict[str, object]:
        """開始調試；這個場景已經有進行中的工作階段時回傳它（restart 為 true 時重新開始）。"""
        session = debug.start(
            scene_id,
            revision=body.revision,
            inputs=body.inputs,
            engine=body.engine,
            headless=body.headless,
            base_url=body.base_url,
            restart=body.restart,
        )
        return session.to_json()

    @router.get("/debug/{session_id}")
    def get_debug(session_id: str) -> dict[str, object]:
        return debug.get(session_id).to_json()

    @router.post("/debug/{session_id}/steps/{index}")
    def debug_step(session_id: str, index: int, body: DebugStep | None = None) -> dict[str, object]:
        force = body.force if body is not None else False
        return debug.run_step(session_id, index, force=force).to_json()

    @router.post("/debug/{session_id}/run-to/{index}")
    def debug_run_to(session_id: str, index: int) -> dict[str, object]:
        return debug.run_to(session_id, index).to_json()

    @router.post("/debug/{session_id}/locate")
    def debug_locate(session_id: str, body: DebugLocate) -> dict[str, object]:
        return debug.locate(session_id, body.locator).to_json()

    @router.post("/debug/{session_id}/screenshot")
    def debug_screenshot(session_id: str) -> dict[str, object]:
        return debug.screenshot(session_id).to_json()

    @router.post("/debug/{session_id}/reset")
    def debug_reset(session_id: str) -> dict[str, object]:
        return debug.reset(session_id).to_json()

    @router.post("/debug/{session_id}/reload")
    def debug_reload(session_id: str, body: DebugReload) -> dict[str, object]:
        return debug.reload(session_id, body.revision).to_json()

    @router.delete("/debug/{session_id}")
    def close_debug(session_id: str) -> dict[str, object]:
        debug.close(session_id)
        return {"closed": session_id}

    # ------------------------------------------------------------ 自由試驗場（M6）

    workflows = services.workflows

    @router.get("/workflows")
    def list_workflows() -> dict[str, object]:
        return {"workflows": [item.to_json() for item in workflows.list_workflows()]}

    @router.post("/workflows", status_code=201)
    def create_workflow(body: WorkflowCreate) -> dict[str, object]:
        """新增序列；帶 definition 就是匯入。"""
        return workflows.create_workflow(body.name, body.description, body.definition).to_json()

    @router.get("/workflows/library")
    def workflow_library() -> dict[str, object]:
        """場景庫：發布過的場景版本與它們的入參、出參（編輯序列用）。"""
        return {"scenes": workflows.library(), "display": services.display}

    @router.post("/workflows/check")
    def check_workflow(body: WorkflowCheck) -> dict[str, object]:
        """檢查一份定義（不存檔）：格式、場景與版本、綁定、必填入參。"""
        _, problems = workflows.parse(body.definition)
        return {"ok": not problems, "problems": [problem.to_json() for problem in problems]}

    @router.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: int) -> dict[str, object]:
        record = workflows.get_workflow(workflow_id)
        runs = workflows.list_runs(workflow_id=workflow_id, limit=10)
        return {**record.to_json(), "runs": [run.to_json() for run in runs]}

    @router.put("/workflows/{workflow_id}")
    def update_workflow(workflow_id: int, body: WorkflowUpdate) -> dict[str, object]:
        record = workflows.update_workflow(
            workflow_id,
            base_version=body.base_version,
            name=body.name,
            description=body.description,
            definition=body.definition,
        )
        return record.to_json()

    @router.delete("/workflows/{workflow_id}")
    def delete_workflow(workflow_id: int) -> dict[str, object]:
        workflows.delete_workflow(workflow_id)
        return {"deleted": workflow_id}

    @router.post("/workflows/{workflow_id}/runs", status_code=202)
    def run_workflow(workflow_id: int, body: WorkflowRunCreate) -> dict[str, object]:
        """執行序列：有問題時 422（problems 列出每個問題），沒有問題就排入第一個節點。"""
        record = workflows.start(
            workflow_id,
            engine=body.engine,
            headless=body.headless,
            idempotency_key=body.idempotency_key,
            target=body.target,
        )
        return record.to_json()

    # ------------------------------------------------------------ 遠端 worker（M9a）

    hub = services.workers

    def worker_list() -> dict[str, object]:
        return {
            "workers": [item.to_json() for item in hub.list_workers()],
            "defaultTarget": hub.default_target(),
            "localWorker": services.local_worker,
            "fingerprint": hub.fingerprint,
        }

    @router.get("/workers")
    def list_workers() -> dict[str, object]:
        return worker_list()

    @router.post("/workers", status_code=201)
    def create_worker(body: WorkerCreate) -> dict[str, object]:
        """登記 worker；回應裡的 token 只有這一次拿得到。"""
        record, token = hub.create_worker(body.id, body.name)
        return {"worker": record.to_json(), "token": token}

    @router.get("/workers/{worker_id}")
    def get_worker(worker_id: str) -> dict[str, object]:
        return hub.get_worker(worker_id).to_json()

    @router.patch("/workers/{worker_id}")
    def update_worker(worker_id: str, body: WorkerUpdate) -> dict[str, object]:
        return hub.update_worker(worker_id, name=body.name, disabled=body.disabled).to_json()

    @router.post("/workers/{worker_id}/token")
    def rotate_worker_token(worker_id: str) -> dict[str, object]:
        record, token = hub.rotate_token(worker_id)
        return {"worker": record.to_json(), "token": token}

    @router.post("/workers/{worker_id}/invite")
    def invite_worker(worker_id: str) -> dict[str, object]:
        """產生裝置邀請（M10.1）：舊權杖立刻失效；回應裡的邀請代碼只有這一次拿得到。"""
        return services.invite_device(worker_id)

    @router.delete("/workers/{worker_id}")
    def delete_worker(worker_id: str) -> dict[str, object]:
        hub.delete_worker(worker_id)
        return {"deleted": worker_id}

    @router.put("/settings/default-target")
    def set_default_target(body: TargetSetting) -> dict[str, object]:
        hub.set_default_target(body.target)
        return worker_list()

    @router.get("/workflow-runs")
    def list_workflow_runs(
        workflow: int | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, object]:
        runs = workflows.list_runs(workflow_id=workflow, limit=limit)
        return {"runs": [run.to_json() for run in runs]}

    @router.get("/workflow-runs/{run_id}")
    def get_workflow_run(run_id: str) -> dict[str, object]:
        return workflows.get_run(run_id).to_json()

    @router.post("/workflow-runs/{run_id}/cancel", status_code=202)
    def cancel_workflow_run(run_id: str) -> dict[str, object]:
        return workflows.cancel(run_id).to_json()

    @router.post("/workflow-runs/{run_id}/rerun", status_code=202)
    def rerun_workflow(run_id: str, body: WorkflowRerun | None = None) -> dict[str, object]:
        """再執行一次：resume 為 true 時從停下的節點繼續（沿用前面節點的出參）。"""
        body = body or WorkflowRerun()
        record = workflows.rerun(run_id, resume=body.resume, idempotency_key=body.idempotency_key)
        return record.to_json()

    return router
