"""錄製端 recorders 與錄製的 device_id（M10.2，ADR 0014）

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recorders",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("info", JsonType, nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("last_seen_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recorders"),
        sa.UniqueConstraint("token_hash", name="uq_recorders_token_hash"),
    )
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("device_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("device_id")
    op.drop_table("recorders")
