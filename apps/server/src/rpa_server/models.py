"""資料庫模型：場景 scenes、版本 revisions、執行 runs；M4 加上登入角色 roles 與錄製 recordings；
M6 加上自由試驗場的序列 workflows 與序列的執行 workflow_runs；
M9a 加上遠端 worker workers、設定 settings，執行記下執行位置與由哪台 worker 執行。

版本內容（場景檔與腳本）不放資料庫，放在資料目錄（storage.py）；資料庫只記雜湊與狀態。
改了模型就要新增遷移（rpa_server/migrations/versions），測試會比對兩者是否一致。
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, MetaData, String, Text, UniqueConstraint, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rpa_server.db import NAMING_CONVENTION, JsonType, UtcDateTime

__all__ = [
    "Base",
    "Domain",
    "Recording",
    "RemoteWorker",
    "Revision",
    "Role",
    "Run",
    "Scene",
    "Setting",
    "Workflow",
    "WorkflowRun",
]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Domain(Base):
    """領域：場景管理的二級選單，依目標系統或業務劃分場景。"""

    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


class Scene(Base):
    """場景：id 就是 DSL 的 id，永不重用（只能封存）。名稱與分類取自最新版本。"""

    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domains.id"), index=True)
    base_url: Mapped[str | None] = mapped_column(String(2000))
    latest_number: Mapped[int] = mapped_column(default=0)
    published_number: Mapped[int | None] = mapped_column()
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class Revision(Base):
    """版本：內容不可變；status 是最近一次驗證的結果。"""

    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("scene_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    number: Mapped[int] = mapped_column()
    content_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Run(Base):
    """一次執行：驗證或正式執行。場景名稱與分類記下當時的值，報告篩選用。"""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisions.id"), index=True)
    revision_number: Mapped[int] = mapped_column()
    scene_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    stage: Mapped[str | None] = mapped_column(String(20))
    engine: Mapped[str | None] = mapped_column(String(20))
    base_url: Mapped[str | None] = mapped_column(String(2000))
    headless: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    """無頭模式（不顯示瀏覽器視窗）；False 是有頭模式。之前的執行都是無頭。"""
    input: Mapped[dict[str, object]] = mapped_column(JsonType)
    output: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    scenario_hash: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    workflow_run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    """屬於哪一次序列的執行（M6，目的是 workflow）；單獨的驗證與執行是 None。"""
    node_id: Mapped[str | None] = mapped_column(String(64))
    """序列裡的節點代號。"""
    target: Mapped[str] = mapped_column(String(10), default="local", server_default="local")
    """執行位置（M9a）：local（管理 Portal 這台電腦）、remote（遠端 worker）、
    any（誰有空誰執行）。"""
    required_worker: Mapped[str | None] = mapped_column(String(64))
    """只能由這台 worker 執行（試驗場序列的後續節點跟著第一個節點）；local 代表本機。"""
    worker_id: Mapped[str | None] = mapped_column(String(64), index=True)
    """實際由哪台 worker 執行；local 代表本機。worker 刪除後紀錄仍保留，所以不設外鍵。"""
    lease_until: Mapped[datetime | None] = mapped_column(UtcDateTime())
    """遠端 worker 的租約：過了這個時間還沒報到，執行標為「worker 失聯」。"""


class Role(Base):
    """登入角色：一個測試帳號怎麼登入、怎麼判斷已登入（M4）。

    登入狀態（storageState）不放資料庫，放在資料目錄的 roles/<id>/state.json，只有本人能讀寫。
    """

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    login_url: Mapped[str] = mapped_column(String(2000))
    check_url: Mapped[str | None] = mapped_column(String(2000))
    """確認是否已登入時打開的網址；沒有就用登入網址。"""
    check_locator: Mapped[dict[str, object]] = mapped_column(JsonType)
    """已登入時看得到的元素（DSL 定位器）。"""
    engine: Mapped[str] = mapped_column(String(20))
    """人工登入時用的瀏覽器。"""
    auto_login: Mapped[str | None] = mapped_column(Text)
    """自動登入步驟（DSL 步驟清單的 YAML）；沒有代表只能人工登入。"""
    status: Mapped[str] = mapped_column(String(20))
    """最近一次知道的狀態：none（還沒登入過）、logged_in、needs_login、unknown（檢查出錯）。"""
    message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class Recording(Base):
    """一次錄製或匯入的錄製稿：轉換成哪個場景的哪個版本（M4）。

    遮罩過密碼的原始錄製稿與轉換結果放在資料目錄的 recordings/<id>/。
    """

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(64), index=True)
    """目標場景；新場景在轉換成功時才建立，所以不設外鍵。"""
    scene_name: Mapped[str] = mapped_column(String(200))
    new_scene: Mapped[bool] = mapped_column(Boolean)
    domain_id: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(100))
    revision_number: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(20))
    """codegen（在這台電腦錄製）或 import（貼上錄製稿）。"""
    mode: Mapped[str] = mapped_column(String(20), server_default="new")
    """new（新場景）、continue（接在既有步驟後面）、replace（既有場景整份換成錄製的草稿）。"""
    base_revision: Mapped[int | None] = mapped_column()
    """接著錄製時，執行的是哪一個版本的步驟；存檔時以它為基礎（期間有新版本就不存）。"""
    url: Mapped[str | None] = mapped_column(String(2000))
    engine: Mapped[str] = mapped_column(String(20))
    role_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)
    """recording → done／failed／cancelled。"""
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Workflow(Base):
    """自由試驗場的一個序列（M6）：已發布場景的固定版本，上游出參綁定到下游入參。

    定義是 rpa_core.workflow 的 JSON；每次存檔 version 加一，存檔要帶目前的 version。
    """

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[dict[str, object]] = mapped_column(JsonType)
    version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class WorkflowRun(Base):
    """一次序列的執行（M6）。每個節點是一筆 runs（目的 workflow），依序排入佇列。

    定義存一份開始時的快照：之後改序列不影響這次執行，重新執行與從失敗的節點繼續也用它。
    序列刪除後執行紀錄仍然保留，所以 workflow_id 不設外鍵。
    """

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    workflow_id: Mapped[int | None] = mapped_column(index=True)
    workflow_name: Mapped[str] = mapped_column(String(200))
    workflow_version: Mapped[int] = mapped_column()
    definition: Mapped[dict[str, object]] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), index=True)
    """running → passed／failed／timed_out／cancelled／needs_login；停在哪個節點見 failed_node。"""
    engine: Mapped[str | None] = mapped_column(String(20))
    headless: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    failed_node: Mapped[str | None] = mapped_column(String(64))
    reused: Mapped[dict[str, object]] = mapped_column(JsonType)
    """從失敗的節點繼續時沿用的節點：節點代號 → 原本那次通過的執行編號。"""
    resumed_from: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    target: Mapped[str] = mapped_column(String(10), default="local", server_default="local")
    """執行位置（M9a），每個節點都一樣。"""
    worker_id: Mapped[str | None] = mapped_column(String(64))
    """第一個節點由哪台 worker 領取，後面的節點就固定給它（測試網站的資料、登入狀態一致）。"""


class RemoteWorker(Base):
    """登記的遠端 worker（M9a）：一台 worker 機器一個權杖，資料庫只存權杖的雜湊。"""

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    info: Mapped[dict[str, object]] = mapped_column(JsonType)
    """上線時回報的資訊：協定版本、程式指紋、作業系統、瀏覽器、能不能顯示視窗。"""
    current_run: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Setting(Base):
    """管理 Portal 的設定（M9a：預設執行位置）。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JsonType)
