"""資料庫裡的執行佇列：本機 worker 的任務來源（JobSource），以及本機、遠端共用的領取與結果回寫。

- 依建立時間先進先出。領取時用「狀態還是 queued 才改成 running」的條件更新，避免和取消、
  其他 worker 同時領取時互相覆蓋。
- 執行位置（M9a）：本機 worker 只領 local 與 any 的執行；遠端 worker 只領 remote 與 any 的，
  而且要自己有那個瀏覽器、有頭模式要能顯示視窗（:mod:`rpa_server.dispatch`）。
  指定了 required_worker 的執行只給那台 worker（試驗場序列的後續節點）。
- 試驗場序列的節點第一次被領取時，把序列固定給這台 worker（workflow_runs.worker_id）。
- 場景有 login 時，任務帶著角色的登入設定與 Secrets；結束後依登入檢查的結果更新角色狀態（M4）。
- 每個任務結束後呼叫 ``on_finished``：試驗場序列的節點由它接著排下一個節點（M6）。
"""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Scenario, validate_file
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, ScenarioInvalidError, StageName
from rpa_server.domain import LOCAL_WORKER, now
from rpa_server.i18n import t
from rpa_server.models import Revision, Run, WorkflowRun
from rpa_server.roles import RoleService
from rpa_server.storage import Storage
from rpa_worker import Job

__all__ = ["Outcome", "RunQueue"]

_BATCH: Final = 50
"""領取時一次看這麼多筆排隊中的執行（其中可能有這台 worker 不能跑的）。"""


@dataclass(frozen=True, slots=True)
class Outcome:
    """一次執行的結果（本機的 RunResult 或遠端 worker 回報的 result.json）。"""

    status: str
    output: dict[str, object] | None = None
    error: str | None = None
    scenario_hash: str | None = None
    duration_seconds: float | None = None
    role: str | None = None
    login: Mapping[str, object] | None = None

    @classmethod
    def from_result(cls, result: RunResult) -> "Outcome":
        return cls(
            status=result.status,
            output=result.output,
            error=result.error,
            scenario_hash=result.scenario_hash,
            duration_seconds=result.duration_seconds,
            role=result.role,
            login=result.login,
        )

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "Outcome":
        """遠端 worker 回報的 result.json；欄位不對時拋出 ValueError。"""
        status = data.get("status")
        if status not in ("passed", "failed", "timed_out", "cancelled", "needs_login"):
            raise ValueError(f"invalid status: {status!r}")
        output = data.get("output")
        error = data.get("error")
        digest = data.get("scenarioHash")
        duration = data.get("durationSeconds")
        role = data.get("role")
        login = data.get("login")
        return cls(
            status=status,
            output=cast("dict[str, object]", output) if isinstance(output, dict) else None,
            error=str(error) if error is not None else None,
            scenario_hash=digest if isinstance(digest, str) else None,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            role=role if isinstance(role, str) else None,
            login=cast("Mapping[str, object]", login) if isinstance(login, dict) else None,
        )


@lru_cache(maxsize=512)
def _scenario_at(path: str) -> Scenario | None:
    """版本的場景檔（版本不可變，可以快取）。"""
    return validate_file(Path(path)).scenario


