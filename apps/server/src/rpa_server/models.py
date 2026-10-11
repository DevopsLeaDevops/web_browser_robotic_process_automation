"""資料庫模型：場景 scenes、版本 revisions、執行 runs。

版本內容（場景檔與腳本）不放資料庫，放在資料目錄（storage.py）；資料庫只記雜湊與狀態。
改了模型就要新增遷移（rpa_server/migrations/versions），測試會比對兩者是否一致。
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rpa_server.db import NAMING_CONVENTION, JsonType, UtcDateTime

__all__ = ["Base", "Revision", "Run", "Scene"]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Scene(Base):
    """場景：id 就是 DSL 的 id，永不重用（只能封存）。名稱與分類取自最新版本。"""

    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
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
