"""自由試驗場：組合場景以 DAG 表達依賴，依拓撲順序逐個執行。

第 1 版保留原有順序；第 2 版先固定同名匹配，再依依賴拓撲排序。畫布位置不影響執行。

- **組合場景**（workflows）：名稱、說明與 rpa_core.workflow 的定義；每次存檔 version 加一，
  存檔要帶目前的 version，不一致就回 409。定義有問題也可以存（編輯到一半），但不能執行。
- **組合場景的執行**（workflow_runs）：開始時存一份定義的快照；第一個節點排入佇列，
  worker 每執行完一個節點就呼叫 :meth:`WorkflowService.node_finished`：通過就取出參、排下一個節點，
  沒有通過（失敗、逾時、取消、需要登入）就停在那個節點，後面的節點略過。
- **節點的執行**就是一般的執行（runs，目的 workflow）：有自己的執行目錄、報告，也出現在執行報告。
- **重新執行**用同一份快照從頭開始；**從失敗的節點繼續**沿用前面已通過節點的出參，
  不重複前面的操作（例如建立紀錄），適合登入之後接著跑。
- 單機、組合場景執行：節點的執行一個一個排進同一個佇列，與其他執行依建立時間先後執行。

M11 PR 2：組合場景放在領域資料夾的 composites/<代號>/（:mod:`rpa_server.packs`）。

- **版本**：每次改定義都是新版本（version 是最新的版本號碼）；名稱與說明不分版本。
- **驗證與執行**：驗證跑某個版本（預設最新），結束時寫驗證紀錄；執行只跑發布的版本。
- **發布**：有雜湊相符的通過驗證紀錄（每個節點跑的場景版本也相符），而且釘住的場景版本現在
  都還在、雜湊相同。
- **依賴**：最新與發布的版本釘住的場景版本、場景用到的角色與 Secrets；不完整時不能執行。

所有改變組合場景執行狀態的操作都在同一把鎖裡（worker 的回報與頁面的取消可能同時發生）。
"""

import logging
import os
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Scenario
from rpa_core.pack import (
    COMPOSITES_DIR,
    CompositeManifest,
    PublishedRef,
    SceneRequirement,
    parse_timestamp,
    timestamp,
    workflow_text,
)
from rpa_core.workflow import (
    Workflow,
    WorkflowNode,
    WorkflowProblem,
    check_workflow,
    input_sources,
    parse_workflow,
    plan_workflow,
    resolve_inputs,
)
from rpa_runner.run import new_run_id
from rpa_server.domain import (
    FINISHED,
    CompositeRevisionRecord,
    DependencyItem,
    DependencyStatus,
    Engine,
    NodeStatus,
    RevisionStatus,
    RunRecord,
    Target,
    VerificationRecord,
    WorkflowNodeState,
    WorkflowRecord,
    WorkflowRunRecord,
    WorkflowRunStatus,
    now,
)
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.models import Domain, Revision, Role, Run, Scene, WorkflowRevision
from rpa_server.models import Workflow as WorkflowRow
from rpa_server.models import WorkflowRun as WorkflowRunRow

if TYPE_CHECKING:
    from rpa_server.services import Services

__all__ = ["RUN_LIST_LIMIT", "WorkflowService"]

logger = logging.getLogger("rpa_server")

RUN_LIST_LIMIT: Final = 50
"""組合場景執行清單最多顯示的筆數。"""

