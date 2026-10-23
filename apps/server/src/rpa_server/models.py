"""資料庫模型：場景 scenes、版本 revisions、執行 runs；M4 加上登入角色 roles 與錄製 recordings；
M6 加上自由試驗場的序列 workflows 與序列的執行 workflow_runs；
M9a 加上遠端 worker workers、設定 settings，執行記下執行位置與由哪台 worker 執行；
M10.1 加上裝置邀請 device_invites；M10.2 加上錄製端 recorders 與錄製的 device_id；
錄製端另外顯示的選單 recorders.menus（三段分工，2026-10-22）。
M14：對外 Agent API 的用戶端 api_clients 與稽核 api_audit；執行記下觸發的用戶端 runs.client_id，
錄製端加上允不允許 Agent 調試 recorders.allow_agent、agent_headless_only（ADR 0017）。

M11：場景、版本、角色的定義與驗證、發布紀錄都在領域資料夾（rpa_server.packs）；這幾張表是
資料夾的**索引**，載入時依資料夾重建。只在資料庫的欄位（網址覆寫、排序、登入檢查的結果）
不會被覆蓋；資料夾裡已經沒有的標為來源缺失（missing），執行紀錄引用的列不刪除。
版本內容（場景檔與腳本）不放資料庫；資料庫只記雜湊與狀態。
改了模型就要新增遷移（rpa_server/migrations/versions），測試會比對兩者是否一致。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rpa_server.db import NAMING_CONVENTION, JsonType, UtcDateTime

__all__ = [
    "ApiAudit",
    "ApiClient",
    "Base",
    "DeviceInvite",
    "Domain",
    "Recording",
    "RemoteWorker",
    "Revision",
    "Role",
    "Run",
    "Scene",
    "Setting",
    "Workflow",
    "WorkflowRevision",
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
    problems: Mapped[list[dict[str, object]] | None] = mapped_column(JsonType)
    """最近一次載入領域資料夾發現的問題（M11，rpa_core.pack.PackIssue 的 JSON）。"""
    loaded_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    """最近一次載入領域資料夾的時間（M11）。"""
    source: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    """git 資料來源（M11 PR 3，rpa_server.gitsync.GitSource 的 JSON）：倉庫、分支、目錄、認證方式、
    使用者名稱、提交者、啟動時自動拉取。沒有就是本機領域。權杖與私鑰不在這裡（git/ 目錄）。"""
    sync: Mapped[dict[str, object] | None] = mapped_column(JsonType)
    """同步狀態（M11 PR 3）：上次同步的提交、上次看到的遠端提交、分支、錯誤、衝突的檔案、時間。"""


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
    missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """來源缺失（M11）：領域資料夾裡已經沒有這個場景；清單隱藏、不能執行，執行紀錄照樣保留。"""


class Revision(Base):
    """版本：內容不可變；status 是最近一次驗證的結果（M11 起依資料夾的驗證紀錄計算）。"""

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
    missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """來源缺失（M11）：資料夾裡已經沒有這個版本。"""
    problem: Mapped[str | None] = mapped_column(String(60))
    """讓這個版本不能執行、不能發布的問題代碼（M11，例如內容和版本說明檔的雜湊不同）。"""
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """有雜湊相符的通過驗證紀錄（M11，發布門檻；不管是哪一台伺服器驗證的）。"""


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
    video_seconds: Mapped[float | None] = mapped_column(Float)
    """錄影的長度（M12）；沒有錄影時是 None。影片在執行目錄的 video.webm。"""
    video_bytes: Mapped[int | None] = mapped_column(BigInteger)
    video_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """釘選：不依保留規則刪除錄影。"""
    video_deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    """錄影被刪除的時間；運行紀錄本身留著。"""
    video_deleted_reason: Mapped[str | None] = mapped_column(String(20))
    """刪除的原因：expired（超過保留天數）、quota（超過總量上限）。"""
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    """由哪個 API 用戶端觸發（M14）；人在 Portal 觸發的是 None。用戶端刪除後仍保留，不設外鍵。"""


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
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domains.id"), index=True)
    """定義放在哪個領域資料夾的 roles/（M11）。"""
    missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """來源缺失（M11）：領域資料夾裡已經沒有這個角色。"""


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
    device_id: Mapped[str | None] = mapped_column(String(64))
    """在哪台錄製端錄製（M10.2）；在伺服器這台錄製或貼上的是 None。"""
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Workflow(Base):
    """組合場景（M6）：已發布場景的固定版本，上游出參綁定到下游入參。

    M11 PR 2 起定義在領域資料夾的 composites/<code>/，每次改定義都是新版本（version 是最新的
    版本號碼，存檔要帶它）；這裡是索引，definition 是最新版本的定義（編輯頁用）。
    id 只在這台伺服器有意義（網址用）；跨伺服器認得的是 code。
    """

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[dict[str, object]] = mapped_column(JsonType)
    version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())
    code: Mapped[str] = mapped_column(String(64), unique=True)
    """英數代號（D2），也是資料夾的名稱；舊的組合場景是 wf-<id>。"""
    domain_id: Mapped[str | None] = mapped_column(ForeignKey("domains.id"), index=True)
    published_number: Mapped[int | None] = mapped_column()
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """來源缺失：領域資料夾裡已經沒有這個組合場景。"""


class WorkflowRevision(Base):
    """組合場景的一個版本（M11 PR 2）：資料夾的索引；status 是最近一次驗證紀錄的結果。"""

    __tablename__ = "workflow_revisions"
    __table_args__ = (UniqueConstraint("workflow_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), index=True)
    number: Mapped[int] = mapped_column()
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    problem: Mapped[str | None] = mapped_column(String(60))
    missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


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
    purpose: Mapped[str] = mapped_column(
        String(20), default="validation", server_default="validation"
    )
    """validation（驗證某個版本，結果寫進驗證紀錄）或 execution（執行發布的版本）；M11 PR 2。"""
    workflow_code: Mapped[str | None] = mapped_column(String(64))
    """組合場景的代號（執行當時的）；workflow_version 是跑的版本號碼。"""
    workflow_hash: Mapped[str | None] = mapped_column(String(64))
    """跑的版本的雜湊（definition 是解析過來源的快照，雜湊和版本不同）；驗證紀錄記它。
    M11 PR 2 之前的執行（與它們的重跑）沒有，不寫驗證紀錄。"""


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


class Recorder(Base):
    """登記的錄製端（M10.2，ADR 0014）：錄製、逐步調試、人工登入的瀏覽器開在這台。

    和 worker 分開存：錄製端不領取執行，worker 的分派完全不受影響。代號和 worker 共用一個
    命名空間（邀請以代號找裝置），新增時兩邊都不能重複。
    """

    __tablename__ = "recorders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    info: Mapped[dict[str, object]] = mapped_column(JsonType)
    """上線時回報的資訊：協定版本、程式指紋、App 版本、作業系統、瀏覽器、能不能顯示視窗。"""
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    menus: Mapped[list[str] | None] = mapped_column(JsonType)
    """透過這台打開管理 Portal 時另外顯示的第一級選單（叢集管理、管理後台；預設都不顯示）。"""
    allow_agent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    """允許 API 用戶端（Agent）在這台開調試瀏覽器（M14）；預設不允許。"""
    agent_headless_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    """Agent 在這台只能用無頭模式（不在操作的人面前開視窗）。"""


class DeviceInvite(Base):
    """裝置邀請（M10.1，ADR 0014）：一次性、限時、限定 App 種類；資料庫只存代碼的雜湊。

    ``device_id`` 是要配對的裝置：Worker 是 workers 的代號（M10.2 的錄製端沿用這張表）。
    """

    __tablename__ = "device_invites"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    app: Mapped[str] = mapped_column(String(16))
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Setting(Base):
    """管理 Portal 的設定（M9a：預設執行位置）。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JsonType)


