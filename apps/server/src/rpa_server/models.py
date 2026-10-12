"""資料庫模型：場景 scenes、版本 revisions、執行 runs；M4 加上登入角色 roles 與錄製 recordings。

版本內容（場景檔與腳本）不放資料庫，放在資料目錄（storage.py）；資料庫只記雜湊與狀態。
改了模型就要新增遷移（rpa_server/migrations/versions），測試會比對兩者是否一致。
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, MetaData, String, Text, UniqueConstraint, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rpa_server.db import NAMING_CONVENTION, JsonType, UtcDateTime

__all__ = ["Base", "Domain", "Recording", "Revision", "Role", "Run", "Scene"]


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
    url: Mapped[str | None] = mapped_column(String(2000))
    engine: Mapped[str] = mapped_column(String(20))
    role_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)
    """recording → done／failed／cancelled。"""
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
