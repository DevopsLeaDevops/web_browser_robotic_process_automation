"""管理介面的資料：場景、版本、執行的狀態與給 API、頁面使用的唯讀紀錄。

服務層（services.py）從資料庫讀出後轉成這裡的紀錄，API 與頁面只碰這些紀錄、不碰資料庫物件。

狀態：

- 版本：草稿 draft → 驗證中 validating → 通過 passed／失敗 failed；發布後場景指向該版本。
  改內容就是新版本，舊版本的驗證結果不能拿來發布新內容。
- 執行：queued → running → passed／failed／timed_out／cancelled；場景要以角色登入而角色沒登入時
  是 needs_login（沒有執行任何步驟，登入後可以重新執行）。
- 執行目的：驗證 validation（任何版本，結果決定版本能不能發布）、執行 execution（只用已發布版本）、
  試驗場序列的節點 workflow（序列固定的版本，只能是發布過的版本；M6）。
- 序列的執行：running → passed／failed／timed_out／cancelled／needs_login；節點依序排入佇列，
  一個節點沒有通過就停在那裡，後面的節點是略過 skipped（M6）。
- 執行位置：本機 local（管理 Portal 這台電腦）、遠端 remote（遠端 worker）、任一 any（M9a）。
  遠端 worker 的狀態：線上 online（最近有報到）、忙碌 busy（正在執行）、離線 offline、
  停用 disabled。
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from rpa_core.dsl import Issue, format_issue
from rpa_core.workflow import Workflow, WorkflowProblem

__all__ = [
    "DOMAIN_ID",
    "ENGINES",
    "FINISHED",
    "LOCAL_WORKER",
    "PURPOSES",
    "ROLE_STATUSES",
    "RUN_STATUSES",
    "TARGETS",
    "CompositeRevisionRecord",
    "DependencyItem",
    "DependencyStatus",
    "DomainRecord",
    "Engine",
    "NodeStatus",
    "Purpose",
    "RecorderRecord",
    "RecorderStatus",
    "RecordingRecord",
    "RevisionRecord",
    "RevisionStatus",
    "RoleRecord",
    "RoleStatus",
    "RunRecord",
    "RunStatus",
    "SceneCard",
    "SceneRecord",
    "Target",
    "VerificationRecord",
    "WorkerRecord",
    "WorkerStatus",
    "WorkflowNodeState",
    "WorkflowRecord",
    "WorkflowRunRecord",
    "WorkflowRunStatus",
    "issue_json",
    "now",
]

RevisionStatus = Literal["draft", "validating", "passed", "failed"]
RunStatus = Literal[
    "queued", "running", "passed", "failed", "timed_out", "cancelled", "needs_login"
]
RoleStatus = Literal["none", "logged_in", "needs_login", "unknown"]
"""角色：還沒登入過、已登入、需要登入、不確定（檢查時出錯）。"""
Purpose = Literal["validation", "execution", "workflow"]
Engine = Literal["chromium", "firefox"]

RUN_STATUSES: Final[tuple[RunStatus, ...]] = (
    "queued",
    "running",
    "passed",
    "failed",
    "timed_out",
    "cancelled",
    "needs_login",
)
FINISHED: Final[frozenset[str]] = frozenset(
    {"passed", "failed", "timed_out", "cancelled", "needs_login"}
)
ROLE_STATUSES: Final[tuple[RoleStatus, ...]] = ("none", "logged_in", "needs_login", "unknown")
PURPOSES: Final[tuple[Purpose, ...]] = ("validation", "execution", "workflow")
WorkflowRunStatus = Literal["running", "passed", "failed", "timed_out", "cancelled", "needs_login"]
NodeStatus = Literal[
    "pending",
    "queued",
    "running",
    "passed",
    "failed",
    "timed_out",
    "cancelled",
    "needs_login",
    "skipped",
    "reused",
]
"""序列裡一個節點：還沒輪到、執行中或結束（同執行的狀態）、因為前面停下而略過、沿用上一次的結果。"""
ENGINES: Final[tuple[Engine, ...]] = ("chromium", "firefox")
Target = Literal["local", "remote", "any"]
TARGETS: Final[tuple[Target, ...]] = ("local", "remote", "any")
LOCAL_WORKER: Final = "local"
"""本機 worker（管理 Portal 程序裡的執行緒）在 runs.worker_id 的代號。"""
WorkerStatus = Literal["online", "busy", "offline", "disabled"]
RecorderStatus = Literal["online", "busy", "offline", "disabled"]
"""錄製端（M10.2）：busy 是有錄製、調試或人工登入的子程序在這台執行。"""
DOMAIN_ID: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""領域代號的規則（與場景 id 相同）。"""


