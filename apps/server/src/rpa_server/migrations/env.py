"""Alembic 的執行環境：伺服器啟動時由 rpa_server.db.upgrade 呼叫，也可以用 alembic 命令。

``config.attributes["connection"]`` 有連線時直接使用（伺服器與測試）；沒有時讀
``sqlalchemy.url``（apps/server/alembic.ini，開發者產生新遷移用）。
SQLite 改資料表結構要用 batch 模式（render_as_batch）。
"""

from alembic import context
from sqlalchemy import Connection

from rpa_server.db import create_db_engine
from rpa_server.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        render_as_batch=True,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _online() -> None:
    connection: object = config.attributes.get("connection")
    if isinstance(connection, Connection):
        _run(connection)
        return
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("沒有資料庫連線：請在 alembic.ini 設定 sqlalchemy.url")
    engine = create_db_engine(url)
    try:
        with engine.begin() as own:
            _run(own)
    finally:
        engine.dispose()


if context.is_offline_mode():
    _offline()
else:
    _online()
