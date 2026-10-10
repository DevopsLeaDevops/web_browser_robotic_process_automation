"""管理介面的資料：場景、版本、執行的狀態與給 API、頁面使用的唯讀紀錄。

服務層（services.py）從資料庫讀出後轉成這裡的紀錄，API 與頁面只碰這些紀錄、不碰資料庫物件。

狀態：

- 版本：草稿 draft → 驗證中 validating → 通過 passed／失敗 failed；發布後場景指向該版本。
  改內容就是新版本，舊版本的驗證結果不能拿來發布新內容。
- 執行：queued → running → passed／failed／timed_out／cancelled。
- 執行目的：驗證 validation（任何版本，結果決定版本能不能發布）、執行 execution（只用已發布版本）。
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from rpa_core.dsl import Issue, format_issue

__all__ = [
    "ENGINES",
    "FINISHED",
    "PURPOSES",
    "RUN_STATUSES",
    "Engine",
    "Purpose",
    "RevisionRecord",
    "RevisionStatus",
    "RunRecord",
    "RunStatus",
    "SceneRecord",
    "Stats",
    "issue_json",
    "now",
]

RevisionStatus = Literal["draft", "validating", "passed", "failed"]
RunStatus = Literal["queued", "running", "passed", "failed", "timed_out", "cancelled"]
Purpose = Literal["validation", "execution"]
Engine = Literal["chromium", "firefox"]

RUN_STATUSES: Final[tuple[RunStatus, ...]] = (
    "queued",
    "running",
    "passed",
    "failed",
    "timed_out",
    "cancelled",
)
FINISHED: Final[frozenset[str]] = frozenset({"passed", "failed", "timed_out", "cancelled"})
PURPOSES: Final[tuple[Purpose, ...]] = ("validation", "execution")
ENGINES: Final[tuple[Engine, ...]] = ("chromium", "firefox")


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
class SceneRecord:
    id: str
    name: str
    category: str | None
    description: str | None
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
class Stats:
    scenes: int
    published: int
    runs: int
    passed: int
