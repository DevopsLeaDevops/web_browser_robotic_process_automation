"""資料庫遷移：從空資料庫升到最新版，結果要和模型完全一致；也能降回去再升上來。"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from rpa_server.app import STATIC
from rpa_server.config import sqlite_url
from rpa_server.db import create_db_engine, upgrade
from rpa_server.models import Base

MIGRATIONS = STATIC.parent / "migrations"


def test_migrations_match_models(tmp_path: Path) -> None:
    engine = create_db_engine(sqlite_url(tmp_path / "rpa.db"))
    try:
        upgrade(engine)
        upgrade(engine)  # 已經是最新版時什麼都不做
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            differences = compare_metadata(context, Base.metadata)
        assert differences == []
        assert sorted(inspect(engine).get_table_names()) == [
            "alembic_version",
            "revisions",
            "runs",
            "scenes",
        ]
    finally:
        engine.dispose()


def test_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    engine = create_db_engine(sqlite_url(tmp_path / "rpa.db"))
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    try:
        upgrade(engine)
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        upgrade(engine)
        assert "runs" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_sqlite_connections_enforce_foreign_keys(tmp_path: Path) -> None:
    engine = create_db_engine(sqlite_url(tmp_path / "rpa.db"))
    try:
        with engine.connect() as connection:
            pragma = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            journal = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert pragma == 1
        assert journal == "wal"
    finally:
        engine.dispose()
