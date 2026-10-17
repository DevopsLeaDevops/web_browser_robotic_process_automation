"""裝置邀請 device_invites（M10.1，ADR 0014）

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_invites",
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("app", sa.String(16), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("expires_at", UtcDateTime(), nullable=False),
        sa.Column("used_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("code_hash", name="pk_device_invites"),
    )
    op.create_index("ix_device_invites_device_id", "device_invites", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_device_invites_device_id", table_name="device_invites")
    op.drop_table("device_invites")