_NAME_LIMIT: Final = 200
_CODE: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""組合場景代號的規則（和場景 id 相同）。"""
Purpose = Literal["validation", "execution"]


def _run_record(run: Run) -> RunRecord:
    from rpa_server.services import run_record  # services 匯入本模組，執行時才取用避免循環

    return run_record(run)


class WorkflowService:
    def __init__(self, sessions: sessionmaker[Session], services: "Services") -> None:
        self.sessions = sessions
        self.services = services
        self._lock = threading.RLock()
        self._scenarios: dict[tuple[str, int], Scenario | None] = {}
        """(場景, 版本) → 場景；版本內容不可變，可以一直快取。"""

    # ------------------------------------------------------------ 場景版本

    def _scenario(self, scene_id: str, number: int) -> Scenario | None:
        key = (scene_id, number)
        if key not in self._scenarios:
            try:
                self._scenarios[key] = self.services.revision_scenario(scene_id, number)
            except ServiceError:
                return None
        return self._scenarios[key]

    def check(self, workflow: Workflow) -> list[WorkflowProblem]:
        """執行前的檢查：場景存在、沒有封存、固定的版本發布過，再加上 rpa_core 的靜態檢查。"""
        problems: list[WorkflowProblem] = []
        scenarios: dict[str, Scenario | None] = {}
        with self.sessions() as session:
            for node in workflow.nodes:
                problem = self._node_problem(session, node)
                if problem is not None:
                    problems.append(problem)
                    scenarios[node.id] = None
                else:
                    scenarios[node.id] = self._scenario(node.scene_id, node.revision)
        return problems + check_workflow(workflow, scenarios)

    @staticmethod
    def _node_problem(session: Session, node: WorkflowNode) -> WorkflowProblem | None:
        params = {"node": node.id, "scene": node.scene_id, "revision": node.revision}
        scene = session.get(Scene, node.scene_id)
        revision = session.scalars(
            select(Revision).where(
                Revision.scene_id == node.scene_id, Revision.number == node.revision
            )
        ).first()
        if scene is None or scene.missing:
            code = "scene_missing"
        elif scene.archived:
            code = "scene_archived"
        elif revision is None or revision.missing or revision.problem is not None:
            code = "revision_missing"
        elif revision.published_at is None:
            code = "revision_unpublished"
        else:
            return None
        return WorkflowProblem(f"workflow.{code}", t(f"workflow.{code}", **params), node.id)

    def parse(self, data: object) -> tuple[Workflow | None, list[WorkflowProblem]]:
        """API 送來的定義 → (組合場景, 問題)；格式不對時組合場景是 None。"""
        workflow, problems = parse_workflow(data)
        if workflow is None:
            return None, problems
        return workflow, self.check(workflow)

    def library(self) -> list[dict[str, object]]:
        """編輯組合場景時的場景庫：有發布過版本的場景，每個發布過的版本的入參與出參。

        封存的場景也列出（標示 archived），讓組合場景裡已經用到的節點還能顯示；
        場景庫本身不列出它們。
        """
        with self.sessions() as session:
            published = list(
                session.scalars(
                    select(Revision)
                    .where(Revision.published_at.is_not(None), Revision.missing.is_(False))
                    .order_by(Revision.scene_id, Revision.number.desc())
                )
            )
            scenes = {
                scene.id: scene
                for scene in session.scalars(
                    select(Scene).where(Scene.id.in_({row.scene_id for row in published}))
                )
            }
        names = {domain.id: domain.name for domain in self.services.list_domains()}
        entries: dict[str, dict[str, object]] = {}
        for revision in published:
            scene = scenes[revision.scene_id]
            if scene.missing:  # 領域資料夾裡已經沒有這個場景（M11）
                continue
            entry = entries.setdefault(
                scene.id,
                {
                    "id": scene.id,
                    "name": scene.name,
                    "category": scene.category,
                    "domainId": scene.domain_id,
                    "domainName": names.get(scene.domain_id or ""),
                    "publishedRevision": scene.published_number,
                    "archived": scene.archived,
                    "revisions": [],
                },
            )
            scenario = self._scenario(scene.id, revision.number)
            if scenario is None:
                continue
            cast("list[dict[str, object]]", entry["revisions"]).append(
                {
                    "number": revision.number,
                    "name": scenario.name,
                    "inputs": _specs(scenario, "inputs"),
                    "outputs": _specs(scenario, "outputs"),
                    "role": scenario.login.role if scenario.login is not None else None,
                }
            )
        return sorted(entries.values(), key=lambda item: str(item["id"]))

    # ------------------------------------------------------------ 組合場景

    @staticmethod
    def _row(session: Session, workflow_id: int) -> WorkflowRow:
        row = session.get(WorkflowRow, workflow_id)
        if row is None:
            raise not_found("workflow_not_found", t("error.workflow_not_found", id=workflow_id))
        return row

    def _record(self, row: WorkflowRow, *, with_last_run: bool = True) -> WorkflowRecord:
        workflow, problems = parse_workflow(row.definition)
        if workflow is None:  # 資料庫裡的定義都經過校驗；萬一壞了也要能打開頁面修正
            workflow = Workflow()
        else:
            problems = self.check(workflow)
        last = None
        if with_last_run:
            runs = self.list_runs(workflow_id=row.id, limit=1)
            last = runs[0] if runs else None
        return WorkflowRecord(
            id=row.id,
            name=row.name,
            description=row.description,
            workflow=workflow,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            problems=tuple(problems),
            last_run=last,
            code=row.code,
            domain_id=row.domain_id,
            published_number=row.published_number,
            archived=row.archived,
            dependency=_dependency_status(self._dependencies(row)),
        )

    def list_workflows(self) -> list[WorkflowRecord]:
        with self.sessions() as session:
            rows = list(
                session.scalars(
                    select(WorkflowRow)
                    .where(WorkflowRow.missing.is_(False))
                    .order_by(WorkflowRow.id)
                )
            )
        return [self._record(row) for row in rows]

    def get_workflow(self, workflow_id: int) -> WorkflowRecord:
        with self.sessions() as session:
            row = self._row(session, workflow_id)
        return self._record(row)

    @staticmethod
    def _name(name: str) -> str:
        name = name.strip()
        if not name:
            raise invalid("workflow_name_missing", t("error.workflow_name_missing"))
        return name[:_NAME_LIMIT]

    def _definition(self, data: object) -> Workflow:
        workflow, problems = parse_workflow(data)
        if workflow is None:
            raise invalid(
                "workflow_format",
                t("error.workflow_format", count=len(problems)),
                problems=[problem.to_json() for problem in problems],
            )
        return workflow

    def create_workflow(
        self,
        name: str,
        description: str | None = None,
        definition: object = None,
        *,
        code: str | None = None,
        domain_id: str | None = None,
    ) -> WorkflowRecord:
        """新增組合場景；可以直接帶定義（匯入匯出的 JSON）。定義就是第 1 版。

        code 沒給時自動取 wf-<數字>；domain_id 沒給時放「組合場景」領域（需要時建立）。
        """
        workflow = (
            self._definition(definition)
            if definition is not None
            else Workflow(version=2, mode="dag")
        )
        name = self._name(name)
        description = (description or "").strip() or None
        code = (code or "").strip() or None
        if code is not None and not _CODE.fullmatch(code):
            raise invalid("workflow_code_invalid", t("error.workflow_code_invalid", code=code))
        domain_id = domain_id or self.services.composites_domain()
        packs = self.services.packs
        with packs.lock, self.sessions() as session:
            if session.get(Domain, domain_id) is None:
                raise not_found("domain_not_found", t("error.domain_not_found", id=domain_id))
            code = code or self._next_code(session)
            if self._code_taken(session, code):
                raise conflict("workflow_code_exists", t("error.workflow_code_exists", code=code))
            moment = now()
            row = WorkflowRow(
                name=name,
                description=description,
                definition=workflow.to_json(),
                version=1,
                created_at=moment,
                updated_at=moment,
                code=code,
                domain_id=domain_id,
                archived=False,
                missing=False,
            )
            session.add(row)
            session.flush()
            self.services.storage.place_composite(code, domain_id)
            try:
                packs.write_composite(
                    CompositeManifest(id=code, name=name, description=description)
                )
                self._write_revision(session, row, 1, workflow, t("workflow.note_created"), moment)
                session.commit()
            except BaseException:
                session.rollback()
                packs.discard_composite_revision(code, 1, new=True)
                raise
            session.refresh(row)
        return self._record(row)

    def _next_code(self, session: Session) -> str:
        """新組合場景的代號：wf-<數字>，從目前最大的 id 往後找沒用過的。"""
        number = (session.scalar(select(func.max(WorkflowRow.id))) or 0) + 1
        while self._code_taken(session, f"wf-{number}"):
            number += 1
        return f"wf-{number}"

    def _code_taken(self, session: Session, code: str) -> bool:
        exists = session.scalars(select(WorkflowRow.id).where(WorkflowRow.code == code)).first()
        return exists is not None or self.services.storage.composite_domain(code) is not None

    def _write_revision(
        self,
        session: Session,
        row: WorkflowRow,
        number: int,
        workflow: Workflow,
        note: str | None,
        moment: datetime,
    ) -> None:
        """寫入組合場景的版本：workflow.json、版本說明檔（釘住的場景版本）、資料庫的一列。"""
        packs = self.services.packs
        requires = packs.requirements(session, workflow)
        digest = packs.write_composite_revision(
            row.code,
            number,
            workflow_text(workflow),
            note=note,
            created_at=moment,
            requires=requires,
        )
        session.add(
            WorkflowRevision(
                workflow_id=row.id,
                number=number,
                content_hash=digest,
                status="draft",
                verified=False,
                missing=False,
                note=note,
                created_at=moment,
            )
        )
        if row.domain_id is not None:
            packs.declare_requirements(row.domain_id, requires)

    def update_workflow(
        self,
        workflow_id: int,
        *,
        base_version: int,
        name: str | None = None,
        description: str | None = None,
        definition: object = None,
    ) -> WorkflowRecord:
        """存檔：base_version 不是目前的版本時回 409（別的分頁已經存過）。

        定義和最新版本不同時存成新的版本（version 加一）；名稱與說明寫進 composite.yaml，不分版本。
        """
        workflow = self._definition(definition) if definition is not None else None
        packs = self.services.packs
        with packs.lock, self.sessions() as session:
            row = self._row(session, workflow_id)
            if base_version != row.version:
                raise conflict(
                    "stale_workflow",
                    t("error.stale_workflow", base=base_version, latest=row.version),
                    latest=row.version,
                )
            moment = now()
            if name is not None or description is not None:
                if name is not None:
                    row.name = self._name(name)
                if description is not None:
                    row.description = description.strip() or None
                manifest = packs.composite_manifest(row.code) or CompositeManifest(
                    id=row.code, name=row.name
                )
                packs.write_composite(
                    manifest.model_copy(update={"name": row.name, "description": row.description})
                )
            number: int | None = None
            if workflow is not None and workflow.to_json() != row.definition:
                number = row.version + 1
                try:
                    self._write_revision(
                        session, row, number, workflow, t("workflow.note_saved"), moment
                    )
                except FileExistsError:
                    session.rollback()
                    raise conflict(
                        "stale_workflow",
                        t("error.stale_workflow", base=base_version, latest=number),
                        latest=number,
                    ) from None
                row.definition = workflow.to_json()
                row.version = number
            row.updated_at = moment
            try:
                session.commit()
            except BaseException:
                session.rollback()
                if number is not None:
                    packs.discard_composite_revision(row.code, number, new=False)
                raise
            session.refresh(row)
        return self._record(row)

    def manage(
        self,
        workflow_id: int,
        *,
        code: str | None = None,
        domain_id: str | None = None,
        archived: bool | None = None,
    ) -> WorkflowRecord:
        """改代號、搬到其他領域、封存（M11 收尾；第 12 節「之後可以在頁面改代號或搬到其他領域」）。

        代號就是資料夾的名稱：改代號是把 composites/<舊代號> 改名，搬領域是把資料夾搬到另一個
        領域資料夾（推送後在 git 裡是刪除＋新增；版本與驗證紀錄跟著走）。執行中不能改代號或搬。
        """
        packs = self.services.packs
        storage = self.services.storage
        with packs.lock, self.sessions() as session:
            row = self._row(session, workflow_id)
            code = (code or "").strip() or None
            moving = (code is not None and code != row.code) or (
                domain_id is not None and domain_id != row.domain_id
            )
            if moving:
                running = session.scalar(
                    select(func.count())
                    .select_from(WorkflowRunRow)
                    .where(
                        WorkflowRunRow.workflow_id == workflow_id,
                        WorkflowRunRow.status == "running",
                    )
                )
                if running:
                    raise conflict("workflow_running", t("error.workflow_running", id=row.code))
            if code is not None and code != row.code:
                if not _CODE.fullmatch(code):
                    raise invalid(
                        "workflow_code_invalid", t("error.workflow_code_invalid", code=code)
                    )
                if self._code_taken(session, code):
                    raise conflict(
                        "workflow_code_exists", t("error.workflow_code_exists", code=code)
                    )
                source = storage.composite_dir(row.code)
                target = source.with_name(code)
                source.rename(target)
                storage.forget_composite(row.code)
                storage.place_composite(code, row.domain_id or self.services.composites_domain())
                manifest = packs.composite_manifest(code) or CompositeManifest(
                    id=code, name=row.name
                )
                packs.write_composite(manifest.model_copy(update={"id": code}))
                row.code = code
            if domain_id is not None and domain_id != row.domain_id:
                if session.get(Domain, domain_id) is None:
                    raise not_found("domain_not_found", t("error.domain_not_found", id=domain_id))
                source = storage.composite_dir(row.code)
                target = storage.domain_dir(domain_id) / COMPOSITES_DIR / row.code
                if target.exists():
                    raise conflict(
                        "workflow_code_exists", t("error.workflow_code_exists", code=row.code)
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                storage.forget_composite(row.code)
                storage.place_composite(row.code, domain_id)
                row.domain_id = domain_id
                for number in {
                    row.version,
                    *([row.published_number] if row.published_number else []),
                }:
                    entry, _ = packs.composite_entry(row.code)
                    revision = entry.revisions.get(number) if entry is not None else None
                    if revision is not None and revision.requires:
                        packs.declare_requirements(domain_id, revision.requires)
            if archived is not None and archived != row.archived:
                manifest = packs.composite_manifest(row.code) or CompositeManifest(
                    id=row.code, name=row.name
                )
                packs.write_composite(manifest.model_copy(update={"archived": archived}))
                row.archived = archived
            row.updated_at = now()
            session.commit()
            session.refresh(row)
        return self._record(row)

    def dependents(self) -> dict[str, list[WorkflowRecord]]:
        """領域 → 依賴它的組合場景（最新版本或發布的版本釘住了那個領域的場景）。"""
        found: dict[str, list[WorkflowRecord]] = {}
        packs = self.services.packs
        for record in self.list_workflows():
            entry, _ = packs.composite_entry(record.code)
            if entry is None:
                continue
            domains: set[str] = set()
            numbers = {record.version}
            if record.published_number is not None:
                numbers.add(record.published_number)
            for number in numbers:
                revision = entry.revisions.get(number)
                if revision is not None:
                    domains.update(item.domain for item in revision.requires or [])
            for domain_id in sorted(domains - {record.domain_id or ""}):
                found.setdefault(domain_id, []).append(record)
        return found

    def delete_workflow(self, workflow_id: int) -> None:
        """刪除組合場景；執行中不能刪。已經執行過的紀錄保留（有定義的快照）。"""
        with self.sessions() as session:
            row = self._row(session, workflow_id)
            running = session.scalar(
                select(func.count())
                .select_from(WorkflowRunRow)
                .where(
                    WorkflowRunRow.workflow_id == workflow_id,
                    WorkflowRunRow.status == "running",
                )
            )
            if running:
                raise conflict("workflow_running", t("error.workflow_running", id=workflow_id))
            for revision in session.scalars(
                select(WorkflowRevision).where(WorkflowRevision.workflow_id == workflow_id)
            ):
                session.delete(revision)
            session.flush()
            session.delete(row)
            session.commit()
            code = row.code
        # 資料夾一起刪除（推送之後別人拉取也會刪除；歷史在 git 裡）
        self.services.packs.remove_composite(code)

    # ------------------------------------------------------------ 執行

    def start(
        self,
        workflow_id: int,
        *,
        engine: Engine | None = None,
        headless: bool | None = None,
        idempotency_key: str | None = None,
        target: Target | None = None,
        purpose: Purpose = "validation",
        revision: int | None = None,
    ) -> WorkflowRunRecord:
        """執行組合場景：先檢查，沒有問題才建立組合場景的執行並排入第一個節點。

        purpose 是 validation（驗證某個版本，預設最新；結束時寫驗證紀錄）或 execution
        （執行發布的版本）。target 是執行位置（M9a）：每個節點都一樣，而且第一個節點由哪台
        worker 領取，後面就都給它。
        """
        key = (idempotency_key or "").strip() or None
        existing = self._by_key(key)
        if existing is not None:
            return existing
        with self.sessions() as session:
            row = self._row(session, workflow_id)
            if row.archived:
                raise conflict("workflow_archived", t("error.workflow_archived", id=row.code))
            if purpose == "execution":
                if row.published_number is None:
                    raise conflict(
                        "workflow_unpublished", t("error.workflow_unpublished", id=row.code)
                    )
                number = row.published_number
            else:
                number = revision or row.version
            source_hash = self._usable_revision(session, row, number).content_hash
            code, name = row.code, row.name
        workflow = self._revision_workflow(code, number)
        problems = self.check(workflow) + [
            WorkflowProblem(item.code, item.message)
            for item in self._requirement_items_for(code, number)
            if item.level == "error"
        ]
        self._ensure_runnable(workflow, problems)
        target = self.services.resolve_target(target)
        headless = self.services.resolve_headless(headless, target)
        return self._launch(
            workflow_id=workflow_id,
            name=name,
            version=number,
            workflow=workflow,
            engine=engine,
            headless=headless,
            key=key,
            reused={},
            start_index=0,
            target=target,
            purpose=purpose,
            code=code,
            source_hash=source_hash,
        )

    @staticmethod
    def _usable_revision(session: Session, row: WorkflowRow, number: int) -> WorkflowRevision:
        item = session.scalars(
            select(WorkflowRevision).where(
                WorkflowRevision.workflow_id == row.id, WorkflowRevision.number == number
            )
        ).first()
        if item is None or item.missing:
            raise not_found(
                "workflow_revision_not_found",
                t("error.workflow_revision_not_found", id=row.code, number=number),
            )
        if item.problem is not None:
            raise conflict(
                "workflow_revision_unusable",
                t(
                    "error.workflow_revision_unusable",
                    id=row.code,
                    number=number,
                    problem=item.problem,
                ),
            )
        return item

    def _revision_workflow(self, code: str, number: int) -> Workflow:
        """某個版本的定義（讀領域資料夾裡的 workflow.json）。"""
        entry, _ = self.services.packs.composite_entry(code)
        revision = entry.revisions.get(number) if entry is not None else None
        if revision is None or revision.workflow is None:
            raise conflict(
                "workflow_revision_unusable",
                t(
                    "error.workflow_revision_unusable",
                    id=code,
                    number=number,
                    problem=revision.problem if revision is not None else "missing",
                ),
            )
        return revision.workflow

    def rerun(
        self, run_id: str, *, resume: bool = False, idempotency_key: str | None = None
    ) -> WorkflowRunRecord:
        """用同一份定義再執行一次：從頭開始，或從停下的節點繼續（沿用前面節點的出參）。"""
        key = (idempotency_key or "").strip() or None
        existing = self._by_key(key)
        if existing is not None:
            return existing
        with self.sessions() as session:
            row = self._run_row(session, run_id)
            if row.status == "running":
                raise conflict("workflow_run_active", t("error.workflow_run_active", id=run_id))
            workflow = Workflow.model_validate(row.definition)
            snapshot = (row.workflow_id, row.workflow_name, row.workflow_version)
            purpose = cast("Purpose", row.purpose)
            code, source_hash = row.workflow_code, row.workflow_hash
            engine, headless = row.engine, row.headless
            target = cast("Target", row.target)
            reused: dict[str, str] = {}
            start_index = 0
            pinned: str | None = None
            if resume:
                start_index, reused = self._resume_point(session, row, workflow)
                # 沿用的節點在哪台 worker 執行，接下來的節點也給它（M9a）
                pinned = row.worker_id if target != "local" and reused else None
        self._ensure_runnable(workflow, self.check(workflow))
        if target == "remote" and not self.services.workers.has_remote():
            target, pinned = "local", None
        return self._launch(
            workflow_id=snapshot[0],
            name=snapshot[1],
            version=snapshot[2],
            workflow=workflow,
            engine=cast("Engine | None", engine),
            headless=headless if headless or self.services.can_display(target) else True,
            key=key,
            reused=reused,
            start_index=start_index,
            resumed_from=run_id if resume else None,
            target=target,
            worker_id=pinned,
            purpose=purpose,
            code=code,
            source_hash=source_hash,
        )

    def _resume_point(
        self, session: Session, row: WorkflowRunRow, workflow: Workflow
    ) -> tuple[int, dict[str, str]]:
        """從停下的節點繼續：(從第幾個節點開始, 沿用的節點 → 那次通過的執行編號)。"""
        ordered = workflow.execution_nodes()
        index = next((i for i, node in enumerate(ordered) if node.id == row.failed_node), -1)
        if row.status == "passed" or index < 0:
            raise conflict("workflow_not_resumable", t("error.workflow_not_resumable", id=row.id))
        passed = self._latest_runs(session, row.id)
        reused: dict[str, str] = {}
        for node in ordered[:index]:
            previous = cast("dict[str, str]", row.reused).get(node.id)
            run = passed.get(node.id)
            if run is not None and run.status == "passed":
                reused[node.id] = run.id
            elif previous is not None:
                reused[node.id] = previous
            else:
                raise conflict(
                    "workflow_not_resumable", t("error.workflow_not_resumable", id=row.id)
                )
        return index, reused

    @staticmethod
    def _ensure_runnable(workflow: Workflow, problems: Sequence[WorkflowProblem]) -> None:
        if problems:
            raise invalid(
                "workflow_invalid",
                t("error.workflow_invalid", count=len(problems)),
                problems=[problem.to_json() for problem in problems],
            )
        if not workflow.nodes:  # check_workflow 會回報；這裡只是保險
            raise invalid("workflow_invalid", t("error.workflow_invalid", count=1))

    def _by_key(self, key: str | None) -> WorkflowRunRecord | None:
        if key is None:
            return None
        with self.sessions() as session:
            row = session.scalars(
                select(WorkflowRunRow).where(WorkflowRunRow.idempotency_key == key)
            ).first()
            run_id = row.id if row is not None else None
        return self.get_run(run_id) if run_id is not None else None

    def _launch(
        self,
        *,
        workflow_id: int | None,
        name: str,
        version: int,
        workflow: Workflow,
        engine: Engine | None,
        headless: bool,
        key: str | None,
        reused: Mapping[str, str],
        start_index: int,
        resumed_from: str | None = None,
        target: Target = "local",
        worker_id: str | None = None,
        purpose: Purpose = "validation",
        code: str | None = None,
        source_hash: str | None = None,
    ) -> WorkflowRunRecord:
        workflow, problems = plan_workflow(
            workflow,
            {node.id: self._scenario(node.scene_id, node.revision) for node in workflow.nodes},
        )
        self._ensure_runnable(workflow, problems)
        with self._lock:
            run_id = new_run_id(code or (f"wf{workflow_id}" if workflow_id is not None else "wf"))
            with self.sessions() as session:
                session.add(
                    WorkflowRunRow(
                        id=run_id,
                        workflow_id=workflow_id,
                        workflow_name=name,
                        workflow_version=version,
                        definition=workflow.to_json(),
                        status="running",
                        engine=engine,
                        headless=headless,
                        reused=dict(reused),
                        resumed_from=resumed_from,
                        idempotency_key=key,
                        cancel_requested=False,
                        created_at=now(),
                        target=target,
                        worker_id=worker_id,
                        purpose=purpose,
                        workflow_code=code,
                        workflow_hash=source_hash,
                    )
                )
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    existing = self._by_key(key)
                    if existing is None:
                        raise
                    return existing
            self._start_node(run_id, start_index)
        self.services.packs.record_workflow_run(run_id)  # run.json（M11 PR 2）
        return self.get_run(run_id)

    def _start_node(self, run_id: str, index: int) -> None:
        """排入第 index 個節點；取值或排入失敗時，組合場景的執行停在這個節點。"""
        with self.sessions() as session:
            row = self._run_row(session, run_id)
            workflow = Workflow.model_validate(row.definition)
            outputs = self._outputs(session, row)
            engine, headless = row.engine, row.headless
            target, pinned = cast("Target", row.target), row.worker_id
        node = workflow.execution_nodes()[index]
        values, problems = resolve_inputs(node, outputs)
        if problems:
            self._finish(run_id, "failed", node.id, problems[0].message)
            return
        try:
            self.services.request_run(
                node.scene_id,
                purpose="workflow",
                number=node.revision,
                inputs=values,
                engine=cast("Engine | None", engine),
                headless=headless,
                workflow_run_id=run_id,
                node_id=node.id,
                target=target,
                required_worker=pinned,
            )
        except ServiceError as error:
            details = error.details.get("problems")
            items = [
                str(cast("dict[str, object]", item).get("message"))
                for item in (cast("list[object]", details) if isinstance(details, list) else [])
                if isinstance(item, dict)
            ]
            if items:
                problems_text = t("js.list_separator").join(items)
                message = t(
                    "workflow_run.node_inputs_invalid", node=node.id, problems=problems_text
                )
            else:
                message = t("workflow_run.node_not_started", node=node.id, detail=error.message)
            self._finish(run_id, "failed", node.id, message)

    def _finish(
        self, run_id: str, status: WorkflowRunStatus, node: str | None, error: str | None
    ) -> None:
        with self.sessions() as session:
            row = self._run_row(session, run_id)
            if row.status != "running":
                return
            row.status = status
            row.failed_node = node
            row.error = error
            row.finished_at = now()
            session.commit()
        # run.json；驗證另外寫進領域資料夾的驗證紀錄（M11 PR 2）
        self.services.packs.record_workflow_run(run_id)

    def node_finished(self, run_id: str) -> None:
        """一個節點的執行結束：通過就排下一個節點，沒有通過就停在這個節點。

        只處理組合場景執行裡最新的那一次節點執行，同一個通知來兩次（例如重啟時的回復）也不會排兩次。
        """
        with self._lock:
            with self.sessions() as session:
                run = session.get(Run, run_id)
                if run is None or run.workflow_run_id is None or run.status not in FINISHED:
                    return
                row = session.get(WorkflowRunRow, run.workflow_run_id)
                if row is None or row.status != "running":
                    return
                latest = session.scalars(
                    select(Run)
                    .where(Run.workflow_run_id == row.id)
                    .order_by(Run.created_at.desc(), Run.id.desc())
                    .limit(1)
                ).first()
                if latest is None or latest.id != run.id:
                    return
                workflow = Workflow.model_validate(row.definition)
                ordered = workflow.execution_nodes()
                index = next((i for i, item in enumerate(ordered) if item.id == run.node_id), -1)
                status, node, scene = run.status, run.node_id, run.scene_id
                workflow_run = row.id
            if index < 0:
                self._finish(workflow_run, "failed", node, None)
            elif status != "passed":
                message = t(
                    "workflow_run.node_stopped",
                    node=node,
                    scene=scene,
                    status=t(f"status.{status}"),
                )
                self._finish(workflow_run, cast("WorkflowRunStatus", status), node, message)
            elif index + 1 < len(workflow.nodes):
                self._start_node(workflow_run, index + 1)
            else:
                self._finish(workflow_run, "passed", None, None)

    def cancel(self, run_id: str) -> WorkflowRunRecord:
        """取消組合場景的執行：停止目前的節點，後面的節點不執行。已經發生的外部動作不會復原。"""
        with self._lock:
            with self.sessions() as session:
                row = self._run_row(session, run_id)
                if row.status != "running":
                    return self.get_run(run_id)
                active = list(
                    session.scalars(
                        select(Run).where(
                            Run.workflow_run_id == run_id,
                            Run.status.in_(["queued", "running"]),
                        )
                    )
                )
                row.cancel_requested = True
                session.commit()
                current = active[0].node_id if active else None
            self._finish(run_id, "cancelled", current, t("workflow_run.cancelled"))
            for run in active:
                self.services.cancel_run(run.id)
        return self.get_run(run_id)

    def recover(self) -> int:
        """伺服器啟動時：還在執行中的組合場景，依最新節點的狀態接著處理（排下一個或停下）。"""
        with self.sessions() as session:
            rows = list(
                session.scalars(select(WorkflowRunRow).where(WorkflowRunRow.status == "running"))
            )
            pending: list[tuple[str, str | None]] = []
            for row in rows:
                latest = session.scalars(
                    select(Run)
                    .where(Run.workflow_run_id == row.id)
                    .order_by(Run.created_at.desc(), Run.id.desc())
                    .limit(1)
                ).first()
                pending.append((row.id, latest.id if latest is not None else None))
        for workflow_run, latest in pending:
            if latest is not None:
                self.node_finished(latest)  # 還在排隊的節點不受影響，worker 會照常執行
            else:
                self._finish(workflow_run, "failed", None, t("run.interrupted"))
        return len(pending)

    # ------------------------------------------------------------ 版本、發布、依賴（M11 PR 2）

    def revisions(self, workflow_id: int) -> list[CompositeRevisionRecord]:
        with self.sessions() as session:
            row = self._row(session, workflow_id)
            items = session.scalars(
                select(WorkflowRevision)
                .where(WorkflowRevision.workflow_id == row.id, WorkflowRevision.missing.is_(False))
                .order_by(WorkflowRevision.number.desc())
            )
            return [
                CompositeRevisionRecord(
                    number=item.number,
                    content_hash=item.content_hash,
                    status=cast("RevisionStatus", item.status),
                    verified=item.verified,
                    problem=item.problem,
                    note=item.note,
                    created_at=item.created_at,
                    published_at=item.published_at,
                    published=row.published_number == item.number,
                )
                for item in items
            ]

    def verifications(self, workflow_id: int) -> list[VerificationRecord]:
        """組合場景的驗證紀錄（領域資料夾裡的，不管是哪一台伺服器驗證的），最新的在前。"""
        with self.sessions() as session:
            code = self._row(session, workflow_id).code
        entry, _ = self.services.packs.composite_entry(code)
        if entry is None:
            return []
        server = self.services.packs.server().id
        found: list[VerificationRecord] = []
        with self.sessions() as session:
            for number, revision in entry.revisions.items():
                digest = revision.info.hash if revision.info is not None else None
                for item in revision.verifications:
                    record = item.record
                    here = (
                        record.server.id == server
                        and session.get(WorkflowRunRow, item.id) is not None
                    )
                    # 雜湊相符：定義的雜湊一樣，而且節點跑的場景版本都是釘住的那些
                    matches = record.hash == digest
                    if matches and digest is not None and record.status == "passed":
                        matches = item.proves(digest, revision.requires)
                    found.append(
                        VerificationRecord(
                            id=item.id,
                            revision=number,
                            status=record.status,
                            matches=matches,
                            finished_at=parse_timestamp(record.finished_at),
                            by=record.by,
                            server_id=record.server.id,
                            server_name=record.server.name,
                            worker=record.worker.id,
                            engine=record.engine,
                            headless=record.headless,
                            here=here,
                        )
                    )
        return sorted(found, key=lambda item: (item.finished_at, item.id), reverse=True)

    def publish(self, workflow_id: int, number: int) -> WorkflowRecord:
        """發布組合場景的版本：有雜湊相符的通過驗證紀錄（節點跑的場景版本也相符），
        釘住的場景版本現在都還在、雜湊相同。寫進 composite.yaml 的 published。
        """
        packs = self.services.packs
        with packs.lock, self.sessions() as session:
            row = self._row(session, workflow_id)
            item = self._usable_revision(session, row, number)
            entry, _ = packs.composite_entry(row.code)
            revision = entry.revisions.get(number) if entry is not None else None
            proofs = revision.proofs() if revision is not None else []
            if entry is None or revision is None or not proofs:
                raise conflict(
                    "workflow_not_validated",
                    t("error.workflow_not_validated", id=row.code, number=number),
                )
            errors = [
                problem
                for problem in self._requirement_items(
                    session, number, revision.requires or [], revision.workflow
                )
                if problem.level == "error"
            ]
            if errors:
                raise conflict(
                    "workflow_dependencies",
                    t("error.workflow_dependencies", id=row.code, count=len(errors)),
                    problems=[problem.to_json() for problem in errors],
                )
            moment = now()
            published = PublishedRef(
                revision=number,
                verification=proofs[0].id,
                at=timestamp(moment),
                by=packs.operator(),
                server=packs.server(),
            )
            packs.write_composite(entry.manifest.model_copy(update={"published": published}))
            row.published_number = number
            row.updated_at = moment
            item.published_at = moment
            item.verified = True
            session.commit()
        return self.get_workflow(workflow_id)

    def dependencies(self, workflow_id: int) -> list[DependencyItem]:
        """依賴的問題（最新版本與發布的版本）：任務紀錄第 7 節的清單與補全方式。"""
        with self.sessions() as session:
            row = self._row(session, workflow_id)
        return self._dependencies(row)

    def _dependencies(self, row: WorkflowRow) -> list[DependencyItem]:
        numbers: set[int] = {row.version}
        if row.published_number is not None:
            numbers.add(row.published_number)
        items: list[DependencyItem] = []
        seen: set[tuple[str, str, str | None]] = set()
        for number in sorted(numbers):
            for item in self._requirement_items_for(row.code, number):
                key = (item.code, item.message, item.scene)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        return items

    def _requirement_items_for(self, code: str, number: int) -> list[DependencyItem]:
        entry, _ = self.services.packs.composite_entry(code)
        revision = entry.revisions.get(number) if entry is not None else None
        if revision is None or revision.workflow is None:
            return []
        with self.sessions() as session:
            return self._requirement_items(
                session, number, revision.requires or [], revision.workflow
            )

    def _requirement_source(self, domain_id: str) -> dict[str, str] | None:
        """依賴的領域從哪裡取得：任一個領域的 pack.yaml requires 裡記的 source。"""
        packs = self.services.packs
        folders = sorted(self.services.storage.domains.glob("*"))
        for folder in folders:
            manifest = packs.manifest(folder.name) if folder.is_dir() else None
            for item in manifest.requires if manifest is not None else []:
                if item.domain == domain_id and item.source is not None:
                    found = {"url": item.source.repo, "directory": item.source.directory or ""}
                    if item.source.branch:
                        found["branch"] = item.source.branch
                    return found
        return None

    def _requirement_items(
        self,
        session: Session,
        number: int,
        requires: Sequence[SceneRequirement],
        workflow: Workflow | None,
    ) -> list[DependencyItem]:
        """一個版本的依賴：釘住的場景版本在不在、雜湊對不對；場景用到的角色與 Secrets。"""
        if workflow is None:
            return []
        pinned = {(item.scene, item.revision): item for item in requires}
        items: list[DependencyItem] = []
        checked: set[tuple[str, int]] = set()

        def add(
            level: Literal["error", "warning"],
            code: str,
            action: str | None,
            params: Mapping[str, object],
            source: dict[str, str] | None = None,
        ) -> None:
            items.append(
                DependencyItem(
                    level=level,
                    code=f"dependency.{code}",
                    message=t(f"dependency.{code}", **params),
                    revision=number,
                    domain=cast("str | None", params.get("domain")),
                    scene=cast("str | None", params.get("scene")),
                    action=action,
                    source=source,
                )
            )

        for node in workflow.nodes:
            key = (node.scene_id, node.revision)
            if key in checked:
                continue
            checked.add(key)
            params: dict[str, object] = {"scene": node.scene_id, "revision": node.revision}
            pin = pinned.get(key)
            if pin is None:
                add("error", "unpinned", "resave", params)
                continue
            params["domain"] = pin.domain
            domain = session.get(Domain, pin.domain)
            if domain is None:
                add(
                    "error",
                    "domain_missing",
                    "add_domain",
                    params,
                    self._requirement_source(pin.domain),
                )
                continue
            # 領域有 git 資料來源：缺的東西多半是還沒拉取（或拉取失敗），補全的方式是拉取
            refresh = "pull" if domain.source else "reload_domain"
            scene = session.get(Scene, pin.scene)
            if scene is None or scene.missing or scene.domain_id != pin.domain:
                add("error", "scene_missing", refresh, params)
                continue
            revision = session.scalars(
                select(Revision).where(
                    Revision.scene_id == pin.scene, Revision.number == pin.revision
                )
            ).first()
            if revision is None or revision.missing:
                add("error", "revision_missing", refresh, params)
                continue
            if revision.problem is not None:
                add("error", "revision_unusable", "reload_domain", params)
                continue
            if revision.content_hash != pin.hash:
                add("error", "hash_mismatch", "resave", params)
                continue
            scenario = self._scenario(pin.scene, pin.revision)
            if scenario is None:
                continue
            if scenario.login is not None:
                role = session.get(Role, scenario.login.role)
                params["role"] = scenario.login.role
                if role is None or role.missing:
                    add("error", "role_missing", "reload_domain", params)
                elif role.status != "logged_in" and not role.auto_login:
                    add("warning", "role_login", "login", params)
            stored = {info.name for info in self.services.roles.list_secrets()}
            missing = [
                name for name in scenario.secrets if name not in stored and name not in os.environ
            ]
            if missing:
                add(
                    "warning", "secrets_missing", "secrets", {**params, "names": ", ".join(missing)}
                )
        return items

    # ------------------------------------------------------------ 查詢

    @staticmethod
    def _run_row(session: Session, run_id: str) -> WorkflowRunRow:
        row = session.get(WorkflowRunRow, run_id)
        if row is None:
            raise not_found("workflow_run_not_found", t("error.workflow_run_not_found", id=run_id))
        return row

    @staticmethod
    def _latest_runs(session: Session, run_id: str) -> dict[str, Run]:
        """組合場景執行裡每個節點最新的一次執行。"""
        found: dict[str, Run] = {}
        for run in session.scalars(
            select(Run).where(Run.workflow_run_id == run_id).order_by(Run.created_at, Run.id)
        ):
            if run.node_id is not None:
                found[run.node_id] = run
        return found

    def _outputs(
        self, session: Session, row: WorkflowRunRow
    ) -> dict[str, Mapping[str, object] | None]:
        """節點代號 → 通過之後發布的出參（沿用的節點取原本那次執行）；沒有通過的是 None。"""
        outputs: dict[str, Mapping[str, object] | None] = {}
        for node, run in self._latest_runs(session, row.id).items():
            outputs[node] = dict(run.output or {}) if run.status == "passed" else None
        for node, previous in cast("dict[str, str]", row.reused).items():
            run = session.get(Run, previous)
            outputs[node] = (
                dict(run.output or {}) if run is not None and run.status == "passed" else None
            )
        return outputs

    def _run_record(self, session: Session, row: WorkflowRunRow) -> WorkflowRunRecord:
        workflow, _ = parse_workflow(row.definition)
        nodes: list[WorkflowNodeState] = []
        if workflow is not None:
            latest = self._latest_runs(session, row.id)
            reused = cast("dict[str, str]", row.reused)
            for index, node in enumerate(workflow.execution_nodes()):
                nodes.append(self._node_state(session, row, index, node, latest, reused))
        return WorkflowRunRecord(
            id=row.id,
            workflow_id=row.workflow_id,
            workflow_name=row.workflow_name,
            workflow_version=row.workflow_version,
            status=cast("WorkflowRunStatus", row.status),
            engine=row.engine,
            headless=row.headless,
            error=row.error,
            failed_node=row.failed_node,
            resumed_from=row.resumed_from,
            target=cast("Target", row.target),
            worker_id=row.worker_id,
            cancel_requested=row.cancel_requested,
            created_at=row.created_at,
            finished_at=row.finished_at,
            nodes=tuple(nodes),
            purpose=row.purpose,
            workflow_code=row.workflow_code,
        )

    def _node_state(
        self,
        session: Session,
        row: WorkflowRunRow,
        index: int,
        node: WorkflowNode,
        latest: Mapping[str, Run],
        reused: Mapping[str, str],
    ) -> WorkflowNodeState:
        scenario = self._scenario(node.scene_id, node.revision)
        sources = (
            {name: source.to_json() for name, source in input_sources(node, scenario).items()}
            if scenario is not None
            else {}
        )
        run: Run | None = None
        error: str | None = None
        status: NodeStatus
        if node.id in reused:
            run = session.get(Run, reused[node.id])
            status = "reused"
        elif node.id in latest:
            run = latest[node.id]
            status = cast("NodeStatus", run.status)
        elif row.status == "running":
            status = "pending"
        elif row.failed_node == node.id:
            status = "failed"  # 沒有開始執行就停下（例如綁定的值不符合入參規則）
            error = row.error
        else:
            status = "skipped"
        name = run.scene_name if run is not None else (scenario.name if scenario else node.scene_id)
        return WorkflowNodeState(
            index=index,
            id=node.id,
            scene_id=node.scene_id,
            scene_name=name,
            revision=node.revision,
            status=status,
            sources=sources,
            run=_run_record(run) if run is not None else None,
            error=error,
        )

    def get_run(self, run_id: str) -> WorkflowRunRecord:
        with self.sessions() as session:
            return self._run_record(session, self._run_row(session, run_id))

    def list_runs(
        self, *, workflow_id: int | None = None, limit: int = RUN_LIST_LIMIT
    ) -> list[WorkflowRunRecord]:
        statement = (
            select(WorkflowRunRow)
            .order_by(WorkflowRunRow.created_at.desc(), WorkflowRunRow.id.desc())
            .limit(limit)
        )
        if workflow_id is not None:
            statement = statement.where(WorkflowRunRow.workflow_id == workflow_id)
        with self.sessions() as session:
            return [self._run_record(session, row) for row in session.scalars(statement)]


def _specs(scenario: Scenario, key: str) -> list[list[object]]:
    """入參或出參：[名稱, DSL 寫法的規格] 的清單，保留場景檔的順序。"""
    specs = scenario.inputs if key == "inputs" else scenario.outputs
    return [
        [name, spec.model_dump(mode="json", by_alias=True, exclude_none=True)]
        for name, spec in specs.items()
    ]


def _dependency_status(items: Sequence[DependencyItem]) -> DependencyStatus:
    if any(item.level == "error" for item in items):
        return "incomplete"
    return "warnings" if items else "complete"