def now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def issue_json(issue: Issue) -> dict[str, object]:
    """校驗問題的 JSON（與 ``rpa validate --format json`` 相同的欄位），加上完整說明 text。"""
    position = issue.position
    return {
        "line": position.line if position else None,
        "column": position.column if position else None,
        "step": issue.step,
        "stepId": issue.step_id,
        "field": issue.field or None,
        "path": list(issue.path),
        "code": issue.code,
        "message": issue.message,
        "text": format_issue(issue),
    }


@dataclass(frozen=True, slots=True)
class DomainRecord:
    """領域：場景管理的一個二級選單，例如「測試網站自動化」「谷歌自動化」。"""

    id: str
    name: str
    description: str | None
    position: int
    scene_count: int
    created_at: datetime
    problems: tuple[dict[str, object], ...] = ()
    """最近一次載入領域資料夾發現的問題（M11；rpa_core.pack.PackIssue 的 JSON）。"""
    loaded_at: datetime | None = None
    role_count: int = 0

    @property
    def errors(self) -> int:
        return sum(1 for item in self.problems if item.get("severity") != "warning")

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "position": self.position,
            "sceneCount": self.scene_count,
            "roleCount": self.role_count,
            "createdAt": _iso(self.created_at),
            "loadedAt": _iso(self.loaded_at),
            "problems": list(self.problems),
        }


@dataclass(frozen=True, slots=True)
class SceneRecord:
    id: str
    name: str
    category: str | None
    description: str | None
    domain_id: str | None
    """所屬領域；None 代表還沒分到任何領域。"""
    kind: str
    """最新版本的種類：dsl 或 script。"""
    base_url: str | None
    """執行時預設的網址（覆寫場景檔的 browser.baseUrl）；None 代表照場景檔。"""
    latest_number: int
    latest_status: RevisionStatus
    published_number: int | None
    archived: bool
    created_at: datetime
    updated_at: datetime
    missing: bool = False
    """來源缺失（M11）：領域資料夾裡已經沒有這個場景。"""

    @property
    def published(self) -> bool:
        return self.published_number is not None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "domainId": self.domain_id,
            "kind": self.kind,
            "baseUrl": self.base_url,
            "latestRevision": self.latest_number,
            "latestStatus": self.latest_status,
            "publishedRevision": self.published_number,
            "archived": self.archived,
            "missing": self.missing,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    scene_id: str
    number: int
    content_hash: str
    kind: str
    status: RevisionStatus
    note: str | None
    created_at: datetime
    published_at: datetime | None
    published: bool
    """是不是場景目前發布的版本。"""
    verified: bool = False
    """有雜湊相符的通過驗證紀錄（M11 的發布門檻，不管是哪一台伺服器驗證的）。"""
    problem: str | None = None
    """讓這個版本不能執行、不能發布的問題代碼（M11）。"""

    def to_json(self) -> dict[str, object]:
        return {
            "sceneId": self.scene_id,
            "number": self.number,
            "contentHash": self.content_hash,
            "kind": self.kind,
            "status": self.status,
            "note": self.note,
            "createdAt": _iso(self.created_at),
            "publishedAt": _iso(self.published_at),
            "published": self.published,
            "verified": self.verified,
            "problem": self.problem,
        }


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    """領域資料夾裡的一份驗證紀錄（M11）：哪一台伺服器、誰、在哪台 worker、結果。"""

    id: str
    """執行編號（也是檔名）。"""
    revision: int
    status: str
    matches: bool
    """紀錄的雜湊和版本相符；不符的通過紀錄不能當發布的依據。"""
    finished_at: datetime
    by: str
    server_id: str
    server_name: str
    worker: str
    engine: str | None
    headless: bool | None
    here: bool
    """這台伺服器有這次執行的紀錄（可以開報告）。"""

    @property
    def proof(self) -> bool:
        return self.status == "passed" and self.matches

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "revision": self.revision,
            "status": self.status,
            "matches": self.matches,
            "proof": self.proof,
            "finishedAt": _iso(self.finished_at),
            "by": self.by,
            "server": {"id": self.server_id, "name": self.server_name},
            "worker": self.worker,
            "engine": self.engine,
            "headless": self.headless,
            "here": self.here,
        }


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    scene_id: str
    scene_name: str
    category: str | None
    revision_number: int
    purpose: Purpose
    status: RunStatus
    stage: str | None
    engine: str | None
    base_url: str | None
    input: dict[str, object]
    output: dict[str, object] | None
    error: str | None
    scenario_hash: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    headless: bool = True
    """無頭模式（不顯示瀏覽器視窗）；False 是有頭模式。"""
    workflow_run_id: str | None = None
    """屬於哪一次序列的執行（M6）。"""
    node_id: str | None = None
    target: Target = "local"
    """執行位置（M9a）。"""
    worker_id: str | None = None
    """由哪台 worker 執行；local 是本機，還沒開始時是 None。"""

    @property
    def finished(self) -> bool:
        return self.status in FINISHED

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sceneId": self.scene_id,
            "sceneName": self.scene_name,
            "category": self.category,
            "revision": self.revision_number,
            "purpose": self.purpose,
            "status": self.status,
            "stage": self.stage,
            "engine": self.engine,
            "baseUrl": self.base_url,
            "headless": self.headless,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "scenarioHash": self.scenario_hash,
            "cancelRequested": self.cancel_requested,
            "createdAt": _iso(self.created_at),
            "startedAt": _iso(self.started_at),
            "finishedAt": _iso(self.finished_at),
            "durationSeconds": self.duration_seconds,
            "finished": self.finished,
            "reportUrl": f"/runs/{self.id}/files/report.html" if self.finished else None,
            "workflowRunId": self.workflow_run_id,
            "nodeId": self.node_id,
            "target": self.target,
            "workerId": self.worker_id,
        }