class RunQueue:
    def __init__(
        self, sessions: sessionmaker[Session], storage: Storage, roles: RoleService | None = None
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.roles = roles
        self.on_finished: Callable[[str], None] = lambda run_id: None
        """任務結束（資料庫已更新）之後呼叫，參數是執行編號。"""

    # ------------------------------------------------------------ 場景與登入

    def scenario(self, scene_id: str, number: int) -> Scenario | None:
        return _scenario_at(str(self.storage.scenario_path(scene_id, number)))

    def engine_of(self, run: Run) -> str:
        """這次執行要用的瀏覽器：指定的，或場景預設的。"""
        if run.engine:
            return run.engine
        scenario = self.scenario(run.scene_id, run.revision_number)
        return scenario.browser.engine if scenario is not None else "chromium"

    def extras(self, scene_id: str, number: int) -> tuple[LoginSettings | None, dict[str, str]]:
        """場景要的登入設定與 Secrets 的值（只交給 runner，不寫進資料庫）。"""
        if self.roles is None:
            return None, {}
        scenario = self.scenario(scene_id, number)
        if scenario is None:
            return None, {}
        login = None
        names = list(scenario.secrets)
        if scenario.login is not None:
            login = self.roles.login_settings(scenario.login.role)
            names += list(login.secrets) if login is not None else []
        return login, self.roles.secret_values(names)

    # ------------------------------------------------------------ 領取

    def claim_run(
        self,
        worker_id: str,
        targets: Collection[str],
        *,
        accepts: Callable[[Run], bool] = lambda run: True,
        lease_until: datetime | None = None,
    ) -> Run | None:
        """領取下一個這台 worker 可以執行的任務，狀態改成 running；沒有就回傳 None。"""
        with self.sessions() as session:
            for _ in range(5):
                candidates = session.scalars(
                    select(Run)
                    .where(
                        Run.status == "queued",
                        Run.target.in_(list(targets)),
                        or_(Run.required_worker.is_(None), Run.required_worker == worker_id),
                    )
                    .order_by(Run.created_at, Run.id)
                    .limit(_BATCH)
                ).all()
                run = next((item for item in candidates if accepts(item)), None)
                if run is None:
                    return None
                claimed = cast(
                    "CursorResult[Any]",
                    session.execute(
                        update(Run)
                        .where(Run.id == run.id, Run.status == "queued")
                        .values(
                            status="running",
                            started_at=now(),
                            stage=None,
                            worker_id=worker_id,
                            lease_until=lease_until,
                        )
                    ),
                )
                if claimed.rowcount == 1:
                    if run.workflow_run_id is not None:
                        session.execute(
                            update(WorkflowRun)
                            .where(
                                WorkflowRun.id == run.workflow_run_id,
                                WorkflowRun.worker_id.is_(None),
                            )
                            .values(worker_id=worker_id)
                        )
                    session.commit()
                    session.refresh(run)
                    return run
                session.rollback()
            return None

    def claim(self) -> Job | None:
        """本機 worker 的任務來源。"""
        run = self.claim_run(LOCAL_WORKER, ("local", "any"))
        if run is None:
            return None
        # 從快照執行：執行中拉取或重新載入領域資料夾不影響這次執行（M11 收尾）
        path = self.storage.snapshot(run.scene_id, run.revision_number, run.id)
        login, secrets = self.extras(run.scene_id, run.revision_number)
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

    # ------------------------------------------------------------ 進度與結果

    def set_stage(self, run_id: str, stage: str | None) -> None:
        with self.sessions() as session:
            session.execute(
                update(Run).where(Run.id == run_id, Run.status == "running").values(stage=stage)
            )
            session.commit()

    def progress(self, job: Job, stage: StageName) -> None:
        self.set_stage(job.run_id, stage)

    def finish(self, job: Job, result: RunResult) -> None:
        self.storage.drop_snapshot(job.run_id)
        self.complete(job.run_id, Outcome.from_result(result))

    def fail(self, job: Job, error: Exception) -> None:
        self.storage.drop_snapshot(job.run_id)
        if isinstance(error, ScenarioInvalidError):
            message = t("run.scenario_invalid", count=len(error.issues))
        else:
            message = t("run.crashed", detail=f"{type(error).__name__}: {error}")
        self.fail_run(job.run_id, message)

    def complete(self, run_id: str, outcome: Outcome, *, worker_id: str | None = None) -> bool:
        """寫回結果；worker_id 有指定時，只接受這台 worker 正在執行的。回傳是否寫入。"""
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None or not self._owned(run, worker_id):
                return False
            run.status = outcome.status
            run.stage = None
            run.output = outcome.output
            run.error = outcome.error
            run.scenario_hash = outcome.scenario_hash
            run.finished_at = now()
            run.duration_seconds = outcome.duration_seconds
            run.lease_until = None
            if run.purpose == "validation":
                revision = session.get(Revision, run.revision_id)
                if revision is not None:
                    matches = outcome.scenario_hash == revision.content_hash
                    if outcome.status == "passed" and not matches:
                        run.status = "failed"
                        run.error = t("run.hash_mismatch")
                    revision.status = "passed" if run.status == "passed" else "failed"
            session.commit()
        login = outcome.login
        if self.roles is not None and outcome.role is not None and login is not None:
            status = str(login.get("status"))
            message = t("role.needs_login_run", id=run_id) if status == "needs_login" else None
            self.roles.record_result(outcome.role, status, message)
        self.on_finished(run_id)
        return True

    def fail_run(self, run_id: str, message: str, *, worker_id: str | None = None) -> bool:
        """沒辦法執行（場景沒通過校驗、程式錯誤、worker 失聯）：標為失敗。回傳是否寫入。"""
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None or not self._owned(run, worker_id):
                return False
            run.status = "failed"
            run.stage = None
            run.error = message
            run.finished_at = now()
            run.lease_until = None
            if run.purpose == "validation":
                revision = session.get(Revision, run.revision_id)
                if revision is not None:
                    revision.status = "failed"
            session.commit()
        self.on_finished(run_id)
        return True

    @staticmethod
    def _owned(run: Run, worker_id: str | None) -> bool:
        if worker_id is None:
            return True
        return run.status == "running" and run.worker_id == worker_id
