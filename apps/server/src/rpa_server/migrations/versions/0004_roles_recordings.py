"""登入角色 roles 與錄製 recordings（M4）

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("login_url", sa.String(2000), nullable=False),
        sa.Column("check_url", sa.String(2000), nullable=True),
        sa.Column("check_locator", JsonType, nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("auto_login", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("checked_at", UtcDateTime(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
    )
    op.create_table(
        "recordings",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("scene_name", sa.String(200), nullable=False),
        sa.Column("new_scene", sa.Boolean(), nullable=False),
        sa.Column("domain_id", sa.String(64), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("role_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("warnings", JsonType, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("finished_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recordings"),
    )
    op.create_index("ix_recordings_scene_id", "recordings", ["scene_id"])
    op.create_index("ix_recordings_status", "recordings", ["status"])
    op.create_index("ix_recordings_created_at", "recordings", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_recordings_created_at", table_name="recordings")
    op.drop_index("ix_recordings_status", table_name="recordings")
    op.drop_index("ix_recordings_scene_id", table_name="recordings")
    op.drop_table("recordings")
    op.drop_table("roles")
