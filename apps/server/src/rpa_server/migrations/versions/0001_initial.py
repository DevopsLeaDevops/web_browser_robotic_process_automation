"""建立 scenes、revisions、runs（M3）

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(2000), nullable=True),
        sa.Column("latest_number", sa.Integer(), nullable=False),
        sa.Column("published_number", sa.Integer(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scenes"),
    )
    op.create_table(
        "revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("published_at", UtcDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], name="fk_revisions_scene_id_scenes"),
        sa.PrimaryKeyConstraint("id", name="pk_revisions"),
        sa.UniqueConstraint("scene_id", "number", name="uq_revisions_scene_id"),
    )
    op.create_index("ix_revisions_scene_id", "revisions", ["scene_id"])
    op.create_table(
        "runs",
        sa.Column("id", sa.String(120), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(20), nullable=True),
        sa.Column("engine", sa.String(20), nullable=True),
        sa.Column("base_url", sa.String(2000), nullable=True),
        sa.Column("input", JsonType, nullable=False),
        sa.Column("output", JsonType, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("scenario_hash", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("started_at", UtcDateTime(), nullable=True),
        sa.Column("finished_at", UtcDateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], name="fk_runs_scene_id_scenes"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["revisions.id"], name="fk_runs_revision_id_revisions"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_runs_idempotency_key"),
    )
    op.create_index("ix_runs_scene_id", "runs", ["scene_id"])
    op.create_index("ix_runs_revision_id", "runs", ["revision_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("revisions")
    op.drop_table("scenes")
