"""資料庫裡的執行佇列：rpa-worker 的任務來源（JobSource）。

M3 是單機、單一 worker（ADR 0008：SQLite 只允許單一程序），依建立時間先進先出。
領取時用「狀態還是 queued 才改成 running」的條件更新，避免和取消同時發生時互相覆蓋。
場景有 login 時，任務帶著角色的登入設定與 Secrets；結束後依登入檢查的結果更新角色狀態（M4）。
"""

from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import validate_file
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, ScenarioInvalidError, StageName
from rpa_server.domain import now
from rpa_server.i18n import t
from rpa_server.models import Revision, Run
from rpa_server.roles import RoleService
from rpa_server.storage import Storage
from rpa_worker import Job

__all__ = ["RunQueue"]


class RunQueue:
    def __init__(
        self, sessions: sessionmaker[Session], storage: Storage, roles: RoleService | None = None
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.roles = roles

    def _extras(self, path: Path) -> tuple[LoginSettings | None, dict[str, str]]:
        """場景要的登入設定與 Secrets 的值（只交給 runner，不寫進資料庫）。"""
        if self.roles is None:
            return None, {}
        scenario = validate_file(path).scenario
        if scenario is None:
            return None, {}
        login = None
        names = list(scenario.secrets)
        if scenario.login is not None:
            login = self.roles.login_settings(scenario.login.role)
            names += list(login.secrets) if login is not None else []
        return login, self.roles.secret_values(names)

    def claim(self) -> Job | None:
        with self.sessions() as session:
            for _ in range(5):
                run = session.scalars(
                    select(Run)
                    .where(Run.status == "queued")
                    .order_by(Run.created_at, Run.id)
                    .limit(1)
                ).first()
                if run is None:
                    return None
                claimed = cast(
                    "CursorResult[Any]",
                    session.execute(
                        update(Run)
                        .where(Run.id == run.id, Run.status == "queued")
                        .values(status="running", started_at=now(), stage=None)
                    ),
                )
                session.commit()
                if claimed.rowcount == 1:
                    path = self.storage.scenario_path(run.scene_id, run.revision_number)
                    login, secrets = self._extras(path)
                    return Job(
                        run_id=run.id,
                        scenario=path,
                        inputs=dict(run.input),
                        out_root=self.storage.runs,
                        engine=run.engine,
                        base_url=run.base_url,
                        headless=run.headless,
                        login=login,
                        secrets=secrets,
                    )
            return None

    def progress(self, job: Job, stage: StageName) -> None:
        with self.sessions() as session:
            session.execute(
                update(Run).where(Run.id == job.run_id, Run.status == "running").values(stage=stage)
            )
            session.commit()

    def finish(self, job: Job, result: RunResult) -> None:
        with self.sessions() as session:
            run = session.get(Run, job.run_id)
            if run is None:
                return
            run.status = result.status
            run.stage = None
            run.output = result.output
            run.error = result.error
            run.scenario_hash = result.scenario_hash
            run.finished_at = now()
            run.duration_seconds = result.duration_seconds
            if run.purpose == "validation":
                revision = session.get(Revision, run.revision_id)
                if revision is not None:
                    matches = result.scenario_hash == revision.content_hash
                    if result.status == "passed" and not matches:
                        run.status = "failed"
                        run.error = t("run.hash_mismatch")
                    revision.status = "passed" if run.status == "passed" else "failed"
            session.commit()
        login = result.login
        if self.roles is not None and result.role is not None and login is not None:
            status = str(login.get("status"))
            message = (
                t("role.needs_login_run", id=result.run_id) if status == "needs_login" else None
            )
            self.roles.record_result(result.role, status, message)

    def fail(self, job: Job, error: Exception) -> None:
        if isinstance(error, ScenarioInvalidError):
            message = t("run.scenario_invalid", count=len(error.issues))
        else:
            message = t("run.crashed", detail=f"{type(error).__name__}: {error}")
        with self.sessions() as session:
            run = session.get(Run, job.run_id)
            if run is None:
                return
            run.status = "failed"
            run.stage = None
            run.error = message
            run.finished_at = now()
            if run.purpose == "validation":
                revision = session.get(Revision, run.revision_id)
                if revision is not None:
                    revision.status = "failed"
            session.commit()
