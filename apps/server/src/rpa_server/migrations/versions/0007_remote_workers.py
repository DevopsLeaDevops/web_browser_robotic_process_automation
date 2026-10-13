"""遠端 worker workers、設定 settings；執行與序列的執行記下執行位置與 worker（M9a）

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("info", JsonType, nullable=False),
        sa.Column("current_run", sa.String(120), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("last_seen_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_workers"),
        sa.UniqueConstraint("token_hash", name="uq_workers_token_hash"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", JsonType, nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
    )
    with op.batch_alter_table("runs") as batch:
        # 之前的執行都在本機
        batch.add_column(sa.Column("target", sa.String(10), nullable=False, server_default="local"))
        batch.add_column(sa.Column("required_worker", sa.String(64), nullable=True))
        batch.add_column(sa.Column("worker_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("lease_until", UtcDateTime(), nullable=True))
        batch.create_index("ix_runs_worker_id", ["worker_id"])
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(sa.Column("target", sa.String(10), nullable=False, server_default="local"))
        batch.add_column(sa.Column("worker_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("worker_id")
        batch.drop_column("target")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_worker_id")
        batch.drop_column("lease_until")
        batch.drop_column("worker_id")
        batch.drop_column("required_worker")
        batch.drop_column("target")
    op.drop_table("settings")
    op.drop_table("workers")
