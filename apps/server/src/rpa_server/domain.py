"""管理介面的資料：場景、版本、執行的狀態與給 API、頁面使用的唯讀紀錄。

服務層（services.py）從資料庫讀出後轉成這裡的紀錄，API 與頁面只碰這些紀錄、不碰資料庫物件。

狀態：

- 版本：草稿 draft → 驗證中 validating → 通過 passed／失敗 failed；發布後場景指向該版本。
  改內容就是新版本，舊版本的驗證結果不能拿來發布新內容。
- 執行：queued → running → passed／failed／timed_out／cancelled；場景要以角色登入而角色沒登入時
  是 needs_login（沒有執行任何步驟，登入後可以重新執行）。
- 執行目的：驗證 validation（任何版本，結果決定版本能不能發布）、執行 execution（只用已發布版本）。
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from rpa_core.dsl import Issue, format_issue

__all__ = [
    "DOMAIN_ID",
    "ENGINES",
    "FINISHED",
    "PURPOSES",
    "ROLE_STATUSES",
    "RUN_STATUSES",
    "DomainRecord",
    "Engine",
    "Purpose",
    "RecordingRecord",
    "RevisionRecord",
    "RevisionStatus",
    "RoleRecord",
    "RoleStatus",
    "RunRecord",
    "RunStatus",
    "SceneCard",
    "SceneRecord",
    "issue_json",
    "now",
]

RevisionStatus = Literal["draft", "validating", "passed", "failed"]
RunStatus = Literal[
    "queued", "running", "passed", "failed", "timed_out", "cancelled", "needs_login"
]
RoleStatus = Literal["none", "logged_in", "needs_login", "unknown"]
"""角色：還沒登入過、已登入、需要登入、不確定（檢查時出錯）。"""
Purpose = Literal["validation", "execution"]
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
PURPOSES: Final[tuple[Purpose, ...]] = ("validation", "execution")
ENGINES: Final[tuple[Engine, ...]] = ("chromium", "firefox")
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

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "position": self.position,
            "sceneCount": self.scene_count,
            "createdAt": _iso(self.created_at),
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
        }
