"""資料庫：連線、共用欄位型別、遷移。規則見 ADR 0008。

- SQLite（預設）與 PostgreSQL 共用模型與遷移；只用兩邊都支援的寫法。
- 時間一律以 UTC 存放（SQLite 不保存時區，讀回來時補上）。
- SQLite 每個連線都開啟外鍵檢查與 WAL 模式。
- 啟動時執行 Alembic 遷移到最新版本（:func:`upgrade`）。
"""

from datetime import UTC, datetime
from importlib.resources import as_file, files
from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, DateTime, Engine, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.types import TypeDecorator

__all__ = ["NAMING_CONVENTION", "JsonType", "UtcDateTime", "create_db_engine", "upgrade"]

NAMING_CONVENTION: Final = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""約束的命名規則：名稱固定，SQLite 的 batch 遷移才找得到要改的約束。"""

JsonType = JSON().with_variant(JSONB(), "postgresql")
"""JSON 欄位：PostgreSQL 存成 JSONB；查詢不使用 JSONB 專屬運算子。"""


class UtcDateTime(TypeDecorator[datetime]):
    """有時區的時間，一律換成 UTC 存放；讀回來一定帶 UTC 時區。"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("時間必須帶時區（請用 datetime.now(UTC)）")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def create_db_engine(url: str) -> Engine:
    """建立連線；SQLite 會開啟外鍵檢查、WAL 與等待鎖的時間。"""
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection: DBAPIConnection, record: ConnectionPoolEntry) -> None:  # pyright: ignore[reportUnusedFunction]
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


def upgrade(engine: Engine) -> None:
    """把資料庫遷移到最新版本（rpa_server/migrations）。"""
    with as_file(files("rpa_server").joinpath("migrations")) as location:
        config = Config()
        config.set_main_option("script_location", str(location))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
