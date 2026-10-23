"""資料庫遷移：從空資料庫升到最新版，結果要和模型完全一致；也能降回去再升上來；
有資料的舊資料庫也升得上來（SQLite 的 batch 遷移會重建資料表，不能被外鍵檢查擋下）。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.engine.interfaces import ReflectedColumn

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
            "api_audit",
            "api_clients",
            "device_invites",
            "domains",
            "recorders",
            "recordings",
            "revisions",
            "roles",
            "runs",
            "scenes",
            "settings",
            "workers",
            "workflow_revisions",
            "workflow_runs",
            "workflows",
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


def _upgrade_to(engine: Engine, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _sample(column: ReflectedColumn) -> object:
    """非空欄位的樣本值（依欄位型別）。"""
    try:
        kind: type[object] = column["type"].python_type
    except NotImplementedError:
        return "x"
    if kind is bool:
        return False
    if kind is int:
        return 1
    if kind is float:
        return 1.0
    if kind is datetime:
        return datetime(2026, 10, 1, tzinfo=UTC).strftime("%Y-%m-%d %H:%M:%S.000000")
    if kind in (dict, list):
        return "{}"
    return "x"


def _insert(connection: Connection, table: str, **values: object) -> None:
    """插入一列：沒給的非空欄位填樣本值（舊版的欄位從資料庫讀，不寫死）。"""
    inspector = inspect(connection)
    keys = set(inspector.get_pk_constraint(table)["constrained_columns"])
    row = dict(values)
    for column in inspector.get_columns(table):
        name = str(column["name"])
        if name in row or column["nullable"] or column.get("default") is not None:
            continue
        if name in keys and _sample(column) == 1:
            continue  # 整數主鍵自動編號
        row[name] = _sample(column)
    names = ", ".join(row)
    placeholders = ", ".join(f":{name}" for name in row)
    connection.execute(text(f"INSERT INTO {table} ({names}) VALUES ({placeholders})"), row)


@pytest.mark.parametrize("start", ["0001", "0009"])
def test_old_database_with_data_upgrades(tmp_path: Path, start: str) -> None:
    """有資料的舊資料庫：被參照的資料表重建時不能因為外鍵檢查失敗，資料都要留著。"""
    engine = create_db_engine(sqlite_url(tmp_path / "rpa.db"))
    try:
        _upgrade_to(engine, start)
        with engine.begin() as connection:
            tables = set(inspect(connection).get_table_names())
            if "domains" in tables:
                _insert(connection, "domains", id="lab")
            _insert(connection, "scenes", id="ba-001")
            _insert(connection, "revisions", scene_id="ba-001", number=1)
            revision = connection.execute(text("SELECT id FROM revisions")).scalar_one()
            _insert(connection, "runs", id="ba-001-run", scene_id="ba-001", revision_id=revision)
            if "roles" in tables:
                _insert(connection, "roles", id="lab-user")
            if "workflows" in tables:
                _insert(connection, "workflows")
                workflow = connection.execute(text("SELECT id FROM workflows")).scalar_one()
                _insert(connection, "workflow_runs", id="wf1-run", workflow_id=workflow)
        upgrade(engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM runs")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM revisions")).scalar_one() == 1
            if start == "0009":
                code = connection.execute(text("SELECT code FROM workflows")).scalar_one()
                assert code == "wf-1"
                assert connection.execute(text("SELECT count(*) FROM roles")).scalar_one() == 1
            # 遷移結束後外鍵檢查要開回來
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    finally:
        engine.dispose()


def test_agent_api_migration_keeps_recorders_closed(tmp_path: Path) -> None:
    """M14：既有的錄製端都不允許 Agent 調試，既有的執行都不是 Agent 觸發的。"""
    engine = create_db_engine(sqlite_url(tmp_path / "rpa.db"))
    try:
        _upgrade_to(engine, "0014")
        with engine.begin() as connection:
            _insert(connection, "recorders", id="mac-01", token_hash="h")
            _insert(connection, "domains", id="lab")
            _insert(connection, "scenes", id="ba-001")
            _insert(connection, "revisions", scene_id="ba-001", number=1)
            revision = connection.execute(text("SELECT id FROM revisions")).scalar_one()
            _insert(connection, "runs", id="ba-001-run", scene_id="ba-001", revision_id=revision)
        upgrade(engine)
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT allow_agent, agent_headless_only FROM recorders")
            ).one()
            assert tuple(row) == (0, 0)
            assert connection.execute(text("SELECT client_id FROM runs")).scalar_one() is None
            assert connection.execute(text("SELECT count(*) FROM api_clients")).scalar_one() == 0
    finally:
        engine.dispose()
