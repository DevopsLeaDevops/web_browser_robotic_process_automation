"""領域資料夾的 git 同步（M11 PR 3）：資料來源設定與同步狀態

資料來源（倉庫、分支、目錄、認證方式、使用者名稱、提交者、啟動時自動拉取）與同步狀態（上次同步的
提交、遠端提交、錯誤、衝突）每台伺服器自己保存，不進 git；權杖與 SSH 私鑰在 <資料目錄>/git/。

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("domains") as batch:
        batch.add_column(sa.Column("source", JsonType, nullable=True))
        batch.add_column(sa.Column("sync", JsonType, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("domains") as batch:
        batch.drop_column("sync")
        batch.drop_column("source")
