"""專案：「專案空間」的二級選單，一個專案是一份「組合場景自動化」（2026-10-23 使用者要求）。

專案是這台伺服器上組合場景的分組，管理方式和領域相同（管理後台 › 專案管理）：新增（代號用在網址，
建立後不能改）、改名稱與說明、刪除沒有組合場景的專案、調整順序。

專案、排列順序與組合場景屬於哪個專案都只存在資料庫（projects、workflows.project_id），不寫進領域
資料夾與 git，和領域的順序一樣每台伺服器各自管理。組合場景本身照舊放在某個領域資料夾的
composites/<代號>/；從 git 拉來、這台還沒見過的組合場景不屬於任何專案，在專案管理列出，
到組合場景頁的「設定」選專案。
"""

import threading
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rpa_server.config import COMPOSITES_PROJECT
from rpa_server.domain import DOMAIN_ID, ProjectRecord, now
from rpa_server.errors import conflict, invalid, not_found
from rpa_server.i18n import follow_locale, t
from rpa_server.models import Project
from rpa_server.models import Workflow as WorkflowRow

__all__ = ["ProjectService"]


class ProjectService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions
        self._lock = threading.Lock()

    @staticmethod
    def _project(session: Session, project_id: str) -> Project:
        project = session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found", t("error.project_not_found", id=project_id))
        return project

    @staticmethod
    def _record(session: Session, project: Project) -> ProjectRecord:
        count = session.scalar(
            select(func.count())
            .select_from(WorkflowRow)
            .where(WorkflowRow.project_id == project.id, WorkflowRow.missing.is_(False))
        )
        name, description = project.name, project.description
        if project.id == COMPOSITES_PROJECT:  # 升級時建立的：沒改過名稱與說明就跟著介面語言
            name = follow_locale(name, "project.composites_name") or name
            description = follow_locale(description, "project.composites_description")
        return ProjectRecord(
            id=project.id,
            name=name,
            description=description,
            position=project.position,
            composite_count=count or 0,
            created_at=project.created_at,
        )

    def check(self, session: Session, project_id: str) -> None:
        """組合場景要放進的專案存在嗎（新增、搬移組合場景時，在同一個交易裡檢查）。"""
        self._project(session, project_id)

    def list_projects(self) -> list[ProjectRecord]:
        """全部專案，依排列順序；就是專案空間的二級選單。"""
        with self.sessions() as session:
            projects = session.scalars(
                select(Project).order_by(Project.position, Project.created_at)
            )
            return [self._record(session, project) for project in projects]

    def get_project(self, project_id: str) -> ProjectRecord:
        with self.sessions() as session:
            return self._record(session, self._project(session, project_id))

    def create_project(
        self, project_id: str, name: str, description: str | None = None
    ) -> ProjectRecord:
        """新增專案，排在最後。代號的規則和領域相同（用在網址，建立後不能改）。"""
        project_id, name = project_id.strip(), name.strip()
        if not DOMAIN_ID.fullmatch(project_id):
            raise invalid("project_id_invalid", t("error.project_id_invalid", id=project_id))
        if not name:
            raise invalid("project_name_missing", t("error.project_name_missing"))
        with self._lock, self.sessions() as session:
            if session.get(Project, project_id) is not None:
                raise conflict("project_exists", t("error.project_exists", id=project_id))
            last = session.scalar(select(func.max(Project.position)))
            project = Project(
                id=project_id,
                name=name,
                description=(description or "").strip() or None,
                position=(last if last is not None else -1) + 1,
                created_at=now(),
            )
            session.add(project)
            session.commit()
            return self._record(session, project)

    def update_project(
        self, project_id: str, *, name: str | None = None, description: str | None = None
    ) -> ProjectRecord:
        """改名稱或說明；代號不能改（網址用它）。"""
        with self._lock, self.sessions() as session:
            project = self._project(session, project_id)
            if name is not None:
                if not name.strip():
                    raise invalid("project_name_missing", t("error.project_name_missing"))
                project.name = name.strip()
            if description is not None:
                project.description = description.strip() or None
            session.commit()
            return self._record(session, project)

    def delete_project(self, project_id: str) -> None:
        """只能刪除沒有組合場景（包含封存的）的專案；組合場景要先刪除或移到其他專案。"""
        with self._lock, self.sessions() as session:
            project = self._project(session, project_id)
            used = session.scalar(
                select(func.count())
                .select_from(WorkflowRow)
                .where(WorkflowRow.project_id == project_id, WorkflowRow.missing.is_(False))
            )
            if used:
                raise conflict(
                    "project_not_empty", t("error.project_not_empty", id=project_id, count=used)
                )
            # 來源缺失的組合場景只剩執行紀錄引用，不再屬於任何專案
            for row in session.scalars(
                select(WorkflowRow).where(WorkflowRow.project_id == project_id)
            ):
                row.project_id = None
            session.flush()
            session.delete(project)
            session.commit()

    def reorder_projects(self, ids: Sequence[str]) -> list[ProjectRecord]:
        """依 ``ids`` 重排全部專案（專案管理的上移、下移）；專案空間的選單照這個順序。

        ``ids`` 要剛好是現在的全部專案；有人在別處新增或刪除了專案時回 409，請重新整理再排。
        """
        with self._lock, self.sessions() as session:
            projects = {project.id: project for project in session.scalars(select(Project))}
            if len(ids) != len(set(ids)) or set(ids) != set(projects):
                raise conflict("project_order_changed", t("error.project_order_changed"))
            for position, project_id in enumerate(ids):
                projects[project_id].position = position
            session.commit()
        return self.list_projects()
