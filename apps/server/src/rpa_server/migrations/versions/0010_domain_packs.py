"""領域資料夾（M11）：資料庫裡的場景、版本、角色改成資料夾的索引

領域記下最近一次載入的時間與載入問題；場景、版本、角色記下「資料夾裡已經沒有了」（來源缺失）；
版本記下讓它不能執行的問題與有沒有雜湊相符的通過驗證紀錄；角色屬於某個領域。
檔案的搬移（scenes/ → domains/<領域>/）在伺服器啟動時由 rpa_server.packs 完成，不在遷移裡。

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType, UtcDateTime

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("domains") as batch:
        batch.add_column(sa.Column("problems", JsonType, nullable=True))
        batch.add_column(sa.Column("loaded_at", UtcDateTime(), nullable=True))
    with op.batch_alter_table("scenes") as batch:
        batch.add_column(
            sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("revisions") as batch:
        batch.add_column(
            sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("problem", sa.String(60), nullable=True))
        batch.add_column(
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("roles") as batch:
        batch.add_column(sa.Column("domain_id", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.create_index("ix_roles_domain_id", ["domain_id"])
        batch.create_foreign_key("fk_roles_domain_id_domains", "domains", ["domain_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("roles") as batch:
        batch.drop_constraint("fk_roles_domain_id_domains", type_="foreignkey")
        batch.drop_index("ix_roles_domain_id")
        batch.drop_column("missing")
        batch.drop_column("domain_id")
    with op.batch_alter_table("revisions") as batch:
        batch.drop_column("verified")
        batch.drop_column("problem")
        batch.drop_column("missing")
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("missing")
    with op.batch_alter_table("domains") as batch:
        batch.drop_column("loaded_at")
        batch.drop_column("problems")
