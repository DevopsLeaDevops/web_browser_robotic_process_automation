"""資料庫裡的執行佇列：rpa-worker 的任務來源（JobSource）。

M3 是單機、單一 worker（ADR 0008：SQLite 只允許單一程序），依建立時間先進先出。
領取時用「狀態還是 queued 才改成 running」的條件更新，避免和取消同時發生時互相覆蓋。
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from rpa_runner.run import RunResult, ScenarioInvalidError, StageName
from rpa_server.domain import now
from rpa_server.i18n import t
from rpa_server.models import Revision, Run
from rpa_server.storage import Storage
from rpa_worker import Job

__all__ = ["RunQueue"]


class RunQueue:
    def __init__(self, sessions: sessionmaker[Session], storage: Storage) -> None:
        self.sessions = sessions
        self.storage = storage

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
                claimed = session.execute(
                    update(Run)
                    .where(Run.id == run.id, Run.status == "queued")
                    .values(status="running", started_at=now(), stage=None)
                )
                session.commit()
                if claimed.rowcount == 1:
                    return Job(
                        run_id=run.id,
                        scenario=self.storage.scenario_path(run.scene_id, run.revision_number),
                        inputs=dict(run.input),
                        out_root=self.storage.runs,
                        engine=run.engine,
                        base_url=run.base_url,
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
