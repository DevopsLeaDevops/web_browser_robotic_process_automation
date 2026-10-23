"""對外 Agent API（M14，ADR 0017）：API 用戶端 api_clients、稽核 api_audit、runs.client_id、
錄製端的 recorders.allow_agent 與 agent_headless_only

既有的錄製端都不允許 Agent 調試；既有的執行都不是 Agent 觸發的。

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_clients",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("scopes", JsonType, nullable=False),
        sa.Column("domains", JsonType, nullable=True),
        sa.Column("recorders", JsonType, nullable=False),
        sa.Column("target", sa.String(10), nullable=True),
        sa.Column("workers", JsonType, nullable=True),
        sa.Column("max_debug_sessions", sa.Integer(), nullable=False),
        sa.Column("max_queued_runs", sa.Integer(), nullable=False),
        sa.Column("page_content", sa.Boolean(), nullable=False),
        sa.Column("allowed_ips", JsonType, nullable=True),
        sa.Column("expires_at", UtcDateTime(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("last_used_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_api_clients"),
        sa.UniqueConstraint("key_hash", name="uq_api_clients_key_hash"),
    )
    op.create_table(
        "api_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", UtcDateTime(), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("client_name", sa.String(100), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("target", sa.String(300), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(60), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_api_audit"),
    )
    op.create_index("ix_api_audit_at", "api_audit", ["at"])
    op.create_index("ix_api_audit_client_id", "api_audit", ["client_id"])
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("client_id", sa.String(64), nullable=True))
        batch.create_index("ix_runs_client_id", ["client_id"])
    with op.batch_alter_table("recorders") as batch:
        # 既有的錄製端都不允許 Agent 調試
        batch.add_column(
            sa.Column("allow_agent", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column(
                "agent_headless_only", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("recorders") as batch:
        batch.drop_column("agent_headless_only")
        batch.drop_column("allow_agent")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_client_id")
        batch.drop_column("client_id")
    op.drop_index("ix_api_audit_client_id", table_name="api_audit")
    op.drop_index("ix_api_audit_at", table_name="api_audit")
    op.drop_table("api_audit")
    op.drop_table("api_clients")