class ApiClient(Base):
    """對外 Agent API 的用戶端（M14，ADR 0017）：一個 Agent 系統一把金鑰，資料庫只存金鑰的雜湊。

    清單類的欄位（權限範圍、領域、錄製端、Worker）是 JSON 陣列；``domains``、``workers``
    是 None 時不限。
    """

    __tablename__ = "api_clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(20))
    """金鑰的開頭幾個字，管理後台用來認出是哪一把（不足以使用）。"""
    scopes: Mapped[list[str]] = mapped_column(JsonType)
    domains: Mapped[list[str] | None] = mapped_column(JsonType)
    recorders: Mapped[list[str]] = mapped_column(JsonType)
    target: Mapped[str | None] = mapped_column(String(10))
    """驗證與執行的位置（local、remote、any）；None 時跟隨伺服器的預設執行位置。"""
    workers: Mapped[list[str] | None] = mapped_column(JsonType)
    """可以指定的 Worker（local 是伺服器本機）；None 時不限。"""
    max_debug_sessions: Mapped[int] = mapped_column()
    max_queued_runs: Mapped[int] = mapped_column()
    page_content: Mapped[bool] = mapped_column(Boolean, default=False)
    """回傳頁面內容：截圖、頁面結構、錄影與報告能不能給這個用戶端。"""
    allowed_ips: Mapped[list[str] | None] = mapped_column(JsonType)
    """允許的來源 IP 或網段；None 時不限。"""
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class ApiAudit(Base):
    """API 用戶端的寫入請求（M14）：只增不改。用戶端刪除後紀錄仍保留，所以不設外鍵。"""

    __tablename__ = "api_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    client_name: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(200))
    """路由的路徑樣式，例如 ``/scenes/{scene_id}/revisions``。"""
    target: Mapped[str | None] = mapped_column(String(300))
    """操作的對象：路徑參數的值（場景代號、版本、工作階段、運行編號）。"""
    status: Mapped[int] = mapped_column()
    code: Mapped[str | None] = mapped_column(String(60))
    """失敗時的錯誤代碼。"""
    ip: Mapped[str | None] = mapped_column(String(64))
