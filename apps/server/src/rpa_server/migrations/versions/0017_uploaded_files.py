"""上傳檔案（M7c）：上傳到伺服器的檔案 uploaded_files

檔案入參的值 ``{"file": id, …}`` 參照它；內容放在資料目錄的 input-files/。既有資料不受影響。

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("used_at", UtcDateTime(), nullable=True),
        sa.Column("client_id", sa.String(64), nullable=True),
        sa.Column("deleted_at", UtcDateTime(), nullable=True),
        sa.Column("deleted_reason", sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_uploaded_files"),
    )
    op.create_index("ix_uploaded_files_sha256", "uploaded_files", ["sha256"])
    op.create_index("ix_uploaded_files_created_at", "uploaded_files", ["created_at"])
    op.create_index("ix_uploaded_files_used_at", "uploaded_files", ["used_at"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_used_at", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_created_at", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_sha256", table_name="uploaded_files")
    op.drop_table("uploaded_files")
