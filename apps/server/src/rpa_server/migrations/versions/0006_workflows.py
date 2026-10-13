"""自由試驗場的序列 workflows、序列的執行 workflow_runs；執行加上所屬的序列執行與節點（M6）

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition", JsonType, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workflows"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=True),
        sa.Column("workflow_name", sa.String(200), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("definition", JsonType, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("engine", sa.String(20), nullable=True),
        sa.Column("headless", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("failed_node", sa.String(64), nullable=True),
        sa.Column("reused", JsonType, nullable=False),
        sa.Column("resumed_from", sa.String(120), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("finished_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency_key"),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("workflow_run_id", sa.String(120), nullable=True))
        batch.add_column(sa.Column("node_id", sa.String(64), nullable=True))
        batch.create_index("ix_runs_workflow_run_id", ["workflow_run_id"])
        batch.create_foreign_key(
            "fk_runs_workflow_run_id_workflow_runs", "workflow_runs", ["workflow_run_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("fk_runs_workflow_run_id_workflow_runs", type_="foreignkey")
        batch.drop_index("ix_runs_workflow_run_id")
        batch.drop_column("node_id")
        batch.drop_column("workflow_run_id")
    op.drop_index("ix_workflow_runs_created_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
