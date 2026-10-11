"""領域 domains；場景加上 domain_id（場景管理的二級選單）

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_domains"),
    )
    with op.batch_alter_table("scenes") as batch:
        batch.add_column(sa.Column("domain_id", sa.String(64), nullable=True))
        batch.create_index("ix_scenes_domain_id", ["domain_id"])
        batch.create_foreign_key("fk_scenes_domain_id_domains", "domains", ["domain_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_constraint("fk_scenes_domain_id_domains", type_="foreignkey")
        batch.drop_index("ix_scenes_domain_id")
        batch.drop_column("domain_id")
    op.drop_table("domains")
