"""服務層：場景、版本、執行的所有操作。API 與頁面都只呼叫這裡。

每個方法自己開一個資料庫交易，回傳 domain.py 的唯讀紀錄；錯誤以 :class:`ServiceError` 表示，
API 轉成 JSON、頁面轉成錯誤頁。

發布門檻：版本的最近一次驗證通過，而且有一次「通過的驗證執行」的場景雜湊等於版本的雜湊，
磁碟上的內容也還是同一個雜湊。改內容就是新版本，要重新驗證。
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Scenario, validate_file
from rpa_runner.contract import check_inputs
from rpa_runner.files import RESULT
from rpa_runner.run import new_run_id, scenario_sources
from rpa_server.domain import (
    Engine,
    Purpose,
    RevisionRecord,
    RevisionStatus,
    RunRecord,
    RunStatus,
    SceneRecord,
    Stats,
    issue_json,
    now,
)
from rpa_server.i18n import t
from rpa_server.models import Revision, Run, Scene
from rpa_server.storage import SCENARIO_FILE, Storage, new_scene_template

__all__ = [
    "ImportReport",
    "ServiceError",
    "Services",
    "revision_record",
    "run_record",
    "scene_record",
]

SCENE_ID: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""與 DSL 的 id 相同的規則。"""

RUN_LIST_LIMIT: Final = 200
"""報告清單最多顯示的筆數。"""