@dataclass(frozen=True, slots=True)
class SceneCard:
    """領域頁的一張場景卡片：場景、最近一次執行、最近一張執行截圖。"""

    scene: SceneRecord
    last_run: RunRecord | None
    screenshot_run: str | None
    """有 screenshot.png 的最近一次執行的編號。"""

    def to_json(self) -> dict[str, object]:
        return {
            **self.scene.to_json(),
            "lastRun": self.last_run.to_json() if self.last_run is not None else None,
            "screenshotUrl": (
                f"/runs/{self.screenshot_run}/files/screenshot.png"
                if self.screenshot_run is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class RoleRecord:
    """登入角色，加上登入狀態檔與進行中的登入、檢查（M4）。"""

    id: str
    name: str
    description: str | None
    login_url: str
    check_url: str | None
    check_locator: dict[str, object]
    engine: str
    auto_login: str | None
    status: RoleStatus
    message: str | None
    checked_at: datetime | None
    state_saved_at: datetime | None
    """登入狀態檔的時間；None 代表還沒有登入狀態。"""
    used_by: tuple[str, ...]
    """用到這個角色的場景（最新版本）。"""
    activity: str | None = None
    """進行中的工作：login（人工登入中）、checking（檢查中）。"""
    session: dict[str, object] | None = None
    """最近一次人工登入的進度。"""
    created_at: datetime | None = None
    domain_id: str | None = None
    """定義放在哪個領域資料夾（M11）。"""

    @property
    def has_state(self) -> bool:
        return self.state_saved_at is not None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "loginUrl": self.login_url,
            "checkUrl": self.check_url,
            "check": self.check_locator,
            "engine": self.engine,
            "autoLogin": self.auto_login,
            "status": self.status,
            "message": self.message,
            "checkedAt": _iso(self.checked_at),
            "stateSavedAt": _iso(self.state_saved_at),
            "usedBy": list(self.used_by),
            "activity": self.activity,
            "session": self.session,
            "domainId": self.domain_id,
        }


@dataclass(frozen=True, slots=True)
class RecordingRecord:
    """一次錄製或匯入的錄製稿（M4）。"""

    id: str
    scene_id: str
    scene_name: str
    new_scene: bool
    domain_id: str | None
    revision_number: int | None
    source: str
    url: str | None
    engine: str
    role_id: str | None
    status: str
    warnings: list[dict[str, object]]
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    mode: str = "new"
    """new（新場景）、continue（接在既有步驟後面）、replace（既有場景整份換成錄製的草稿）。"""
    base_revision: int | None = None
    device_id: str | None = None
    """在哪台錄製端錄製（M10.2）；在伺服器這台錄製或貼上的是 None。"""

    @property
    def finished(self) -> bool:
        return self.status != "recording"

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sceneId": self.scene_id,
            "sceneName": self.scene_name,
            "newScene": self.new_scene,
            "domainId": self.domain_id,
            "revision": self.revision_number,
            "source": self.source,
            "url": self.url,
            "engine": self.engine,
            "roleId": self.role_id,
            "status": self.status,
            "warnings": self.warnings,
            "error": self.error,
            "createdAt": _iso(self.created_at),
            "finishedAt": _iso(self.finished_at),
            "finished": self.finished,
            "mode": self.mode,
            "baseRevision": self.base_revision,
            "deviceId": self.device_id,
        }


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    """自由試驗場的一個序列（M6）。"""

    id: int
    name: str
    description: str | None
    workflow: Workflow
    version: int
    created_at: datetime
    updated_at: datetime
    problems: tuple[WorkflowProblem, ...] = ()
    """執行前的檢查發現的問題；有問題時不能執行。"""
    last_run: "WorkflowRunRecord | None" = None
    code: str = ""
    """英數代號（M11 PR 2）；version 是最新的版本號碼。"""
    domain_id: str | None = None
    published_number: int | None = None
    archived: bool = False
    dependency: "DependencyStatus" = "complete"
    """依賴是否完整（最新版本與發布的版本）：complete、warnings、incomplete。"""

    @property
    def published(self) -> bool:
        return self.published_number is not None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "code": self.code,
            "domainId": self.domain_id,
            "name": self.name,
            "description": self.description,
            "definition": self.workflow.to_json(),
            "version": self.version,
            "latestRevision": self.version,
            "publishedRevision": self.published_number,
            "archived": self.archived,
            "dependency": self.dependency,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "problems": [problem.to_json() for problem in self.problems],
            "lastRun": self.last_run.to_json() if self.last_run is not None else None,
        }


