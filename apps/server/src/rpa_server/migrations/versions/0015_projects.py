"""專案 projects；組合場景加上 project_id（專案空間，2026-10-23）

「專案空間」的二級選單是專案，一個專案是一份「組合場景自動化」。原本已經有組合場景時，建立專案
「組合場景自動化」（代號 composites）並把它們都放進去，升級後照樣找得到；名稱與說明沒改過時
跟著介面語言顯示（rpa_server.projects）。

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-23
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from rpa_server.db import UtcDateTime

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPOSITES_PROJECT = "composites"
NAME = "組合場景自動化"
"""繁中訊息目錄的 project.composites_name（測試確認兩者相同）。"""
DESCRIPTION = "升級時自動建立，原本的組合場景都放在這裡。"
"""繁中訊息目錄的 project.composites_description。"""


def upgrade() -> None:
    projects = op.create_table(
        "projects",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("project_id", sa.String(64), nullable=True))
        batch.create_index("ix_workflows_project_id", ["project_id"])
        batch.create_foreign_key(
            "fk_workflows_project_id_projects", "projects", ["project_id"], ["id"]
        )
    workflows = sa.table("workflows", sa.column("id", sa.Integer()), sa.column("project_id"))
    connection = op.get_bind()
    if connection.scalar(sa.select(sa.func.count()).select_from(workflows)):
        op.bulk_insert(
            projects,
            [
                {
                    "id": COMPOSITES_PROJECT,
                    "name": NAME,
                    "description": DESCRIPTION,
                    "position": 0,
                    "created_at": datetime.now(UTC),
                }
            ],
        )
        op.execute(workflows.update().values(project_id=COMPOSITES_PROJECT))


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.drop_constraint("fk_workflows_project_id_projects", type_="foreignkey")
        batch.drop_index("ix_workflows_project_id")
        batch.drop_column("project_id")
    op.drop_table("projects")
