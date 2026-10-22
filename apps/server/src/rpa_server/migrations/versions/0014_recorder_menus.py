"""錄製端另外顯示的第一級選單 recorders.menus（三段分工）

透過錄製端打開管理 Portal 時，叢集管理與管理後台預設不顯示；這一欄記下裝置頁替這台打開了哪些。
之前登記的錄製端都是空的（不顯示）。

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from rpa_server.db import JsonType

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recorders") as batch:
        batch.add_column(sa.Column("menus", JsonType, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recorders") as batch:
        batch.drop_column("menus")