class ServiceError(Exception):
    """操作失敗：status 是對應的 HTTP 狀態碼，code 給程式判斷，message 是目前語言的說明。"""

    def __init__(self, status: int, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def to_json(self) -> dict[str, object]:
        return {"error": {"code": self.code, "message": self.message, **self.details}}


def _not_found(code: str, message: str) -> ServiceError:
    return ServiceError(404, code, message)


def _conflict(code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(409, code, message, **details)


def _invalid(code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(422, code, message, **details)


@dataclass(frozen=True, slots=True)
class ImportReport:
    imported: list[str] = field(default_factory=list[str])
    skipped: list[str] = field(default_factory=list[str])

    def to_json(self) -> dict[str, object]:
        return {"imported": self.imported, "skipped": self.skipped}


# ---------------------------------------------------------------- 轉換


def scene_record(scene: Scene, latest: Revision | None) -> SceneRecord:
    return SceneRecord(
        id=scene.id,
        name=scene.name,
        category=scene.category,
        description=scene.description,
        kind=latest.kind if latest is not None else "dsl",
        base_url=scene.base_url,
        latest_number=scene.latest_number,
        latest_status=cast("RevisionStatus", latest.status if latest is not None else "draft"),
        published_number=scene.published_number,
        archived=scene.archived,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


def revision_record(revision: Revision, scene: Scene) -> RevisionRecord:
    return RevisionRecord(
        scene_id=revision.scene_id,
        number=revision.number,
        content_hash=revision.content_hash,
        kind=revision.kind,
        status=cast("RevisionStatus", revision.status),
        note=revision.note,
        created_at=revision.created_at,
        published_at=revision.published_at,
        published=scene.published_number == revision.number,
    )


def run_record(run: Run) -> RunRecord:
    return RunRecord(
        id=run.id,
        scene_id=run.scene_id,
        scene_name=run.scene_name,
        category=run.category,
        revision_number=run.revision_number,
        purpose=cast("Purpose", run.purpose),
        status=cast("RunStatus", run.status),
        stage=run.stage,
        engine=run.engine,
        base_url=run.base_url,
        input=dict(run.input),
        output=dict(run.output) if run.output is not None else None,
        error=run.error,
        scenario_hash=run.scenario_hash,
        cancel_requested=run.cancel_requested,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=run.duration_seconds,
    )


def _check_base_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise _invalid("base_url_invalid", t("error.base_url_invalid", value=value))
    return value


# ---------------------------------------------------------------- 服務


class Services:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: Storage,
        *,
        examples_dir: Path | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.examples_dir = examples_dir
        self.on_queued: Callable[[], None] = lambda: None
        """有新的執行排入佇列（叫醒 worker）。"""
        self.on_cancel: Callable[[str], object] = lambda run_id: None
        """要求取消執行中的任務。"""

    # ------------------------------------------------------------ 查詢：場景

    @staticmethod
    def _scene(session: Session, scene_id: str) -> Scene:
        scene = session.get(Scene, scene_id)
        if scene is None:
            raise _not_found("scene_not_found", t("error.scene_not_found", id=scene_id))
        return scene

    @staticmethod
    def _revision(session: Session, scene_id: str, number: int) -> Revision:
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == scene_id, Revision.number == number)
        ).first()
        if revision is None:
            raise _not_found(
                "revision_not_found", t("error.revision_not_found", id=scene_id, number=number)
            )
        return revision

    @staticmethod
    def _latest(session: Session, scene: Scene) -> Revision | None:
        return session.scalars(
            select(Revision).where(
                Revision.scene_id == scene.id, Revision.number == scene.latest_number
            )
        ).first()

    def list_scenes(
        self, *, query: str = "", category: str | None = None, include_archived: bool = False
    ) -> list[SceneRecord]:
        statement = select(Scene).order_by(Scene.id)
        if not include_archived:
            statement = statement.where(Scene.archived.is_(False))
        if category:
            statement = statement.where(Scene.category == category)
        if query.strip():
            pattern = f"%{query.strip().lower()}%"
            statement = statement.where(
                or_(func.lower(Scene.id).like(pattern), func.lower(Scene.name).like(pattern))
            )
        with self.sessions() as session:
            scenes = list(session.scalars(statement))
            latest = self._latest_map(session, scenes)
            return [scene_record(scene, latest.get(scene.id)) for scene in scenes]

    @staticmethod
    def _latest_map(session: Session, scenes: Iterable[Scene]) -> dict[str, Revision]:
        wanted = {(scene.id, scene.latest_number) for scene in scenes}
        if not wanted:
            return {}
        scene_ids = sorted({scene_id for scene_id, _ in wanted})
        revisions = session.scalars(select(Revision).where(Revision.scene_id.in_(scene_ids)))
        return {
            revision.scene_id: revision
            for revision in revisions
            if (revision.scene_id, revision.number) in wanted
        }

    def categories(self) -> list[str]:
        with self.sessions() as session:
            values = session.scalars(
                select(Scene.category)
                .where(Scene.category.is_not(None), Scene.archived.is_(False))
                .distinct()
                .order_by(Scene.category)
            )
            return [value for value in values if value]

    def run_categories(self) -> list[str]:
        with self.sessions() as session:
            values = session.scalars(
                select(Run.category).where(Run.category.is_not(None)).distinct()
            )
            return sorted(value for value in values if value)

    def stats(self) -> Stats:
        with self.sessions() as session:
            active = Scene.archived.is_(False)
            return Stats(
                scenes=session.scalar(select(func.count()).select_from(Scene).where(active)) or 0,
                published=session.scalar(
                    select(func.count())
                    .select_from(Scene)
                    .where(active, Scene.published_number.is_not(None))
                )
                or 0,
                runs=session.scalar(select(func.count()).select_from(Run)) or 0,
                passed=session.scalar(
                    select(func.count()).select_from(Run).where(Run.status == "passed")
                )
                or 0,
            )

    def get_scene(self, scene_id: str) -> SceneRecord:
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            return scene_record(scene, self._latest(session, scene))

    def revisions(self, scene_id: str) -> list[RevisionRecord]:
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            revisions = session.scalars(
                select(Revision)
                .where(Revision.scene_id == scene_id)
                .order_by(Revision.number.desc())
            )
            return [revision_record(revision, scene) for revision in revisions]

    def get_revision(self, scene_id: str, number: int | None = None) -> RevisionRecord:
        """某個版本；number 為 None 時是最新版本。"""
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            revision = self._revision(session, scene_id, number or scene.latest_number)
            return revision_record(revision, scene)

    def revision_files(self, scene_id: str, number: int) -> dict[str, str]:
        self.get_revision(scene_id, number)
        return self.storage.load(scene_id, number)

    def revision_scenario(self, scene_id: str, number: int) -> Scenario:
        """版本的場景（從磁碟載入並校驗）。"""
        self.get_revision(scene_id, number)
        return self._load_scenario(scene_id, number)

    def _load_scenario(self, scene_id: str, number: int) -> Scenario:
        scenario = validate_file(self.storage.scenario_path(scene_id, number)).scenario
        if scenario is None:
            raise _conflict(
                "revision_unreadable", t("error.revision_unreadable", id=scene_id, number=number)
            )
        return scenario

    # ------------------------------------------------------------ 場景與版本

    def create_scene(self, scene_id: str, name: str, category: str | None = None) -> SceneRecord:
        scene_id, name = scene_id.strip(), name.strip()
        category = (category or "").strip() or None
        if not SCENE_ID.fullmatch(scene_id):
            raise _invalid("scene_id_invalid", t("error.scene_id_invalid", id=scene_id))
        if not name:
            raise _invalid("scene_name_missing", t("error.scene_name_missing"))
        files = {SCENARIO_FILE: new_scene_template(scene_id, name, category)}
        return self._add_scene(scene_id, files, note=t("revision.note_created"))

    def _add_scene(self, scene_id: str, files: Mapping[str, str], note: str | None) -> SceneRecord:
        checked = self.storage.check(files, scene_id=scene_id)
        if not checked.ok or checked.scenario is None or checked.digest is None:
            raise _invalid(
                "revision_invalid",
                t("error.revision_invalid", count=len(checked.issues)),
                issues=[issue_json(issue) for issue in checked.issues],
            )
        scenario = checked.scenario
        with self.sessions() as session:
            if session.get(Scene, scene_id) is not None:
                raise _conflict("scene_exists", t("error.scene_exists", id=scene_id))
            moment = now()
            scene = Scene(
                id=scene_id,
                name=scenario.name,
                category=scenario.category,
                description=scenario.description,
                latest_number=1,
                archived=False,
                created_at=moment,
                updated_at=moment,
            )
            revision = Revision(
                scene_id=scene_id,
                number=1,
                content_hash=checked.digest,
                kind="script" if scenario.script is not None else "dsl",
                status="draft",
                note=note,
                created_at=moment,
            )
            self._write_revision(session, scene_id, 1, checked.files, [scene, revision])
            return scene_record(scene, revision)

    def _write_revision(
        self,
        session: Session,
        scene_id: str,
        number: int,
        files: Mapping[str, str],
        rows: Sequence[Scene | Revision],
    ) -> None:
        """寫入資料庫列與版本檔案，一起提交；任何一步失敗都不留下半個版本。

        先 flush 資料庫列：(場景, 版本號碼) 有唯一約束，flush 成功代表這個號碼只屬於本交易，
        這時版本目錄如果已經存在，只可能是之前中斷留下的殘留，可以安全移除。
        """
        try:
            for row in rows:  # 依外鍵順序寫入：場景、再版本
                session.add(row)
                session.flush()
        except IntegrityError:
            session.rollback()
            raise _conflict(
                "revision_conflict", t("error.revision_conflict", id=scene_id)
            ) from None
        self.storage.discard(scene_id, number)
        try:
            self.storage.save(scene_id, number, files)
            session.commit()
        except BaseException:
            session.rollback()
            self.storage.discard(scene_id, number)
            raise

    def update_scene(
        self,
        scene_id: str,
        *,
        base_url: str | None = None,
        clear_base_url: bool = False,
        archived: bool | None = None,
    ) -> SceneRecord:
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            if clear_base_url:
                scene.base_url = None
            elif base_url is not None:
                scene.base_url = _check_base_url(base_url)
            if archived is not None:
                scene.archived = archived
            scene.updated_at = now()
            session.commit()
            return scene_record(scene, self._latest(session, scene))

    def save_revision(
        self,
        scene_id: str,
        *,
        base: int,
        files: Mapping[str, str],
        note: str | None = None,
    ) -> RevisionRecord:
        """以最新版本為基礎存成新版本；base 不是最新版本時回 409（別人已經存過）。"""
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            if scene.archived:
                raise _conflict("scene_archived", t("error.scene_archived", id=scene_id))
            if base != scene.latest_number:
                raise _conflict(
                    "stale_base",
                    t("error.stale_base", base=base, latest=scene.latest_number),
                    latest=scene.latest_number,
                )
            checked = self.storage.check(files, scene_id=scene_id)
            if not checked.ok or checked.scenario is None or checked.digest is None:
                raise _invalid(
                    "revision_invalid",
                    t("error.revision_invalid", count=len(checked.issues)),
                    issues=[issue_json(issue) for issue in checked.issues],
                )
            scenario = checked.scenario
            number = scene.latest_number + 1
            moment = now()
            revision = Revision(
                scene_id=scene_id,
                number=number,
                content_hash=checked.digest,
                kind="script" if scenario.script is not None else "dsl",
                status="draft",
                note=(note or "").strip()[:500] or None,
                created_at=moment,
            )
            scene.latest_number = number
            scene.name = scenario.name
            scene.category = scenario.category
            scene.description = scenario.description
            scene.updated_at = moment
            self._write_revision(session, scene_id, number, checked.files, [scene, revision])
            return revision_record(revision, scene)

    def import_examples(self) -> ImportReport:
        """匯入範例資料夾的場景（已存在的 id 略過），每個場景建立第 1 版草稿。"""
        folder = self.examples_dir
        if folder is None or not folder.is_dir():
            raise _not_found("no_examples", t("error.no_examples"))
        report = ImportReport()
        paths = sorted(folder.glob("*.yaml")) + sorted(folder.glob("*/scenario.yaml"))
        for path in paths:
            validated = validate_file(path)
            scenario = validated.scenario
            if scenario is None:
                report.skipped.append(t("import.invalid", path=path.name))
                continue
            files = {
                (SCENARIO_FILE if relative == path.name else relative): (
                    path.parent / relative
                ).read_text(encoding="utf-8")
                for relative in scenario_sources(path, scenario)
            }
            try:
                self._add_scene(
                    scenario.id, files, note=t("revision.note_imported", path=path.name)
                )
            except ServiceError as error:
                report.skipped.append(f"{scenario.id}：{error.message}")
                continue
            report.imported.append(scenario.id)
        return report

    # ------------------------------------------------------------ 執行

    def request_run(
        self,
        scene_id: str,
        *,
        purpose: Purpose,
        number: int | None = None,
        inputs: Mapping[str, object] | None = None,
        engine: Engine | None = None,
        base_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> RunRecord:
        """排入一次執行。驗證可以用任何版本（預設最新）；正式執行只用已發布版本。"""
        inputs = dict(inputs or {})
        key = (idempotency_key or "").strip() or None
        with self.sessions() as session:
            if key is not None:
                existing = session.scalars(select(Run).where(Run.idempotency_key == key)).first()
                if existing is not None:
                    return run_record(existing)
            scene = self._scene(session, scene_id)
            if scene.archived:
                raise _conflict("scene_archived", t("error.scene_archived", id=scene_id))
            if purpose == "execution":
                if scene.published_number is None:
                    raise _conflict("not_published", t("error.not_published", id=scene_id))
                number = scene.published_number
            revision = self._revision(session, scene_id, number or scene.latest_number)
            scenario = self._load_scenario(scene_id, revision.number)
            _, problems = check_inputs(scenario, inputs)
            if problems:
                raise _invalid(
                    "inputs_invalid",
                    t("error.inputs_invalid", count=len(problems)),
                    problems=[{"name": item.name, "message": item.message} for item in problems],
                )
            run = Run(
                id=new_run_id(scene_id),
                scene_id=scene_id,
                revision_id=revision.id,
                revision_number=revision.number,
                scene_name=scene.name,
                category=scene.category,
                purpose=purpose,
                status="queued",
                engine=engine,
                base_url=_check_base_url(base_url) or scene.base_url,
                input=inputs,
                idempotency_key=key,
                cancel_requested=False,
                created_at=now(),
            )
            session.add(run)
            if purpose == "validation":
                revision.status = "validating"
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalars(select(Run).where(Run.idempotency_key == key)).first()
                if existing is None:
                    raise
                return run_record(existing)
            record = run_record(run)
        self.on_queued()
        return record

    def publish(self, scene_id: str, number: int) -> SceneRecord:
        """發布版本：最近一次驗證通過，而且通過的驗證執行跑的就是這份內容。"""
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            revision = self._revision(session, scene_id, number)
            if revision.status != "passed":
                raise _conflict(
                    "not_validated", t("error.not_validated", id=scene_id, number=number)
                )
            proof = session.scalars(
                select(Run).where(
                    Run.revision_id == revision.id,
                    Run.purpose == "validation",
                    Run.status == "passed",
                    Run.scenario_hash == revision.content_hash,
                )
            ).first()
            if proof is None:
                raise _conflict(
                    "not_validated", t("error.not_validated", id=scene_id, number=number)
                )
            if self.storage.digest(scene_id, number) != revision.content_hash:
                raise _conflict(
                    "content_changed", t("error.content_changed", id=scene_id, number=number)
                )
            moment = now()
            scene.published_number = number
            scene.updated_at = moment
            revision.published_at = moment
            session.commit()
            return scene_record(scene, self._latest(session, scene))

    def list_runs(
        self,
        *,
        scenes: Sequence[str] = (),
        categories: Sequence[str] = (),
        statuses: Sequence[str] = (),
        purposes: Sequence[str] = (),
        limit: int = RUN_LIST_LIMIT,
    ) -> list[RunRecord]:
        statement = select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit)
        if scenes:
            statement = statement.where(Run.scene_id.in_(list(scenes)))
        if categories:
            statement = statement.where(Run.category.in_(list(categories)))
        if statuses:
            statement = statement.where(Run.status.in_(list(statuses)))
        if purposes:
            statement = statement.where(Run.purpose.in_(list(purposes)))
        with self.sessions() as session:
            return [run_record(run) for run in session.scalars(statement)]

    def get_run(self, run_id: str) -> RunRecord:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise _not_found("run_not_found", t("error.run_not_found", id=run_id))
            return run_record(run)

    def run_result(self, run_id: str) -> dict[str, object] | None:
        """執行目錄裡的 result.json（執行完才有）。"""
        path = self.storage.run_file(run_id, RESULT)
        if path is None:
            return None
        data: object = json.loads(path.read_text(encoding="utf-8"))
        return cast("dict[str, object]", data) if isinstance(data, dict) else None

    def run_file(self, run_id: str, relative: str) -> Path:
        self.get_run(run_id)
        path = self.storage.run_file(run_id, relative)
        if path is None:
            raise _not_found("file_not_found", t("error.file_not_found", path=relative))
        return path

    def cancel_run(self, run_id: str) -> RunRecord:
        """取消：排隊中的直接取消；執行中的通知 worker 終止。不回滾已經發生的外部動作。"""
        notify = False
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise _not_found("run_not_found", t("error.run_not_found", id=run_id))
            if run.status == "queued":
                moment = now()
                run.status = "cancelled"
                run.error = t("run.cancelled_in_queue")
                run.finished_at = moment
                run.cancel_requested = True
                if run.purpose == "validation":
                    self._settle_revision(session, run.revision_id)
            elif run.status == "running":
                run.cancel_requested = True
                notify = True
            session.commit()
            record = run_record(run)
        if notify:
            self.on_cancel(run_id)
        return record

    @staticmethod
    def _settle_revision(session: Session, revision_id: int) -> None:
        """版本的驗證都結束了卻沒有通過：狀態改回失敗（驗證被取消或中斷）。"""
        revision = session.get(Revision, revision_id)
        if revision is None or revision.status != "validating":
            return
        pending = session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                Run.revision_id == revision_id,
                Run.purpose == "validation",
                Run.status.in_(["queued", "running"]),
            )
        )
        if not pending:
            revision.status = "failed"

    def recover(self) -> int:
        """伺服器啟動時：上次執行到一半的任務標為失敗（排隊中的會繼續執行）。"""
        with self.sessions() as session:
            runs = list(session.scalars(select(Run).where(Run.status == "running")))
            moment = now()
            for run in runs:
                run.status = "failed"
                run.stage = None
                run.error = t("run.interrupted")
                run.finished_at = moment
            session.flush()
            for run in runs:
                if run.purpose == "validation":
                    self._settle_revision(session, run.revision_id)
            session.commit()
            return len(runs)