@dataclass(frozen=True, slots=True)
class WorkflowNodeState:
    """序列執行中的一個節點：狀態、入參的來源與值、那次執行。"""

    index: int
    id: str
    scene_id: str
    scene_name: str
    revision: int
    status: NodeStatus
    sources: dict[str, dict[str, object]]
    """入參名稱 → 來源（rpa_core.workflow.InputSource 的 JSON），依場景檔的順序。"""
    run: RunRecord | None = None
    """這個節點的執行；沿用的節點是原本那次執行。"""
    error: str | None = None
    """沒有開始執行的原因（例如綁定的值不符合入參規則）。"""

    def to_json(self) -> dict[str, object]:
        return {
            "index": self.index,
            "id": self.id,
            "sceneId": self.scene_id,
            "sceneName": self.scene_name,
            "revision": self.revision,
            "status": self.status,
            "sources": self.sources,
            "run": self.run.to_json() if self.run is not None else None,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class WorkflowRunRecord:
    """一次序列的執行（M6）。"""

    id: str
    workflow_id: int | None
    workflow_name: str
    workflow_version: int
    status: WorkflowRunStatus
    engine: str | None
    headless: bool
    error: str | None
    failed_node: str | None
    resumed_from: str | None
    cancel_requested: bool
    created_at: datetime
    finished_at: datetime | None
    nodes: tuple[WorkflowNodeState, ...] = ()
    target: Target = "local"
    worker_id: str | None = None
    """第一個節點由哪台 worker 領取，後面的節點都給它（M9a）。"""
    purpose: str = "validation"
    """validation（驗證某個版本）或 execution（執行發布的版本）；M11 PR 2。"""
    workflow_code: str | None = None

    @property
    def finished(self) -> bool:
        return self.status != "running"

    @property
    def passed_count(self) -> int:
        return sum(node.status in ("passed", "reused") for node in self.nodes)

    @property
    def resumable(self) -> bool:
        """停在某個節點（失敗、逾時、取消、需要登入），可以從那個節點繼續。"""
        return self.finished and self.status != "passed" and self.failed_node is not None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workflowId": self.workflow_id,
            "workflowName": self.workflow_name,
            "workflowVersion": self.workflow_version,
            "status": self.status,
            "engine": self.engine,
            "headless": self.headless,
            "error": self.error,
            "failedNode": self.failed_node,
            "resumedFrom": self.resumed_from,
            "cancelRequested": self.cancel_requested,
            "createdAt": _iso(self.created_at),
            "finishedAt": _iso(self.finished_at),
            "finished": self.finished,
            "resumable": self.resumable,
            "nodes": [node.to_json() for node in self.nodes],
            "target": self.target,
            "workerId": self.worker_id,
            "purpose": self.purpose,
            "workflowCode": self.workflow_code,
        }


