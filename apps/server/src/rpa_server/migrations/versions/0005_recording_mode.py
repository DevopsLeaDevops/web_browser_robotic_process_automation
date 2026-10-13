"""錄製加上 mode 與 base_revision：既有場景可以接著現有步驟錄製

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        # 之前的錄製：新場景是 new，既有場景是 replace（整份換成錄製的草稿）
        batch.add_column(sa.Column("mode", sa.String(20), nullable=False, server_default="new"))
        batch.add_column(sa.Column("base_revision", sa.Integer(), nullable=True))
    recordings = sa.table(
        "recordings", sa.column("mode", sa.String()), sa.column("new_scene", sa.Boolean())
    )
    op.execute(
        recordings.update().where(recordings.c.new_scene == sa.false()).values(mode="replace")
    )


def downgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("base_revision")
        batch.drop_column("mode")
