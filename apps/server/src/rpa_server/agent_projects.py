"""對外 Agent API 的專案（/agent-api/v1，M14）：專案空間裡的專案與組合場景。

- **專案**（``/projects``）：列出、新增、改名稱與說明；刪除與排序只在管理後台。
- **組合場景**（``/composites/{代號}``）：用代號指定。在專案裡建立、存新版本（baseRevision
  不是最新時 409 ``stale_workflow``）、移到其他專案、檢查定義、驗證、發布、執行。定義的格式同
  Portal 匯出的 JSON（:mod:`rpa_core.workflow`），節點只能用發布過的場景版本
  （``/composites/library``）。
- **組合場景的執行**（``/composite-runs``）：每個節點的狀態與那次運行；節點的步驟與產物用
  ``/runs/{id}``。專案的執行（``POST /projects/{id}/runs``）是把專案裡的組合場景逐一排入。
- **權限**：projects:read、projects:write、projects:publish；驗證、執行與讀運行沿用 runs:validate、
  runs:execute、runs:read。組合場景要在可用的專案裡（不屬於任何專案的不給 Agent），放的領域與節點
  用到的場景的領域也要可用；不能用的組合場景與執行一律當成不存在（404）。
- **匯總報告**（``/composite-runs/{id}/report``，2026-10-27）：整次組合運行的結論、數字、
  時間軸與每個節點的入參出參、步驟、斷言；截圖與節點報告的網址換成本 API 的路徑
  （沒有 page_content 權限時是 null）。
- 回應另外帶 ``portalPath``：人在 Portal 看同一筆資料的路徑（Agent 寫測試報告時附上）。
"""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query
from pydantic import Field

from rpa_core.workflow import Workflow, parse_workflow
from rpa_server.agent_api import (
    AGENT_PREFIX,
    AgentBody,
    AgentTools,
    Executor,
    Placer,
    ProjectPublisher,
    ProjectReader,
    ProjectWriter,
    RunReader,
    Validator,
    forbidden,
)
from rpa_server.agents import ApiClientRecord
from rpa_server.composite_report import report_json
from rpa_server.domain import (
    Engine,
    ProjectRecord,
    Target,
    WorkflowRecord,
    WorkflowRunRecord,
)
from rpa_server.errors import ServiceError, conflict, not_found
from rpa_server.i18n import t
from rpa_server.services import Services

__all__ = ["project_routes"]

_ACTIVE_NODES = frozenset({"queued", "running"})
_DONE_NODES = frozenset(
    {"passed", "reused", "failed", "timed_out", "cancelled", "needs_login", "skipped"}
)


class ProjectCreate(AgentBody):
    id: str = Field(max_length=64)
    """代號：用在網址，建立後不能改（規則同領域）。"""
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)


class ProjectUpdate(AgentBody):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class CompositeCreate(AgentBody):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    code: str | None = Field(default=None, max_length=64)
    """英數代號；沒給時自動取 wf-<數字>。"""
    domain_id: str | None = Field(default=None, max_length=64)
    """放在哪個領域資料夾；沒給時放「組合場景」領域。"""
    definition: dict[str, object] | None = None
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=100)


class CompositeSave(AgentBody):
    base_revision: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    definition: dict[str, object] | None = None
    """和最新版本不同時存成新的版本；名稱與說明不分版本。"""
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=100)


class CompositeMove(AgentBody):
    project_id: str = Field(max_length=64)


class DefinitionCheck(AgentBody):
    definition: dict[str, object]


class CompositeRunBody(AgentBody):
    engine: Engine | None = None
    """沒給時每個節點用場景自己的瀏覽器。"""
    headless: bool | None = None
    target: Target | None = None
    worker_id: str | None = Field(default=None, max_length=64)
    """從第一個節點起就給哪台 Worker（local 是伺服器本機）。"""
    idempotency_key: str | None = Field(default=None, max_length=100)


class ProjectRunBody(CompositeRunBody):
    purpose: Literal["validation", "execution"] = "execution"
    """execution 跑每個組合場景發布的版本；validation 驗證最新版本。"""
    composites: list[str] | None = Field(default=None, max_length=200)
    """只跑這些代號；沒給時是專案裡全部沒有封存的組合場景。"""


class CompositeRerunBody(AgentBody):
    resume: bool = False
    """True：從停下的節點繼續，沿用前面節點的出參；False：從頭再執行一次。"""
    idempotency_key: str | None = Field(default=None, max_length=100)