@dataclass(frozen=True, slots=True)
class CompositeRevisionRecord:
    """組合場景的一個版本（M11 PR 2）。"""

    number: int
    content_hash: str
    status: RevisionStatus
    verified: bool
    problem: str | None
    note: str | None
    created_at: datetime
    published_at: datetime | None
    published: bool

    def to_json(self) -> dict[str, object]:
        return {
            "number": self.number,
            "contentHash": self.content_hash,
            "status": self.status,
            "verified": self.verified,
            "problem": self.problem,
            "note": self.note,
            "createdAt": _iso(self.created_at),
            "publishedAt": _iso(self.published_at),
            "published": self.published,
        }


DependencyStatus = Literal["complete", "warnings", "incomplete"]
"""組合場景的依賴：完整、有提醒（可以執行）、不完整（不能執行）。"""


@dataclass(frozen=True, slots=True)
class DependencyItem:
    """組合場景依賴的一個問題（任務紀錄第 7 節）：哪個版本、哪個領域與場景、怎麼補全。"""

    level: Literal["error", "warning"]
    code: str
    message: str
    revision: int
    domain: str | None = None
    scene: str | None = None
    action: str | None = None
    """補全的方式：add_domain、pull、reload_domain、login、secrets、resave。"""
    source: dict[str, str] | None = None
    """add_domain 時，依賴的領域從哪裡取得（pack.yaml requires 的 source：url、directory、
    branch），用來預填「從 git 新增」；M11 收尾。"""

    def to_json(self) -> dict[str, object]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "revision": self.revision,
            "domain": self.domain,
            "scene": self.scene,
            "action": self.action,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class WorkerRecord:
    """一台遠端 worker（M9a）。"""

    id: str
    name: str
    status: WorkerStatus
    disabled: bool
    created_at: datetime
    last_seen_at: datetime | None
    current_run: str | None
    protocol: int | None
    fingerprint: str | None
    same_version: bool
    """程式指紋和管理 Portal 相同（還沒上線過時視為相同）。"""
    os: str | None
    python: str | None
    host: str | None
    browsers: tuple[str, ...]
    display: bool
    version: str | None = None
    """App 的版本（M10.1；舊版 worker 沒有回報）。"""

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "disabled": self.disabled,
            "createdAt": _iso(self.created_at),
            "lastSeenAt": _iso(self.last_seen_at),
            "currentRun": self.current_run,
            "protocol": self.protocol,
            "fingerprint": self.fingerprint,
            "sameVersion": self.same_version,
            "os": self.os,
            "python": self.python,
            "host": self.host,
            "browsers": list(self.browsers),
            "display": self.display,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RecorderRecord:
    """一台錄製端（M10.2）：錄製、逐步調試、人工登入的瀏覽器開在這台。"""

    id: str
    name: str
    status: RecorderStatus
    disabled: bool
    created_at: datetime
    last_seen_at: datetime | None
    protocol: int | None
    fingerprint: str | None
    same_version: bool
    """程式指紋和管理 Portal 相同（還沒上線過時視為相同）。"""
    version: str | None
    os: str | None
    host: str | None
    browsers: tuple[str, ...]
    display: bool
    active: int
    """這台正在執行的互動子程序（錄製、調試、人工登入）數量。"""

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": "recorder",
            "status": self.status,
            "disabled": self.disabled,
            "createdAt": _iso(self.created_at),
            "lastSeenAt": _iso(self.last_seen_at),
            "protocol": self.protocol,
            "fingerprint": self.fingerprint,
            "sameVersion": self.same_version,
            "version": self.version,
            "os": self.os,
            "host": self.host,
            "browsers": list(self.browsers),
            "display": self.display,
            "active": self.active,
        }
