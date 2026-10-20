"""組合場景放進領域資料夾（M11 PR 2）：代號、版本、驗證與發布

組合場景有英數代號（舊的組合場景是 wf-<原數字>）、所在領域、目前發布的版本、封存與來源缺失；
每個版本一列（workflow_revisions，資料夾的索引）；組合場景的執行記下目的（驗證、執行）與代號。
檔案的部分（composites/<代號>/）在伺服器啟動時由 rpa_server.packs 寫入，不在遷移裡。

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("code", sa.String(64), nullable=True))
        batch.add_column(sa.Column("domain_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("published_number", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # 舊的組合場景：代號是 wf-<原數字>（D7）
    op.execute("UPDATE workflows SET code = 'wf-' || CAST(id AS VARCHAR(20))")
    with op.batch_alter_table("workflows") as batch:
        batch.alter_column("code", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint("uq_workflows_code", ["code"])
        batch.create_index("ix_workflows_domain_id", ["domain_id"])
        batch.create_foreign_key("fk_workflows_domain_id_domains", "domains", ["domain_id"], ["id"])
    op.create_table(
        "workflow_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("problem", sa.String(60), nullable=True),
        sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("published_at", UtcDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_revisions_workflow_id_workflows",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_revisions"),
        sa.UniqueConstraint("workflow_id", "number", name="uq_workflow_revisions_workflow_id"),
    )
    op.create_index(
        "ix_workflow_revisions_workflow_id", "workflow_revisions", ["workflow_id"], unique=False
    )
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(20), nullable=False, server_default="validation")
        )
        batch.add_column(sa.Column("workflow_code", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("workflow_code")
        batch.drop_column("purpose")
    op.drop_index("ix_workflow_revisions_workflow_id", table_name="workflow_revisions")
    op.drop_table("workflow_revisions")
    with op.batch_alter_table("workflows") as batch:
        batch.drop_constraint("fk_workflows_domain_id_domains", type_="foreignkey")
        batch.drop_index("ix_workflows_domain_id")
        batch.drop_constraint("uq_workflows_code", type_="unique")
        batch.drop_column("missing")
        batch.drop_column("archived")
        batch.drop_column("published_number")
        batch.drop_column("domain_id")
        batch.drop_column("code")