def project_routes(services: Services, tools: AgentTools) -> APIRouter:
    """專案、組合場景與組合場景的執行（掛在 /agent-api/v1 的子應用上）。"""
    router = APIRouter()
    projects = services.projects
    workflows = services.workflows
    agents = services.agents

    # ------------------------------------------------------------ 權限與轉換

    def project_for(client: ApiClientRecord, project_id: str) -> ProjectRecord:
        project = projects.get_project(project_id)
        if not client.project_allowed(project.id):
            raise forbidden("project_forbidden", t("error.agent_project_forbidden", id=project_id))
        return project

    def visible(client: ApiClientRecord, record: WorkflowRecord) -> bool:
        return client.project_allowed(record.project_id) and client.domain_allowed(record.domain_id)

    def composite_for(client: ApiClientRecord, code: str) -> WorkflowRecord:
        record = workflows.get_workflow(workflows.find(code))
        if not visible(client, record):
            raise not_found("workflow_not_found", t("error.workflow_not_found", id=code))
        return record

    def scenes_check(client: ApiClientRecord, definition: object) -> None:
        """節點用到的場景都要在可用的領域裡；格式不對或場景不存在的交給檢查回報。"""
        workflow = definition if isinstance(definition, Workflow) else parse_workflow(definition)[0]
        if workflow is None or client.policy.domains is None:
            return
        blocked: list[str] = []
        for scene_id in dict.fromkeys(node.scene_id for node in workflow.nodes):
            try:
                domain_id = services.get_scene(scene_id).domain_id
            except ServiceError:
                continue
            if not client.domain_allowed(domain_id):
                blocked.append(scene_id)
        if blocked:
            raise forbidden(
                "composite_scenes_forbidden",
                t("error.agent_composite_scenes_forbidden", scenes=", ".join(blocked)),
                scenes=blocked,
            )

    def project_json(project: ProjectRecord) -> dict[str, object]:
        return {**project.to_json(), "portalPath": f"/projects/{project.id}"}

    def progress(run: WorkflowRunRecord) -> dict[str, object]:
        current = next((node.id for node in run.nodes if node.status in _ACTIVE_NODES), None)
        return {
            "total": len(run.nodes),
            "done": sum(node.status in _DONE_NODES for node in run.nodes),
            "passed": run.passed_count,
            "current": current,
        }

    def run_json(client: ApiClientRecord, run: WorkflowRunRecord) -> dict[str, object]:
        data = run.to_json()
        for state, node in zip(
            run.nodes, cast("list[dict[str, object]]", data["nodes"]), strict=True
        ):
            node["run"] = tools.run_json(client, state.run) if state.run is not None else None
        data["progress"] = progress(run)
        data["portalPath"] = f"/playground/runs/{run.id}"
        data["reportUrl"] = f"{AGENT_PREFIX}/composite-runs/{run.id}/report"
        return data

    def report_for(client: ApiClientRecord, report: dict[str, object]) -> dict[str, object]:
        """匯總報告給 Agent：Portal 的網址換成本 API 的路徑；沒有 page_content 權限時
        不給截圖與報告。"""
        data = report_json(report)
        content = client.policy.page_content
        for node in cast("list[dict[str, object]]", data["nodes"]):
            run_id = node.get("runId")
            files = f"{AGENT_PREFIX}/runs/{run_id}/files/"
            shot, report_url = node.get("screenshot"), node.get("reportUrl")
            node["screenshotUrl"] = f"{files}{shot}" if content and run_id and shot else None
            node["reportUrl"] = f"{files}report.html" if content and run_id and report_url else None
            node["portalPath"] = node.pop("runUrl", None)
            for key in ("replayUrl", "reusedUrl"):
                node.pop(key, None)
        data["portalPath"] = f"/playground/runs/{report['id']}"
        return data

    def summary(record: WorkflowRecord) -> dict[str, object]:
        last = record.last_run
        return {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "description": record.description,
            "projectId": record.project_id,
            "domainId": record.domain_id,
            "latestRevision": record.version,
            "publishedRevision": record.published_number,
            "archived": record.archived,
            "dependency": record.dependency,
            "problems": len(record.problems),
            "lastRun": (
                {
                    "id": last.id,
                    "status": last.status,
                    "purpose": last.purpose,
                    "revision": last.workflow_version,
                    "createdAt": last.to_json()["createdAt"],
                    "finishedAt": last.to_json()["finishedAt"],
                }
                if last is not None
                else None
            ),
            "portalPath": f"/playground/{record.id}",
        }

    def composite_json(client: ApiClientRecord, record: WorkflowRecord) -> dict[str, object]:
        data = record.to_json()
        last = record.last_run
        data["lastRun"] = run_json(client, last) if last is not None else None
        data["portalPath"] = f"/playground/{record.id}"
        return data

    def run_for(client: ApiClientRecord, run_id: str) -> WorkflowRunRecord:
        """看得到的組合場景執行：組合場景在可用的專案與領域；組合場景刪掉後只看得到自己的。"""
        run = workflows.get_run(run_id)
        try:
            record = (
                workflows.get_workflow(run.workflow_id) if run.workflow_id is not None else None
            )
        except ServiceError:
            record = None
        shown = visible(client, record) if record is not None else run.client_id == client.id
        if not shown:
            raise not_found("workflow_run_not_found", t("error.workflow_run_not_found", id=run_id))
        return run

    def start(
        client: ApiClientRecord,
        record: WorkflowRecord,
        body: CompositeRunBody,
        *,
        purpose: Literal["validation", "execution"],
        revision: int | None = None,
        key: str | None = None,
    ) -> WorkflowRunRecord:
        existing = workflows.by_key(key)
        if existing is not None:
            return existing
        number = record.published_number if purpose == "execution" else revision or record.version
        if number is not None:
            scenes_check(client, workflows.revision_workflow(record.code, number))
        tools.run_limit(client)
        target, worker = tools.placement(client, body.target, body.worker_id)
        return workflows.start(
            record.id,
            engine=body.engine,
            headless=body.headless,
            idempotency_key=key,
            target=target,
            purpose=purpose,
            revision=revision,
            worker_id=worker,
            client_id=client.id,
        )

    # ------------------------------------------------------------ 專案

    @router.get("/projects")
    def list_projects(client: ProjectReader) -> dict[str, object]:
        """可用的專案，依專案管理的順序。"""
        items = [p for p in projects.list_projects() if client.project_allowed(p.id)]
        return {"projects": [project_json(project) for project in items]}

    @router.post("/projects", status_code=201)
    def create_project(client: ProjectWriter, body: ProjectCreate) -> dict[str, object]:
        """新增專案（排在最後）；限定了可用專案的金鑰不能新增。"""
        if client.policy.projects is not None:
            raise forbidden("project_create_forbidden", t("error.agent_project_create_forbidden"))
        remembered = agents.recall(client.id, "project", body.idempotency_key)
        if remembered is not None:
            return remembered
        data = project_json(projects.create_project(body.id, body.name, body.description))
        agents.remember(client.id, "project", body.idempotency_key, data)
        return data

    @router.get("/projects/{project_id}")
    def get_project(client: ProjectReader, project_id: str) -> dict[str, object]:
        """專案與它的組合場景（摘要；完整的定義用 ``/composites/{代號}``）。"""
        project = project_for(client, project_id)
        items = workflows.list_workflows(project_id=project.id)
        return {
            **project_json(project),
            "composites": [
                summary(item) for item in items if client.domain_allowed(item.domain_id)
            ],
        }

    @router.patch("/projects/{project_id}")
    def update_project(
        client: ProjectWriter, project_id: str, body: ProjectUpdate
    ) -> dict[str, object]:
        project_for(client, project_id)
        project = projects.update_project(project_id, name=body.name, description=body.description)
        return project_json(project)

    @router.post("/projects/{project_id}/composites", status_code=201)
    def create_composite(
        client: ProjectWriter, project_id: str, body: CompositeCreate
    ) -> dict[str, object]:
        """在專案裡建立組合場景；帶定義時那就是第 1 版。冪等鍵用過時回傳上次建立的。"""
        project_for(client, project_id)
        kind = f"composite:{project_id}"
        remembered = agents.recall(client.id, kind, body.idempotency_key)
        if remembered is not None:
            return remembered
        domain_id = body.domain_id or services.composites_domain()
        tools.domain_check(client, domain_id)
        if body.definition is not None:
            scenes_check(client, body.definition)
        record = workflows.create_workflow(
            body.name,
            body.description,
            body.definition,
            code=body.code,
            domain_id=domain_id,
            project_id=project_id,
            note=(
                tools.note(client, body.note, "")
                if body.note
                else t("agent.note_created", name=client.name)
            ),
        )
        data = composite_json(client, record)
        agents.remember(client.id, kind, body.idempotency_key, data)
        return data

    # ------------------------------------------------------------ 組合場景

    @router.get("/composites")
    def list_composites(client: ProjectReader, project: str | None = None) -> dict[str, object]:
        """看得到的組合場景（摘要）；project 只列那個專案的。"""
        if project is not None:
            project_for(client, project)
        items = workflows.list_workflows(project_id=project)
        return {"composites": [summary(item) for item in items if visible(client, item)]}

    @router.get("/composites/library")
    def library(client: ProjectReader) -> dict[str, object]:
        """場景庫：可用領域裡發布過的場景版本，與每個版本的入參、出參、登入角色。"""
        scenes = [
            entry
            for entry in workflows.library()
            if client.domain_allowed(cast("str | None", entry.get("domainId")))
        ]
        return {"scenes": scenes}

    @router.post("/composites/check")
    def check_definition(client: ProjectReader, body: DefinitionCheck) -> dict[str, object]:
        """不存檔檢查定義：格式、場景與版本、依賴、綁定、必填入參。"""
        scenes_check(client, body.definition)
        _, problems = workflows.parse(body.definition)
        return {"ok": not problems, "problems": [problem.to_json() for problem in problems]}

    @router.get("/composites/{code}")
    def get_composite(client: ProjectReader, code: str) -> dict[str, object]:
        """定義、檢查發現的問題、版本、驗證紀錄、依賴與最近的執行。"""
        record = composite_for(client, code)
        runs = workflows.list_runs(workflow_id=record.id, limit=10)
        return {
            **composite_json(client, record),
            "revisions": [item.to_json() for item in workflows.revisions(record.id)],
            "verifications": [item.to_json() for item in workflows.verifications(record.id)],
            "dependencies": [item.to_json() for item in workflows.dependencies(record.id)],
            "runs": [run_json(client, run) for run in runs],
        }

    @router.put("/composites/{code}")
    def save_composite(client: ProjectWriter, code: str, body: CompositeSave) -> dict[str, object]:
        """存檔：定義不同時存成新版本；baseRevision 不是最新時 409 ``stale_workflow``。"""
        record = composite_for(client, code)
        kind = f"composite-save:{code}"
        remembered = agents.recall(client.id, kind, body.idempotency_key)
        if remembered is not None:
            return remembered
        if body.definition is not None:
            scenes_check(client, body.definition)
        saved = workflows.update_workflow(
            record.id,
            base_version=body.base_revision,
            name=body.name,
            description=body.description,
            definition=body.definition,
            note=tools.note(client, body.note, t("agent.note_saved")),
        )
        data = composite_json(client, saved)
        agents.remember(client.id, kind, body.idempotency_key, data)
        return data

    @router.patch("/composites/{code}")
    def move_composite(client: ProjectWriter, code: str, body: CompositeMove) -> dict[str, object]:
        """移到另一個可用的專案。"""
        record = composite_for(client, code)
        project_for(client, body.project_id)
        return composite_json(client, workflows.manage(record.id, project_id=body.project_id))

    @router.post("/composites/{code}/revisions/{number}/validate", status_code=202)
    def validate_composite(
        client: Validator, code: str, number: int, body: CompositeRunBody
    ) -> dict[str, object]:
        """交給 Worker 驗證這個版本；通過的紀錄是發布的依據。"""
        record = composite_for(client, code)
        key = tools.scoped_key(client, body.idempotency_key)
        run = start(client, record, body, purpose="validation", revision=number, key=key)
        return run_json(client, run)

    @router.post("/composites/{code}/revisions/{number}/publish")
    def publish_composite(client: ProjectPublisher, code: str, number: int) -> dict[str, object]:
        """發布驗證通過、雜湊相符、依賴完整的版本（門檻和 Portal 相同）。"""
        record = composite_for(client, code)
        scenes_check(client, workflows.revision_workflow(record.code, number))
        return composite_json(client, workflows.publish(record.id, number))

    @router.post("/composites/{code}/runs", status_code=202)
    def run_composite(client: Executor, code: str, body: CompositeRunBody) -> dict[str, object]:
        """正式執行發布的版本；沒有發布時 409 ``workflow_unpublished``。"""
        record = composite_for(client, code)
        key = tools.scoped_key(client, body.idempotency_key)
        return run_json(client, start(client, record, body, purpose="execution", key=key))

    @router.post("/projects/{project_id}/runs", status_code=202)
    def run_project(client: Placer, project_id: str, body: ProjectRunBody) -> dict[str, object]:
        """把專案裡的組合場景逐一排入（各自是一次組合場景的執行）；排不進去的列在 skipped。"""
        client.require("runs:validate" if body.purpose == "validation" else "runs:execute")
        project_for(client, project_id)
        members = [
            item
            for item in workflows.list_workflows(project_id=project_id)
            if not item.archived and client.domain_allowed(item.domain_id)
        ]
        skipped: list[dict[str, object]] = []
        if body.composites is not None:
            wanted = list(dict.fromkeys(body.composites))
            known = {item.code for item in members}
            members = [item for item in members if item.code in wanted]
            for code in wanted:
                if code not in known:
                    error = not_found("workflow_not_found", t("error.workflow_not_found", id=code))
                    skipped.append({"code": code, **error.to_json()})
        started: list[dict[str, object]] = []
        for record in members:
            key = (
                tools.scoped_key(client, f"{body.idempotency_key}\n{record.code}")
                if body.idempotency_key
                else None
            )
            try:
                run = start(client, record, body, purpose=body.purpose, key=key)
            except ServiceError as error:
                skipped.append({"code": record.code, **error.to_json()})
                continue
            started.append(run_json(client, run))
        return {
            "projectId": project_id,
            "purpose": body.purpose,
            "runs": started,
            "skipped": skipped,
        }

    # ------------------------------------------------------------ 組合場景的執行

    @router.get("/composite-runs")
    def list_runs(
        client: RunReader,
        project: str | None = None,
        composite: str | None = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        mine: bool = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, object]:
        """看得到的組合場景執行，新的在前；project、composite 只列那個專案或組合場景的。"""
        allowed = client.policy.projects
        if project is not None:
            project_for(client, project)
            scope: list[str] | None = [project]
        else:
            scope = (
                list(allowed) if allowed is not None else [p.id for p in projects.list_projects()]
            )
        workflow_id = composite_for(client, composite).id if composite is not None else None
        runs = workflows.list_runs(
            workflow_id=workflow_id,
            projects=scope,
            statuses=status or [],
            purposes=purpose or [],
            client_id=client.id if mine else None,
            limit=limit,
        )
        members = {item.id: item for item in workflows.list_workflows()}
        shown = [
            run
            for run in runs
            if run.workflow_id is not None
            and run.workflow_id in members
            and client.domain_allowed(members[run.workflow_id].domain_id)
        ]
        return {"runs": [run_json(client, run) for run in shown]}

    @router.get("/composite-runs/{run_id}")
    def get_run(client: RunReader, run_id: str) -> dict[str, object]:
        """狀態、進度（progress）、每個節點的狀態與那次運行；節點的步驟用 ``/runs/{id}/steps``。"""
        return run_json(client, run_for(client, run_id))

    @router.get("/composite-runs/{run_id}/report")
    def get_report(client: RunReader, run_id: str) -> dict[str, object]:
        """整次組合運行的匯總報告：結論（停在哪個節點的哪一步）、數字、時間軸、每個節點的明細。"""
        run_for(client, run_id)
        return report_for(client, services.composite_report(run_id))

    @router.post("/composite-runs/{run_id}/cancel", status_code=202)
    def cancel_run(client: Placer, run_id: str) -> dict[str, object]:
        """取消自己觸發的組合場景執行：停止目前的節點，後面的不執行。"""
        run = run_for(client, run_id)
        if run.client_id != client.id:
            raise forbidden("run_forbidden", t("error.agent_run_forbidden", id=run_id))
        client.require("runs:validate" if run.purpose == "validation" else "runs:execute")
        return run_json(client, workflows.cancel(run_id))

    @router.post("/composite-runs/{run_id}/rerun", status_code=202)
    def rerun(
        client: Placer, run_id: str, body: CompositeRerunBody | None = None
    ) -> dict[str, object]:
        """用同一份定義再執行一次；resume 從停下的節點繼續（例如人工登入之後）。"""
        run = run_for(client, run_id)
        client.require("runs:validate" if run.purpose == "validation" else "runs:execute")
        if run.status == "running":
            raise conflict("workflow_run_active", t("error.workflow_run_active", id=run_id))
        fixed = client.policy.target
        if fixed is not None and run.target != fixed:
            raise forbidden("target_forbidden", t("error.agent_target_forbidden", target=fixed))
        body = body or CompositeRerunBody()
        key = tools.scoped_key(client, body.idempotency_key)
        existing = workflows.by_key(key)
        if existing is not None:
            return run_json(client, existing)
        tools.run_limit(client)
        again = workflows.rerun(
            run_id, resume=body.resume, idempotency_key=key, client_id=client.id
        )
        return run_json(client, again)

    return router
