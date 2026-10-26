"""資料庫：連線、共用欄位型別、遷移。規則見 ADR 0008。

- SQLite（預設）與 PostgreSQL 共用模型與遷移；只用兩邊都支援的寫法。
- 時間一律以 UTC 存放（SQLite 不保存時區，讀回來時補上）。
- SQLite 每個連線都開啟外鍵檢查與 WAL 模式。
- 啟動時執行 Alembic 遷移到最新版本（:func:`upgrade`）；遷移前先看有沒有要套用的
  （:func:`migration_status`），有的話 SQLite 先備份（ADR 0018，rpa_server.updates）。
"""

from datetime import UTC, datetime
from importlib.resources import as_file, files
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, DateTime, Engine, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.types import TypeDecorator

__all__ = [
    "NAMING_CONVENTION",
    "JsonType",
    "UtcDateTime",
    "create_db_engine",
    "migration_status",
    "upgrade",
]

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


def migration_status(engine: Engine) -> tuple[bool, bool]:
    """(有沒有還沒套用的遷移, 資料庫是不是已經有版本)；全新的資料庫是 (True, False)。"""
    with as_file(files("rpa_server").joinpath("migrations")) as location:
        config = Config()
        config.set_main_option("script_location", str(location))
        heads = set(ScriptDirectory.from_config(config).get_heads())
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return current != heads, bool(current)


def upgrade(engine: Engine) -> None:
    """把資料庫遷移到最新版本（rpa_server/migrations）。

    SQLite 的 batch 遷移會重建資料表（建新表、搬資料、刪舊表）。開著外鍵檢查時，刪除被其他表
    參照、而且有資料的舊表會失敗（全新的資料庫沒有資料，所以只有升級舊資料時才會遇到）。
    遷移期間關閉外鍵檢查，完成後用 ``PRAGMA foreign_key_check`` 確認沒有斷掉的參照，再打開。
    """
    sqlite = engine.dialect.name == "sqlite"
    with as_file(files("rpa_server").joinpath("migrations")) as location:
        config = Config()
        config.set_main_option("script_location", str(location))
        with engine.connect() as connection:
            if sqlite:
                # 在交易裡改 foreign_keys 不會生效：先在交易外面關掉
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
            try:
                with connection.begin():
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                    if sqlite:
                        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                        if broken:
                            raise RuntimeError(
                                f"遷移後有 {len(broken)} 筆外鍵參照不存在：{broken[:5]}"
                            )
            finally:
                if sqlite:
                    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                    connection.commit()
