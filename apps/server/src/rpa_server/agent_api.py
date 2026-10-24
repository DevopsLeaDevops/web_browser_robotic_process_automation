"""對外 Agent API（/agent-api/v1，M14，ADR 0017）：第三方 Agent 系統寫場景、在錄製端調試、
交給 Worker 驗證與執行，並取得運行過程。

- 只在對外埠提供（:class:`rpa_server.middleware.PortGateMiddleware`）；每個請求帶
  ``Authorization: Bearer <API 金鑰>``，用戶端與權限範圍見 :mod:`rpa_server.agents`。
- 路由只轉接服務層，業務規則與發布門檻和 Portal 相同。這一層另外檢查：權限範圍（403
  ``scope_missing``）、可用的領域與錄製端、回傳頁面內容、執行位置、限額（429 ``limit_reached``）。
- 調試指定錄製端（``recorderId``）：用 :func:`rpa_server.context.use_recorder` 把瀏覽器開在那台；
  場景已有別人（人或其他用戶端）在調試時回 409 ``debug_in_use``，不搶走。Agent 只看得到、
  只能操作自己開的工作階段。
- 寫入請求都記稽核（:class:`AuditMiddleware`）；錯誤一律 ``{"error": {"code", "message", …}}``，
  請求格式不對是 422 ``request_invalid``。
- 這組 API 自己的 OpenAPI 在 ``/agent-api/v1/openapi.json``（不需要金鑰，不含資料）。
- 專案與組合場景的路由在 :mod:`rpa_server.agent_projects`，共用這裡的權限檢查與轉換
  （:class:`AgentTools`）。
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Final, Literal, cast

import anyio
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rpa_core.dsl import scenario_json_schema, validate_text
from rpa_core.dsl.editing import SECTION_KEYS, section_text
from rpa_core.dsl.features import FEATURES
from rpa_runner.files import REPORT, RESULT, STEPS, VIDEO, read_json_or
from rpa_server import __version__
from rpa_server.agents import ApiClientRecord
from rpa_server.api import ContractItem, RevisionCreate, SceneCreate
from rpa_server.context import Via, use_recorder
from rpa_server.debugging import DebugSession
from rpa_server.domain import LOCAL_WORKER, Engine, RunRecord, SceneRecord, Target, issue_json
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.recordings import RecordingTarget
from rpa_server.services import Services
from rpa_server.storage import SCENARIO_FILE

__all__ = [
    "AGENT_PREFIX",
    "API_VERSION",
    "AgentBody",
    "AgentTools",
    "Client",
    "Executor",
    "Placer",
    "ProjectPublisher",
    "ProjectReader",
    "ProjectWriter",
    "RunReader",
    "Validator",
    "agent_api",
    "forbidden",
    "limit_reached",
]

AGENT_PREFIX: Final = "/agent-api/v1"
API_VERSION: Final = "1"
_CLIENT: Final = "agent_client"
"""驗過金鑰的用戶端放在請求的 state（稽核中介層讀）。"""
_ACTIVE_RUNS: Final = ("queued", "running")
_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})


class AgentBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AgentSceneCreate(SceneCreate):
    idempotency_key: str | None = Field(default=None, max_length=100)


class AgentRevisionCreate(RevisionCreate):
    idempotency_key: str | None = Field(default=None, max_length=100)


class SectionBody(AgentBody):
    base_revision: int = Field(ge=1)
    text: str = Field(max_length=200_000)
    note: str | None = Field(default=None, max_length=500)


class ContractBody(AgentBody):
    base_revision: int = Field(ge=1)
    inputs: list[ContractItem] | None = None
    outputs: list[ContractItem] | None = None
    note: str | None = Field(default=None, max_length=500)


class ImportBody(AgentBody):
    """匯入 Playwright（Python）腳本：continue 接在最新版本後面，replace 整份換掉。"""

    source: str = Field(max_length=1_000_000)
    mode: Literal["continue", "replace"] = "continue"
    url: str | None = Field(default=None, max_length=2000)
    engine: Engine = "chromium"
    role_id: str | None = Field(default=None, max_length=64)


class CheckBody(AgentBody):
    yaml: str = Field(max_length=1_000_000)
    scene_id: str | None = Field(default=None, max_length=64)
    """有給時同時檢查場景檔的 id 和它相同。"""


class DebugBody(AgentBody):
    recorder_id: str | None = Field(default=None, max_length=64)
    """在哪台錄製端開瀏覽器；這把金鑰只允許一台時可以不給。"""
    revision: int | None = Field(default=None, ge=1)
    inputs: dict[str, object] | None = None
    engine: Engine | None = None
    headless: bool = True
    base_url: str | None = Field(default=None, max_length=2000)
    restart: bool = False


class StepBody(AgentBody):
    force: bool = False


class LocateBody(AgentBody):
    locator: str | dict[str, object]


class SnapshotBody(AgentBody):
    within: str | dict[str, object] | None = None


class ReloadBody(AgentBody):
    revision: int = Field(ge=1)


class RunBody(AgentBody):
    inputs: dict[str, object] = Field(default_factory=dict[str, object])
    engine: Engine | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    headless: bool | None = None
    target: Target | None = None
    worker_id: str | None = Field(default=None, max_length=64)
    """指定由哪台 Worker 執行（local 是伺服器本機）。"""
    idempotency_key: str | None = Field(default=None, max_length=100)


class RerunBody(AgentBody):
    idempotency_key: str | None = Field(default=None, max_length=100)


# ---------------------------------------------------------------- 稽核


def _error_code(body: bytes) -> str | None:
    try:
        data: object = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict):
        error = cast("dict[str, object]", data).get("error")
        if isinstance(error, dict):
            code = cast("dict[str, object]", error).get("code")
            return str(code) if code is not None else None
    return None


class AuditMiddleware:
    """寫入請求（POST、PUT、PATCH、DELETE）結束後記一筆稽核：用戶端、動作（路由）、對象（路徑參數）、
    結果碼與錯誤代碼。金鑰不對的請求沒有用戶端，不記。"""

    def __init__(self, app: ASGIApp, services: Services) -> None:
        self.app = app
        self.services = services

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET") in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        status = 500
        body = bytearray()

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            elif message["type"] == "http.response.body" and status >= 400 and len(body) < 8192:
                body.extend(cast("bytes", message.get("body", b"")))
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            state = cast("dict[str, object]", scope.get("state") or {})
            client = state.get(_CLIENT)
            if isinstance(client, ApiClientRecord):
                route = scope.get("route")
                action = str(getattr(route, "path", None) or scope.get("path", ""))
                params = cast("dict[str, object]", scope.get("path_params") or {})
                target = "/".join(str(value) for value in params.values()) or None
                peer = cast("tuple[str, int] | None", scope.get("client"))
                await anyio.to_thread.run_sync(
                    lambda: self.services.agents.record_audit(
                        client,
                        method=str(scope.get("method", "")),
                        action=action,
                        target=target,
                        status=status,
                        code=_error_code(bytes(body)) if status >= 400 else None,
                        ip=peer[0] if peer is not None else None,
                    )
                )


# ---------------------------------------------------------------- 錯誤


def forbidden(code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(403, code, message, **details)


def limit_reached(message: str, limit: int) -> ServiceError:
    return ServiceError(429, "limit_reached", message, limit=limit)


def _json_error(status: int, code: str, message: str, **details: object) -> JSONResponse:
    return JSONResponse(ServiceError(status, code, message, **details).to_json(), status)


# ---------------------------------------------------------------- 組裝


_bearer = HTTPBearer(auto_error=False)


def current_client(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ApiClientRecord:
    """依 API 金鑰找出用戶端（401 ``unauthorized``），記在請求上給稽核用。"""
    services = cast("Services", request.app.state.services)
    key = credentials.credentials if credentials is not None else None
    peer = request.client.host if request.client is not None else None
    client = services.agents.authenticate(key, peer)
    request.state.agent_client = client
    return client


Client = Annotated[ApiClientRecord, Depends(current_client)]


def _scoped(*scopes: str) -> Callable[[ApiClientRecord], ApiClientRecord]:
    def check(client: Client) -> ApiClientRecord:
        client.require(*scopes)
        return client

    return check


Reader = Annotated[ApiClientRecord, Depends(_scoped("scenes:read"))]
Writer = Annotated[ApiClientRecord, Depends(_scoped("scenes:write"))]
Debugger = Annotated[ApiClientRecord, Depends(_scoped("debug"))]
Validator = Annotated[ApiClientRecord, Depends(_scoped("runs:validate"))]
Publisher = Annotated[ApiClientRecord, Depends(_scoped("scenes:publish"))]
Executor = Annotated[ApiClientRecord, Depends(_scoped("runs:execute"))]
RunReader = Annotated[ApiClientRecord, Depends(_scoped("runs:read"))]
Placer = Annotated[ApiClientRecord, Depends(_scoped("runs:validate", "runs:execute"))]
"""驗證或執行其中一個（看 Worker、取消、重跑；實際要哪一個依運行的目的再檢查）。"""
ProjectReader = Annotated[ApiClientRecord, Depends(_scoped("projects:read"))]
ProjectWriter = Annotated[ApiClientRecord, Depends(_scoped("projects:write"))]
ProjectPublisher = Annotated[ApiClientRecord, Depends(_scoped("projects:publish"))]


@dataclass(frozen=True, slots=True)
class AgentTools:
    """場景與專案的路由共用的檢查與轉換（在 :func:`agent_api` 裡依服務建立）。"""

    domain_check: Callable[[ApiClientRecord, str | None], None]
    """領域不在可用的清單時 403 ``domain_forbidden``。"""
    note: Callable[[ApiClientRecord, str | None, str], str]
    """Agent 存的版本說明：「Agent〈名稱〉：說明」。"""
    run_json: Callable[[ApiClientRecord, RunRecord], dict[str, object]]
    """運行的 JSON：產物網址改成 Agent API 的（沒開回傳頁面內容時是 None），加上 Portal 的路徑。"""
    scoped_key: Callable[[ApiClientRecord, str | None], str | None]
    run_limit: Callable[[ApiClientRecord], None]
    """排隊中與執行中的運行達到上限時 429 ``limit_reached``。"""
    placement: Callable[
        [ApiClientRecord, Target | None, str | None], tuple[Target | None, str | None]
    ]


def agent_api(services: Services) -> FastAPI:
    """建立 /agent-api/v1 的子應用（掛在主應用下）。"""
    app = FastAPI(
        title="RPA Agent API",
        version=API_VERSION,
        description=t("agent.openapi_description"),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.services = services
    agents = services.agents
    debug = services.debug

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError) -> Response:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(error.to_json(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def request_invalid(request: Request, error: RequestValidationError) -> Response:  # pyright: ignore[reportUnusedFunction]
        problems = [
            {
                "field": ".".join(str(part) for part in cast("list[object]", item.get("loc", []))),
                "message": str(item.get("msg", "")),
            }
            for item in cast("list[dict[str, object]]", error.errors())
        ]
        return _json_error(
            422, "request_invalid", t("error.agent_request_invalid"), problems=problems
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> Response:  # pyright: ignore[reportUnusedFunction]
        codes = {404: "not_found", 405: "method_not_allowed"}
        code = codes.get(error.status_code, "http_error")
        return _json_error(error.status_code, code, str(error.detail))

    # ------------------------------------------------------------ 權限與轉換

    def domain_check(client: ApiClientRecord, domain_id: str | None) -> None:
        if not client.domain_allowed(domain_id):
            raise forbidden(
                "domain_forbidden", t("error.agent_domain_forbidden", id=domain_id or "-")
            )

    def scene_for(client: ApiClientRecord, scene_id: str) -> SceneRecord:
        scene = services.get_scene(scene_id)
        domain_check(client, scene.domain_id)
        return scene

    def content_check(client: ApiClientRecord) -> None:
        if not client.policy.page_content:
            raise forbidden("content_disabled", t("error.agent_content_disabled"))

    def note(client: ApiClientRecord, text: str | None, default: str) -> str:
        return t("agent.note", name=client.name, note=(text or "").strip() or default)[:500]

    def session_for(client: ApiClientRecord, session_id: str) -> DebugSession:
        session = debug.get(session_id)
        if session.client_id != client.id:
            raise not_found("debug_not_found", t("error.debug_not_found", id=session_id))
        return session

    def session_json(client: ApiClientRecord, session: DebugSession) -> dict[str, object]:
        data = session.to_json()
        if session.screenshot and client.policy.page_content:
            data["screenshotUrl"] = f"{AGENT_PREFIX}/debug/{session.id}/files/{session.screenshot}"
        else:
            data["screenshotUrl"] = None
        return data

    def run_for(client: ApiClientRecord, run_id: str) -> RunRecord:
        run = services.get_run(run_id)
        try:
            domain_id = services.get_scene(run.scene_id).domain_id
        except ServiceError:
            domain_id = None
        if not client.domain_allowed(domain_id):
            raise not_found("run_not_found", t("error.run_not_found", id=run_id))
        return run

    def run_json(client: ApiClientRecord, run: RunRecord) -> dict[str, object]:
        data = run.to_json()
        data["portalPath"] = f"/runs/{run.id}"
        content = client.policy.page_content
        data["reportUrl"] = (
            f"{AGENT_PREFIX}/runs/{run.id}/files/{REPORT}" if run.finished and content else None
        )
        video = run.video
        if video is not None and content and video.get("url"):
            data["video"] = {**video, "url": f"{AGENT_PREFIX}/runs/{run.id}/files/{VIDEO}"}
        elif video is not None:
            data["video"] = None
        return data

    def scoped_key(client: ApiClientRecord, key: str | None) -> str | None:
        """運行的冪等鍵在全伺服器唯一：加上用戶端，不同用戶端用同一個值不會互相影響。"""
        key = (key or "").strip()
        if not key:
            return None
        digest = hashlib.sha256(f"{client.id}\n{key}".encode()).hexdigest()[:40]
        return f"agent:{digest}"

    def run_limit(client: ApiClientRecord) -> None:
        """排隊中與執行中的運行（含組合場景的節點）不能超過上限。"""
        limit = client.policy.max_queued_runs
        active = services.list_runs(client_id=client.id, statuses=_ACTIVE_RUNS, limit=limit + 1)
        if len(active) >= limit:
            raise limit_reached(t("error.agent_run_limit", limit=limit), limit)

    def queued_check(client: ApiClientRecord, key: str | None) -> RunRecord | None:
        """冪等鍵用過時回傳那次運行；否則檢查排隊中與執行中的數量。"""
        if key is not None:
            existing = agents.run_for_key(key)
            if existing is not None:
                return services.get_run(existing)
        run_limit(client)
        return None

    def placement(
        client: ApiClientRecord, target: Target | None, worker_id: str | None
    ) -> tuple[Target | None, str | None]:
        """執行位置：用戶端固定了位置時不能指定別的；指定 Worker 要在允許的清單裡。"""
        fixed = client.policy.target
        if fixed is not None and target is not None and target != fixed:
            raise forbidden("target_forbidden", t("error.agent_target_forbidden", target=fixed))
        target = target or fixed
        worker_id = (worker_id or "").strip() or None
        if worker_id is None:
            return target, None
        allowed = client.policy.workers
        if allowed is not None and worker_id not in allowed:
            raise forbidden("worker_forbidden", t("error.agent_worker_forbidden", id=worker_id))
        if worker_id == LOCAL_WORKER:
            if target == "remote":
                raise invalid(
                    "worker_target_mismatch", t("error.agent_worker_target", id=worker_id)
                )
            return "local", None
        services.workers.get_worker(worker_id)
        if target == "local":
            raise invalid("worker_target_mismatch", t("error.agent_worker_target", id=worker_id))
        return "remote", worker_id

    def queue_run(
        client: ApiClientRecord,
        scene_id: str,
        body: RunBody,
        *,
        purpose: Literal["validation", "execution"],
        number: int | None = None,
    ) -> dict[str, object]:
        scene_for(client, scene_id)
        key = scoped_key(client, body.idempotency_key)
        existing = queued_check(client, key)
        if existing is not None:
            return run_json(client, existing)
        target, worker = placement(client, body.target, body.worker_id)
        run = services.request_run(
            scene_id,
            purpose=purpose,
            number=number,
            inputs=body.inputs,
            engine=body.engine,
            base_url=body.base_url,
            idempotency_key=key,
            headless=body.headless,
            target=target,
            required_worker=worker,
            client_id=client.id,
        )
        return run_json(client, run)

    # ------------------------------------------------------------ 探索

    @app.get("/meta")
    def meta(client: Client) -> dict[str, object]:
        """這把金鑰能做什麼：權限範圍、限制與限額；伺服器與 API 的版本、支援的 DSL 擴充。"""
        policy = client.policy
        return {
            "apiVersion": API_VERSION,
            "serverVersion": __version__,
            "server": services.server_info(),
            "client": {"id": client.id, "name": client.name},
            "scopes": list(policy.scopes),
            "pageContent": policy.page_content,
            "limits": {
                "debugSessions": policy.max_debug_sessions,
                "queuedRuns": policy.max_queued_runs,
            },
            "domains": list(policy.domains) if policy.domains is not None else None,
            "projects": list(policy.projects) if policy.projects is not None else None,
            "recorders": list(policy.recorders),
            "target": policy.target,
            "workers": list(policy.workers) if policy.workers is not None else None,
            "expiresAt": client.to_json()["expiresAt"],
            "dslFeatures": sorted(FEATURES),
        }

    @app.get("/dsl/schema")
    def dsl_schema(client: Client) -> dict[str, object]:
        """場景 DSL 的 JSON Schema（同 ``rpa schema``）。"""
        return scenario_json_schema()

    @app.post("/dsl/check")
    def dsl_check(client: Client, body: CheckBody) -> dict[str, object]:
        """不存檔校驗場景 YAML；問題帶行號、步驟與欄位。"""
        if body.scene_id:
            checked = services.storage.check({SCENARIO_FILE: body.yaml}, scene_id=body.scene_id)
            issues = checked.issues
        else:
            issues = validate_text(body.yaml).issues
        return {
            "ok": not issues,
            "issues": [issue_json(issue) for issue in issues],
        }

    @app.get("/domains")
    def list_domains(client: Reader) -> dict[str, object]:
        domains = [d for d in services.list_domains() if client.domain_allowed(d.id)]
        return {
            "domains": [{"id": d.id, "name": d.name, "description": d.description} for d in domains]
        }

    @app.get("/roles")
    def list_roles(client: Reader) -> dict[str, object]:
        """登入角色與登入狀態；需要登入時請人在錄製端做人工登入。"""
        roles = [
            role
            for role in services.roles.list_roles()
            if role.domain_id is None or client.domain_allowed(role.domain_id)
        ]
        return {
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "description": role.description,
                    "status": role.status,
                    "checkedAt": role.to_json()["checkedAt"],
                    "usedBy": list(role.used_by),
                    "domainId": role.domain_id,
                }
                for role in roles
            ]
        }

    @app.get("/secrets")
    def list_secrets(client: Reader) -> dict[str, object]:
        """Secrets 只有名稱；值由人在 Portal 填，永遠不回傳。"""
        return {"secrets": [{"name": info.name} for info in services.roles.list_secrets()]}

    @app.get("/recorders")
    def list_recorders(client: Debugger) -> dict[str, object]:
        """這把金鑰可以開調試的錄製端：是否在線、能不能有頭、瀏覽器、App 版本與支援的功能。"""
        allowed = set(client.policy.recorders)
        return {
            "recorders": [
                {
                    "id": item.id,
                    "name": item.name,
                    "status": item.status,
                    "allowAgent": item.allow_agent and not item.disabled,
                    "headlessOnly": item.agent_headless_only,
                    "display": item.display,
                    "browsers": list(item.browsers),
                    "version": item.version,
                    "os": item.os,
                    "features": list(item.features),
                    "capabilities": list(item.capabilities),
                }
                for item in services.recorders.list_recorders()
                if item.id in allowed
            ]
        }

    @app.get("/workers")
    def list_workers(client: Placer) -> dict[str, object]:
        """可以指定的 Worker（local 是伺服器本機），以及這把金鑰的執行位置。"""
        allowed = client.policy.workers
        workers: list[dict[str, object]] = []
        if services.local_worker and (allowed is None or LOCAL_WORKER in allowed):
            workers.append(
                {"id": LOCAL_WORKER, "name": services.server_info()["name"], "status": "online"}
            )
        workers.extend(
            {
                "id": item.id,
                "name": item.name,
                "status": item.status,
                "display": item.display,
                "browsers": list(item.browsers),
                "version": item.version,
                "os": item.os,
                "features": list(item.features),
            }
            for item in services.workers.list_workers()
            if allowed is None or item.id in allowed
        )
        return {
            "workers": workers,
            "target": client.policy.target,
            "defaultTarget": services.workers.default_target(),
        }

    # ------------------------------------------------------------ 場景與版本

    @app.get("/scenes")
    def list_scenes(
        client: Reader, q: str = "", category: str | None = None, domain: str | None = None
    ) -> dict[str, object]:
        scenes = services.list_scenes(query=q, category=category, domain=domain)
        return {"scenes": [s.to_json() for s in scenes if client.domain_allowed(s.domain_id)]}

    @app.post("/scenes", status_code=201)
    def create_scene(client: Writer, body: AgentSceneCreate) -> dict[str, object]:
        """建立場景（第 1 版是只有開頁面的範本）；冪等鍵用過時回傳上次建立的場景。"""
        remembered = agents.recall(client.id, "scene", body.idempotency_key)
        if remembered is not None:
            return remembered
        domain_id = body.domain_id or services.unassigned_domain()
        domain_check(client, domain_id)
        scene = services.create_scene(
            body.id,
            body.name,
            body.category,
            domain_id=domain_id,
            note=t("agent.note_created", name=client.name),
        )
        data = scene.to_json()
        agents.remember(client.id, "scene", body.idempotency_key, data)
        return data

    @app.get("/scenes/{scene_id}")
    def get_scene(client: Reader, scene_id: str) -> dict[str, object]:
        """場景、版本清單、發布狀態，最新版本需要的角色與 Secrets（needs）。"""
        scene = scene_for(client, scene_id)
        try:
            needs_json = services.scene_needs(
                services.revision_scenario(scene_id, scene.latest_number)
            ).to_json()
        except ServiceError:
            needs_json = None
        session = debug.for_scene(scene_id)
        return {
            **scene.to_json(),
            "revisions": [revision.to_json() for revision in services.revisions(scene_id)],
            "needs": needs_json,
            "debug": (
                {"id": session.id, "mine": session.client_id == client.id, "status": session.status}
                if session is not None
                else None
            ),
        }

    @app.get("/scenes/{scene_id}/revisions/{number}")
    def get_revision(client: Reader, scene_id: str, number: int) -> dict[str, object]:
        scene_for(client, scene_id)
        revision = services.get_revision(scene_id, number)
        return {**revision.to_json(), "files": services.revision_files(scene_id, number)}

    @app.post("/scenes/{scene_id}/revisions", status_code=201)
    def save_revision(
        client: Writer, scene_id: str, body: AgentRevisionCreate
    ) -> dict[str, object]:
        """存成新版本；baseRevision 不是最新版時 409 ``stale_base``（帶 latest）。"""
        scene_for(client, scene_id)
        kind = f"revision:{scene_id}"
        remembered = agents.recall(client.id, kind, body.idempotency_key)
        if remembered is not None:
            return remembered
        revision = services.save_revision(
            scene_id,
            base=body.base_revision,
            files=body.files,
            note=note(client, body.note, t("agent.note_saved")),
        )
        data = revision.to_json()
        agents.remember(client.id, kind, body.idempotency_key, data)
        return data

    @app.get("/scenes/{scene_id}/sections/{key}")
    def get_section(
        client: Reader, scene_id: str, key: str, revision: int | None = None
    ) -> dict[str, object]:
        """場景檔的一段原文：steps、verify、inputs、outputs。"""
        scene_for(client, scene_id)
        shown = services.get_revision(scene_id, revision)
        if key not in SECTION_KEYS:
            raise not_found("section_unknown", t("error.section_unknown", key=key))
        text = services.revision_files(scene_id, shown.number)[SCENARIO_FILE]
        return {"key": key, "revision": shown.number, "text": section_text(text, key)}

    @app.put("/scenes/{scene_id}/sections/{key}", status_code=201)
    def save_section(
        client: Writer, scene_id: str, key: str, body: SectionBody
    ) -> dict[str, object]:
        """只換掉一段，存成新版本；text 以 ``key:`` 開頭，空白時移除這一段。"""
        scene_for(client, scene_id)
        default = (
            t("revision.note_section", section=t(f"section.{key}")) if key in SECTION_KEYS else key
        )
        revision = services.save_section(
            scene_id,
            key,
            base=body.base_revision,
            text=body.text,
            note=note(client, body.note, default),
        )
        return revision.to_json()

    @app.put("/scenes/{scene_id}/contract", status_code=201)
    def save_contract(client: Writer, scene_id: str, body: ContractBody) -> dict[str, object]:
        """以表格形式改入參與出參（None 的那一段不動），存成新版本。"""
        scene_for(client, scene_id)

        def items(rows: list[ContractItem] | None) -> list[dict[str, object]] | None:
            return None if rows is None else [row.model_dump(by_alias=True) for row in rows]

        revision = services.save_contract(
            scene_id,
            base=body.base_revision,
            inputs=items(body.inputs),
            outputs=items(body.outputs),
            note=note(client, body.note, t("revision.note_contract")),
        )
        return revision.to_json()

    @app.post("/scenes/{scene_id}/import", status_code=201)
    def import_script(client: Writer, scene_id: str, body: ImportBody) -> dict[str, object]:
        """匯入 Playwright（Python）腳本，轉成 DSL 存成新版本；轉不了的寫在 warnings。"""
        scene_for(client, scene_id)
        record = services.recordings.import_source(
            body.source,
            RecordingTarget(scene_id, False, mode=body.mode),
            url=body.url,
            engine=body.engine,
            role_id=body.role_id,
        )
        return record.to_json()

    # ------------------------------------------------------------ 調試

    @app.post("/scenes/{scene_id}/debug", status_code=202)
    def start_debug(client: Debugger, scene_id: str, body: DebugBody) -> dict[str, object]:
        """在錄製端開調試工作階段（預設無頭）；這個場景已經有自己的工作階段時回傳它。"""
        scene_for(client, scene_id)
        allowed = client.policy.recorders
        recorder_id = (body.recorder_id or "").strip() or None
        if recorder_id is None:
            if len(allowed) != 1:
                raise invalid("recorder_required", t("error.agent_recorder_required"))
            recorder_id = allowed[0]
        if recorder_id not in allowed:
            raise forbidden(
                "recorder_forbidden", t("error.agent_recorder_forbidden", id=recorder_id)
            )
        recorder = services.recorders.get_recorder(recorder_id)
        if not recorder.allow_agent or recorder.disabled:
            raise forbidden("recorder_agent_off", t("error.agent_recorder_off", name=recorder.name))
        if not body.headless and recorder.agent_headless_only:
            raise forbidden(
                "recorder_headless_only", t("error.agent_recorder_headless", name=recorder.name)
            )
        existing = debug.for_scene(scene_id)
        if existing is not None and existing.client_id != client.id:
            raise conflict("debug_in_use", t("error.agent_debug_in_use", id=scene_id))
        mine = [s for s in debug.sessions() if s.client_id == client.id and s.scene_id != scene_id]
        limit = client.policy.max_debug_sessions
        if len(mine) >= limit:
            raise limit_reached(t("error.agent_debug_limit", limit=limit), limit)
        with use_recorder(Via(recorder.id, recorder.name)):
            session = debug.start(
                scene_id,
                revision=body.revision,
                inputs=body.inputs,
                engine=body.engine,
                headless=body.headless,
                base_url=body.base_url,
                restart=body.restart,
                client_id=client.id,
            )
        return session_json(client, session)

    @app.get("/debug")
    def list_debug(client: Debugger) -> dict[str, object]:
        """自己開的、還在進行的工作階段。"""
        sessions = [s for s in debug.sessions() if s.client_id == client.id]
        return {"sessions": [session_json(client, s) for s in sessions]}

    @app.get("/debug/{session_id}")
    def get_debug(client: Debugger, session_id: str) -> dict[str, object]:
        return session_json(client, session_for(client, session_id))

    @app.post("/debug/{session_id}/snapshot")
    def debug_snapshot(
        client: Debugger, session_id: str, body: SnapshotBody | None = None
    ) -> dict[str, object]:
        """目前頁面的結構：無障礙樹、表單欄位、iframe 與分頁；密碼與 Secrets 的值遮罩。"""
        content_check(client)
        session_for(client, session_id)
        return debug.snapshot(session_id, body.within if body is not None else None)

    @app.post("/debug/{session_id}/screenshot")
    def debug_screenshot(client: Debugger, session_id: str) -> dict[str, object]:
        content_check(client)
        session_for(client, session_id)
        return session_json(client, debug.screenshot(session_id))

    @app.get("/debug/{session_id}/files/{name}")
    def debug_file(client: Debugger, session_id: str, name: str) -> Response:
        content_check(client)
        session_for(client, session_id)
        path = services.storage.debug_file(session_id, name)
        if path is None:
            raise not_found("file_not_found", t("error.file_not_found", path=name))
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/debug/{session_id}/locate")
    def debug_locate(client: Debugger, session_id: str, body: LocateBody) -> dict[str, object]:
        """測試定位器：找到幾個、前幾個的文字（located）。"""
        session_for(client, session_id)
        return session_json(client, debug.locate(session_id, body.locator))

    @app.post("/debug/{session_id}/steps/{index}")
    def debug_step(
        client: Debugger, session_id: str, index: int, body: StepBody | None = None
    ) -> dict[str, object]:
        """執行一步；有副作用而且執行過的步驟要 force，否則 409 ``confirm_required``。"""
        session_for(client, session_id)
        force = body.force if body is not None else False
        return session_json(client, debug.run_step(session_id, index, force=force))

    @app.post("/debug/{session_id}/run-to/{index}")
    def debug_run_to(client: Debugger, session_id: str, index: int) -> dict[str, object]:
        session_for(client, session_id)
        return session_json(client, debug.run_to(session_id, index))

    @app.post("/debug/{session_id}/reload")
    def debug_reload(client: Debugger, session_id: str, body: ReloadBody) -> dict[str, object]:
        """換到剛存的版本：瀏覽器與已執行的步驟（依 id）保留。"""
        session_for(client, session_id)
        return session_json(client, debug.reload(session_id, body.revision))

    @app.post("/debug/{session_id}/reset")
    def debug_reset(client: Debugger, session_id: str) -> dict[str, object]:
        session_for(client, session_id)
        return session_json(client, debug.reset(session_id))

    @app.delete("/debug/{session_id}")
    def close_debug(client: Debugger, session_id: str) -> dict[str, object]:
        session_for(client, session_id)
        debug.close(session_id)
        return {"closed": session_id}

    # ------------------------------------------------------------ 驗證、發布、執行

    @app.post("/scenes/{scene_id}/revisions/{number}/validate", status_code=202)
    def validate_revision(
        client: Validator, scene_id: str, number: int, body: RunBody
    ) -> dict[str, object]:
        """交給 Worker 驗證這個版本；通過的紀錄是發布的依據。"""
        return queue_run(client, scene_id, body, purpose="validation", number=number)

    @app.post("/scenes/{scene_id}/revisions/{number}/publish")
    def publish_revision(client: Publisher, scene_id: str, number: int) -> dict[str, object]:
        """發布驗證通過、內容雜湊相符的版本（門檻和 Portal 相同）。"""
        scene_for(client, scene_id)
        return services.publish(scene_id, number).to_json()

    @app.post("/scenes/{scene_id}/runs", status_code=202)
    def run_scene(client: Executor, scene_id: str, body: RunBody) -> dict[str, object]:
        """用入參正式執行已發布版本。"""
        return queue_run(client, scene_id, body, purpose="execution")

    @app.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(client: Placer, run_id: str) -> dict[str, object]:
        """取消自己觸發的運行；已經發生的外部動作不會回滾。"""
        run = run_for(client, run_id)
        if run.client_id != client.id:
            raise forbidden("run_forbidden", t("error.agent_run_forbidden", id=run_id))
        client.require("runs:validate" if run.purpose == "validation" else "runs:execute")
        return run_json(client, services.cancel_run(run_id))

    @app.post("/runs/{run_id}/rerun", status_code=202)
    def rerun(client: Placer, run_id: str, body: RerunBody | None = None) -> dict[str, object]:
        """同樣的入參與選項再跑一次（例如人工登入之後）；驗證用同一個版本，執行用目前發布的版本。"""
        run = run_for(client, run_id)
        if run.purpose == "workflow":
            raise conflict("rerun_workflow", t("error.agent_rerun_workflow"))
        client.require("runs:validate" if run.purpose == "validation" else "runs:execute")
        fixed = client.policy.target
        if fixed is not None and run.target != fixed:
            raise forbidden("target_forbidden", t("error.agent_target_forbidden", target=fixed))
        key = scoped_key(client, body.idempotency_key if body is not None else None)
        existing = queued_check(client, key)
        if existing is not None:
            return run_json(client, existing)
        return run_json(client, services.rerun(run_id, idempotency_key=key, client_id=client.id))

    # ------------------------------------------------------------ 運行過程

    @app.get("/runs")
    def list_runs(
        client: RunReader,
        scene: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[str] | None, Query()] = None,
        purpose: Annotated[list[str] | None, Query()] = None,
        mine: bool = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, object]:
        """看得到的運行（可用領域裡的場景），新的在前；mine 只列自己觸發的。"""
        scenes = list(scene or [])
        domains = client.policy.domains
        if domains is not None:
            visible = {
                s.id for d in domains for s in services.list_scenes(domain=d, include_archived=True)
            }
            scenes = [s for s in scenes if s in visible] if scenes else sorted(visible)
            if not scenes:
                return {"runs": []}
        runs = services.list_runs(
            scenes=scenes,
            statuses=status or [],
            purposes=purpose or [],
            limit=limit,
            client_id=client.id if mine else None,
        )
        return {"runs": [run_json(client, run) for run in runs]}

    @app.get("/runs/{run_id}")
    def get_run(client: RunReader, run_id: str) -> dict[str, object]:
        """狀態、目前階段、哪台 Worker、入參；結束後的出參（只有通過才有）、錯誤與結果。"""
        run = run_for(client, run_id)
        return {
            **run_json(client, run),
            "result": services.run_result(run_id) if run.finished else None,
            "files": (
                services.storage.run_files(run_id)
                if run.finished and client.policy.page_content
                else []
            ),
        }

    @app.get("/runs/{run_id}/steps")
    def run_steps(client: RunReader, run_id: str) -> dict[str, object]:
        """每一步的狀態、時間、錯誤；第一期在運行結束後才有完整的結果。"""
        run = run_for(client, run_id)
        steps: object = []
        if run.finished:
            result = services.run_result(run_id) or {}
            steps = result.get("steps") or []
        else:
            path = services.storage.run_file(run_id, STEPS)
            if path is not None:
                steps = read_json_or(path, [])
        return {"runId": run.id, "status": run.status, "finished": run.finished, "steps": steps}

    @app.get("/runs/{run_id}/files/{relative:path}")
    def run_file(client: RunReader, run_id: str, relative: str) -> Response:
        """運行的產物：截圖、report.html、result.json、錄影等（要回傳頁面內容）。"""
        if relative != RESULT:
            content_check(client)
        run_for(client, run_id)
        path = services.run_file(run_id, relative)
        return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

    # ------------------------------------------------------------ 專案（agent_projects.py）

    from rpa_server.agent_projects import project_routes  # 它匯入本模組，建立時才取用

    tools = AgentTools(
        domain_check=domain_check,
        note=note,
        run_json=run_json,
        scoped_key=scoped_key,
        run_limit=run_limit,
        placement=placement,
    )
    app.include_router(project_routes(services, tools))
    app.add_middleware(AuditMiddleware, services=services)
    return app
