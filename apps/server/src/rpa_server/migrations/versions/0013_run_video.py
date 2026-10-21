"""運行的錄影（M12）：長度、大小、釘選、刪除的時間與原因

影片本身在執行目錄（video.webm、video.json）；這裡記下清單、篩選與清理要用的值。
之前的運行都沒有錄影。

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("video_seconds", sa.Float(), nullable=True))
        batch.add_column(sa.Column("video_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("video_pinned", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("video_deleted_at", UtcDateTime(), nullable=True))
        batch.add_column(sa.Column("video_deleted_reason", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("video_deleted_reason")
        batch.drop_column("video_deleted_at")
        batch.drop_column("video_pinned")
        batch.drop_column("video_bytes")
        batch.drop_column("video_seconds")
