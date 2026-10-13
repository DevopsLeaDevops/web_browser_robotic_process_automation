"""服務層：場景、版本、執行的所有操作。API 與頁面都只呼叫這裡。

每個方法自己開一個資料庫交易，回傳 domain.py 的唯讀紀錄；錯誤以 :class:`ServiceError` 表示，
API 轉成 JSON、頁面轉成錯誤頁。

發布門檻：版本的最近一次驗證通過，而且有一次「通過的驗證執行」的場景雜湊等於版本的雜湊，
磁碟上的內容也還是同一個雜湊。改內容就是新版本，要重新驗證。

M4 的登入角色與 Secrets（roles.py）、錄製（recordings.py）、調試工作階段（debugging.py）
各自一個模組，由這裡建立：``services.roles``、``services.recordings``、``services.debug``；
M6 的自由試驗場序列（workflows.py）是 ``services.workflows``。
"""

import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import GotoStep, Scenario, validate_file
from rpa_core.dsl.editing import (
    SECTION_KEYS,
    contract_section,
    find_block,
    replace_contract,
    replace_section,
)
from rpa_core.i18n import DEFAULT_LOCALE, Locale
from rpa_runner.contract import check_inputs
from rpa_runner.files import RESULT, SCREENSHOT
from rpa_runner.run import new_run_id, scenario_sources
from rpa_server.config import EXAMPLES_DOMAIN
from rpa_server.debugging import DebugManager
from rpa_server.domain import (
    DOMAIN_ID,
    DomainRecord,
    Engine,
    Purpose,
    RevisionRecord,
    RevisionStatus,
    RunRecord,
    RunStatus,
    SceneCard,
    SceneRecord,
    issue_json,
    now,
)
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import follow_locale, t
from rpa_server.models import Domain, Revision, Run, Scene
from rpa_server.recordings import RecordingService
from rpa_server.roles import RoleService
from rpa_server.secret_store import SecretStore
from rpa_server.storage import SCENARIO_FILE, Storage, new_scene_template
from rpa_server.workflows import WorkflowService

__all__ = [
    "ROLES_FILE",
    "ImportReport",
    "SceneNeeds",
    "ServiceError",
    "Services",
    "revision_record",
    "run_record",
    "scene_record",
]

SCENE_ID: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""與 DSL 的 id 相同的規則。"""

_CARD_SHOT_LOOKBACK: Final = 5
"""找卡片截圖時，往回看幾次執行。"""

RUN_LIST_LIMIT: Final = 200
"""報告清單最多顯示的筆數。"""

ROLES_FILE: Final = "roles.json"
"""範例資料夾裡的登入角色定義；匯入範例時，場景用到而還沒登記的角色依這裡建立。"""

_CONTRACT_KEYS: Final = frozenset(
    {
        "type",
        "description",
        "default",
        "enum",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "from",
    }
)


def _contract_specs(
    items: Sequence[Mapping[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """表格的每一列 → (名稱 → DSL 寫法的欄位, 改名的「舊名稱 → 新名稱」)。"""
    converted: dict[str, dict[str, object]] = {}
    renames: dict[str, str] = {}
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            raise _invalid("contract_name_missing", t("error.contract_name_missing"))
        if name in converted:
            raise _invalid("contract_duplicate", t("error.contract_duplicate", name=name))
        previous = str(item.get("previous") or "").strip()
        if previous and previous != name:
            renames[previous] = name
        converted[name] = {
            key: value
            for key, value in item.items()
            if key in _CONTRACT_KEYS and value is not None and value not in ("", [])
        }
    return converted, renames


def render_contract(key: str, items: Sequence[Mapping[str, object]]) -> str:
    """表格切換成 YAML：入參或出參段落的原文（不存檔、不校驗）。"""
    if key not in ("inputs", "outputs"):
        raise _not_found("section_unknown", t("error.section_unknown", key=key))
    specs, _ = _contract_specs(items)
    return contract_section(key, specs)


def _section_lines(issues: list[dict[str, object]], text: str, key: str) -> None:
    """校驗問題落在這一段時，加上段落裡的行號 sectionLine（第一行是 ``key:``）。"""
    found = find_block(text.splitlines(), key)
    if found is None:
        return
    start, end = found
    for issue in issues:
        line = issue.get("line")
        if isinstance(line, int) and start < line <= end:
            issue["sectionLine"] = line - start


def _check_section(key: str, section: str) -> None:
    """段落的原文要以 ``key:`` 開頭，而且只能有這一段（不能順便改其他最上層的鍵）。"""
    if not section.strip():
        return
    keys = [
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"^([A-Za-z_][\w-]*)\s*:", line))
    ]
    if keys != [key]:
        raise _invalid("section_key", t("error.section_key", key=key))


_not_found = not_found
_conflict = conflict
_invalid = invalid


@dataclass(frozen=True, slots=True)
class ImportReport:
    imported: list[str] = field(default_factory=list[str])
    skipped: list[str] = field(default_factory=list[str])
    roles: list[str] = field(default_factory=list[str])
    """一起建立的登入角色。"""

    def to_json(self) -> dict[str, object]:
        return {"imported": self.imported, "skipped": self.skipped, "roles": self.roles}


@dataclass(frozen=True, slots=True)
class SceneNeeds:
    """執行這個場景版本需要先準備的：登入角色、Secrets。"""

    role: str | None
    role_registered: bool
    role_status: str | None
    secrets: tuple[tuple[str, bool], ...]
    """(名稱, 是否已設定)；環境變數有同名的值也算已設定。"""

    @property
    def missing_secrets(self) -> list[str]:
        return [name for name, ready in self.secrets if not ready]

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "roleRegistered": self.role_registered,
            "roleStatus": self.role_status,
            "secrets": [{"name": name, "set": ready} for name, ready in self.secrets],
        }


# ---------------------------------------------------------------- 轉換


def scene_record(scene: Scene, latest: Revision | None) -> SceneRecord:
    return SceneRecord(
        id=scene.id,
        name=scene.name,
        category=scene.category,
        description=scene.description,
        domain_id=scene.domain_id,
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
        headless=run.headless,
        workflow_run_id=run.workflow_run_id,
        node_id=run.node_id,
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
        display: bool = False,
        locale: Locale = DEFAULT_LOCALE,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.examples_dir = examples_dir
        self.display = display
        """這台電腦能不能顯示瀏覽器視窗；能的話執行預設用有頭模式。"""
        self._scene_cache: dict[tuple[str, int], tuple[str | None, tuple[str, ...]]] = {}
        self.roles = RoleService(
            sessions,
            storage,
            SecretStore(storage.secrets),
            display=display,
            locale=locale,
            scene_roles=self.scene_roles,
        )
        self.recordings = RecordingService(
            sessions, storage, self, self.roles, display=display, locale=locale
        )
        self.debug = DebugManager(storage, self, self.roles, display=display, locale=locale)
        self.workflows = WorkflowService(sessions, self)
        self.on_queued: Callable[[], None] = lambda: None
        """有新的執行排入佇列（叫醒 worker）。"""
        self.on_cancel: Callable[[str], object] = lambda run_id: None
        """要求取消執行中的任務。"""

    # ------------------------------------------------------------ 領域

    @staticmethod
    def _domain(session: Session, domain_id: str) -> Domain:
        domain = session.get(Domain, domain_id)
        if domain is None:
            raise _not_found("domain_not_found", t("error.domain_not_found", id=domain_id))
        return domain

    @staticmethod
    def _domain_record(session: Session, domain: Domain) -> DomainRecord:
        count = session.scalar(
            select(func.count())
            .select_from(Scene)
            .where(Scene.domain_id == domain.id, Scene.archived.is_(False))
        )
        name, description = domain.name, domain.description
        if domain.id == EXAMPLES_DOMAIN:  # 系統建立的範例領域：沒改過名稱與說明就跟著介面語言
            name = follow_locale(name, "domain.testsite_name") or name
            description = follow_locale(description, "domain.testsite_description")
        return DomainRecord(
            id=domain.id,
            name=name,
            description=description,
            position=domain.position,
            scene_count=count or 0,
            created_at=domain.created_at,
        )

    def list_domains(self) -> list[DomainRecord]:
        """全部領域，依排列順序；就是場景管理的二級選單。"""
        with self.sessions() as session:
            domains = session.scalars(select(Domain).order_by(Domain.position, Domain.created_at))
            return [self._domain_record(session, domain) for domain in domains]

    def get_domain(self, domain_id: str) -> DomainRecord:
        with self.sessions() as session:
            return self._domain_record(session, self._domain(session, domain_id))

    def create_domain(
        self, domain_id: str, name: str, description: str | None = None
    ) -> DomainRecord:
        domain_id, name = domain_id.strip(), name.strip()
        if not DOMAIN_ID.fullmatch(domain_id):
            raise _invalid("domain_id_invalid", t("error.domain_id_invalid", id=domain_id))
        if not name:
            raise _invalid("domain_name_missing", t("error.domain_name_missing"))
        with self.sessions() as session:
            if session.get(Domain, domain_id) is not None:
                raise _conflict("domain_exists", t("error.domain_exists", id=domain_id))
            last = session.scalar(select(func.max(Domain.position)))
            domain = Domain(
                id=domain_id,
                name=name,
                description=(description or "").strip() or None,
                position=(last if last is not None else -1) + 1,
                created_at=now(),
            )
            session.add(domain)
            session.commit()
            return self._domain_record(session, domain)

    def update_domain(
        self, domain_id: str, *, name: str | None = None, description: str | None = None
    ) -> DomainRecord:
        """改名稱或說明；代號不能改（網址與場景都用它）。"""
        with self.sessions() as session:
            domain = self._domain(session, domain_id)
            if name is not None:
                if not name.strip():
                    raise _invalid("domain_name_missing", t("error.domain_name_missing"))
                domain.name = name.strip()
            if description is not None:
                domain.description = description.strip() or None
            session.commit()
            return self._domain_record(session, domain)

    def delete_domain(self, domain_id: str) -> None:
        """只能刪除沒有場景（包含封存的）的領域。"""
        with self.sessions() as session:
            domain = self._domain(session, domain_id)
            used = session.scalar(
                select(func.count()).select_from(Scene).where(Scene.domain_id == domain_id)
            )
            if used:
                raise _conflict(
                    "domain_not_empty", t("error.domain_not_empty", id=domain_id, count=used)
                )
            session.delete(domain)
            session.commit()

    def seed_examples_domain(self) -> ImportReport | None:
        """還沒有任何領域時：建立「測試網站自動化」，把已經存在的範例場景放進去，再匯入其餘範例。"""
        with self.sessions() as session:
            if session.scalar(select(func.count()).select_from(Domain)):
                return None
            session.add(
                Domain(
                    id=EXAMPLES_DOMAIN,
                    name=t("domain.testsite_name"),
                    description=t("domain.testsite_description"),
                    position=0,
                    created_at=now(),
                )
            )
            session.commit()
            example_ids = [scenario_id for scenario_id, _ in self._examples()]
            for scene in session.scalars(
                select(Scene).where(Scene.domain_id.is_(None), Scene.id.in_(example_ids))
            ):
                scene.domain_id = EXAMPLES_DOMAIN
            session.commit()
        if self.examples_dir is None or not self.examples_dir.is_dir():
            return ImportReport()
        return self.import_examples(EXAMPLES_DOMAIN)

    def _examples(self) -> list[tuple[str, Path]]:
        """範例資料夾裡能通過校驗的場景：(場景 id, 場景檔)。"""
        folder = self.examples_dir
        if folder is None or not folder.is_dir():
            return []
        found: list[tuple[str, Path]] = []
        for path in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*/scenario.yaml")):
            scenario = validate_file(path).scenario
            if scenario is not None:
                found.append((scenario.id, path))
        return found

    def scene_cards(self, domain_id: str) -> list[SceneCard]:
        """領域頁的卡片：場景、最近一次執行、最近一張執行截圖。"""
        scenes = self.list_scenes(domain=domain_id)
        cards: list[SceneCard] = []
        with self.sessions() as session:
            for scene in scenes:
                recent = list(
                    session.scalars(
                        select(Run)
                        .where(Run.scene_id == scene.id)
                        .order_by(Run.created_at.desc(), Run.id.desc())
                        .limit(_CARD_SHOT_LOOKBACK)
                    )
                )
                shot = next(
                    (
                        run.id
                        for run in recent
                        if self.storage.run_file(run.id, SCREENSHOT) is not None
                    ),
                    None,
                )
                last = run_record(recent[0]) if recent else None
                cards.append(SceneCard(scene=scene, last_run=last, screenshot_run=shot))
        return cards

    def unassigned_scenes(self) -> list[SceneRecord]:
        return [scene for scene in self.list_scenes() if scene.domain_id is None]

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
        self,
        *,
        query: str = "",
        category: str | None = None,
        domain: str | None = None,
        include_archived: bool = False,
    ) -> list[SceneRecord]:
        statement = select(Scene).order_by(Scene.id)
        if domain is not None:
            statement = statement.where(Scene.domain_id == domain)
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

    def run_categories(self) -> list[str]:
        with self.sessions() as session:
            values = session.scalars(
                select(Run.category).where(Run.category.is_not(None)).distinct()
            )
            return sorted(value for value in values if value)

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

    def create_scene(
        self,
        scene_id: str,
        name: str,
        category: str | None = None,
        *,
        domain_id: str | None = None,
    ) -> SceneRecord:
        scene_id, name = scene_id.strip(), name.strip()
        category = (category or "").strip() or None
        if not SCENE_ID.fullmatch(scene_id):
            raise _invalid("scene_id_invalid", t("error.scene_id_invalid", id=scene_id))
        if not name:
            raise _invalid("scene_name_missing", t("error.scene_name_missing"))
        files = {SCENARIO_FILE: new_scene_template(scene_id, name, category)}
        return self.add_scene(scene_id, files, note=t("revision.note_created"), domain_id=domain_id)

    def scene_exists(self, scene_id: str) -> bool:
        with self.sessions() as session:
            return session.get(Scene, scene_id) is not None

    def add_scene(
        self,
        scene_id: str,
        files: Mapping[str, str],
        note: str | None,
        *,
        domain_id: str | None = None,
    ) -> SceneRecord:
        checked = self.storage.check(files, scene_id=scene_id)
        if not checked.ok or checked.scenario is None or checked.digest is None:
            raise _invalid(
                "revision_invalid",
                t("error.revision_invalid", count=len(checked.issues)),
                issues=[issue_json(issue) for issue in checked.issues],
            )
        scenario = checked.scenario
        with self.sessions() as session:
            if domain_id is not None:
                self._domain(session, domain_id)
            if session.get(Scene, scene_id) is not None:
                raise _conflict("scene_exists", t("error.scene_exists", id=scene_id))
            moment = now()
            scene = Scene(
                id=scene_id,
                name=scenario.name,
                category=scenario.category,
                description=scenario.description,
                domain_id=domain_id,
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
        domain_id: str | None = None,
        clear_domain: bool = False,
    ) -> SceneRecord:
        with self.sessions() as session:
            scene = self._scene(session, scene_id)
            if clear_domain:
                scene.domain_id = None
            elif domain_id is not None:
                scene.domain_id = self._domain(session, domain_id).id
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

    def import_examples(self, domain_id: str | None = None) -> ImportReport:
        """匯入範例資料夾的場景（已存在的 id 略過），每個場景建立第 1 版草稿。

        domain_id 沒指定時放進「測試網站自動化」（存在的話）。
        """
        folder = self.examples_dir
        if folder is None or not folder.is_dir():
            raise _not_found("no_examples", t("error.no_examples"))
        if domain_id is None:
            with self.sessions() as session:
                if session.get(Domain, EXAMPLES_DOMAIN) is not None:
                    domain_id = EXAMPLES_DOMAIN
        else:
            self.get_domain(domain_id)
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
                self.add_scene(
                    scenario.id,
                    files,
                    note=t("revision.note_imported", path=path.name),
                    domain_id=domain_id,
                )
            except ServiceError as error:
                report.skipped.append(f"{scenario.id}：{error.message}")
                continue
            report.imported.append(scenario.id)
        wanted = sorted(
            {
                scenario.login.role
                for scenario in (validate_file(path).scenario for path in paths)
                if scenario is not None and scenario.login is not None
            }
        )
        if wanted:
            report.roles.extend(self.roles.import_examples(folder / ROLES_FILE, wanted))
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
        headless: bool | None = None,
        workflow_run_id: str | None = None,
        node_id: str | None = None,
    ) -> RunRecord:
        """排入一次執行。驗證可以用任何版本（預設最新）；正式執行只用已發布版本；
        試驗場序列的節點（workflow）用序列固定的版本，只能是發布過的版本（M6）。

        headless 沒指定時：能顯示瀏覽器視窗就用有頭模式，不能就用無頭模式。
        """
        inputs = dict(inputs or {})
        if headless is None:
            headless = not self.display
        elif not headless and not self.display:
            raise _invalid("display_unavailable", t("error.display_unavailable"))
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
            if purpose == "workflow" and revision.published_at is None:
                raise _conflict(
                    "revision_unpublished",
                    t("error.revision_unpublished", id=scene_id, number=revision.number),
                )
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
                headless=headless,
                input=inputs,
                idempotency_key=key,
                cancel_requested=False,
                created_at=now(),
                workflow_run_id=workflow_run_id,
                node_id=node_id,
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
        settled = False
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
                settled = True
            elif run.status == "running":
                run.cancel_requested = True
                notify = True
            session.commit()
            record = run_record(run)
        if notify:
            self.on_cancel(run_id)
        if settled:
            self.run_finished(run_id)
        return record

    def run_finished(self, run_id: str) -> None:
        """一次執行結束了（worker 執行完、排隊中被取消）：屬於試驗場序列時，接著排下一個節點。"""
        self.workflows.node_finished(run_id)

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
        """伺服器啟動時：上次執行到一半的任務標為失敗（排隊中的會繼續執行）。

        錄製到一半的也標為失敗（刪除可能含密碼的暫存原始稿），清掉上次調試留下的目錄。
        """
        self.recordings.recover()
        self.debug.remove_leftovers()
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
        self.workflows.recover()
        return len(runs)

    # ------------------------------------------------------------ M4：角色、入參出參、重新執行

    def _scene_infos(self) -> dict[str, tuple[str | None, tuple[str, ...]]]:
        """沒有封存的場景 → 最新版本的 (登入角色, Secrets 名稱)；依版本快取。"""
        with self.sessions() as session:
            scenes = list(session.scalars(select(Scene).where(Scene.archived.is_(False))))
        found: dict[str, tuple[str | None, tuple[str, ...]]] = {}
        for scene in scenes:
            key = (scene.id, scene.latest_number)
            if key not in self._scene_cache:
                scenario = validate_file(self.storage.scenario_path(*key)).scenario
                login = scenario.login if scenario is not None else None
                secrets = tuple(scenario.secrets) if scenario is not None else ()
                self._scene_cache[key] = (login.role if login is not None else None, secrets)
            found[scene.id] = self._scene_cache[key]
        return found

    def scene_roles(self) -> dict[str, str]:
        """沒有封存的場景 → 最新版本用到的登入角色。"""
        return {scene: role for scene, (role, _) in self._scene_infos().items() if role}

    def secret_usage(self) -> dict[str, list[str]]:
        """Secrets 名稱 → 用到它的場景與角色（角色寫成「角色：代號」）。"""
        usage: dict[str, list[str]] = {}
        for scene, (_, names) in sorted(self._scene_infos().items()):
            for name in names:
                usage.setdefault(name, []).append(scene)
        for role in self.roles.list_roles():
            settings = self.roles.login_settings(role.id)
            for name in settings.secrets if settings is not None else ():
                usage.setdefault(name, []).append(t("secrets.role_user", id=role.id))
        return usage

    def recording_defaults(self) -> dict[str, dict[str, object]]:
        """錄製頁選「既有場景的新版本」時預先填入的值：起始網址、瀏覽器、登入角色。

        起始網址是最新版本第一個開啟網址的步驟（以 / 開頭時接上預設網址）；腳本場景只能重新錄製。
        """
        defaults: dict[str, dict[str, object]] = {}
        for scene in self.list_scenes():
            try:
                scenario = self.revision_scenario(scene.id, scene.latest_number)
            except ServiceError:
                continue
            base = scene.base_url or scenario.browser.base_url
            first = next(
                (step.url for step in scenario.steps or [] if isinstance(step, GotoStep)), None
            )
            url = first or base
            if url and url.startswith("/") and base:
                url = base.rstrip("/") + url
            if url and ("{{" in url or not url.startswith(("http://", "https://"))):
                url = base
            defaults[scene.id] = {
                "url": url,
                "engine": scenario.browser.engine,
                "roleId": scenario.login.role if scenario.login is not None else None,
                "script": scenario.script is not None,
                "steps": len(scenario.steps or []),
                "revision": scene.latest_number,
            }
        return defaults

    def scene_needs(self, scenario: Scenario) -> SceneNeeds:
        """場景版本執行前要準備好的角色與 Secrets。"""
        stored = {info.name for info in self.roles.list_secrets()}
        secrets = tuple((name, name in stored or name in os.environ) for name in scenario.secrets)
        role = scenario.login.role if scenario.login is not None else None
        if role is None:
            return SceneNeeds(None, False, None, secrets)
        try:
            record = self.roles.get_role(role)
        except ServiceError:
            return SceneNeeds(role, False, None, secrets)
        return SceneNeeds(role, True, record.status, secrets)

    def save_contract(
        self,
        scene_id: str,
        *,
        base: int,
        inputs: Sequence[Mapping[str, object]] | None,
        outputs: Sequence[Mapping[str, object]] | None,
        note: str | None = None,
    ) -> RevisionRecord:
        """入參、出參的表單存檔：只改寫場景檔的這兩段，其他內容與註解不變，存成新版本。

        每一項是 ``{"name": 名稱, "previous": 原本的名稱, "type": …, …}``；入參改名時，
        場景裡引用舊名稱的 ``{{ inputs.舊名稱 }}`` 一起改。``None`` 代表那一段不動。
        """
        files = dict(self.revision_files(scene_id, base))
        renames: dict[str, str] = {}
        specs: list[dict[str, dict[str, object]] | None] = []
        for items, rename in ((inputs, True), (outputs, False)):
            if items is None:
                specs.append(None)
                continue
            converted, found = _contract_specs(items)
            if rename:
                renames.update(found)
            specs.append(converted)
        files[SCENARIO_FILE] = replace_contract(
            files[SCENARIO_FILE], inputs=specs[0], outputs=specs[1], renames=renames
        )
        return self.save_revision(
            scene_id, base=base, files=files, note=note or t("revision.note_contract")
        )

    def _section_files(self, scene_id: str, key: str, base: int, text: str) -> dict[str, str]:
        if key not in SECTION_KEYS:
            raise _not_found("section_unknown", t("error.section_unknown", key=key))
        files = dict(self.revision_files(scene_id, base))
        if self._load_scenario(scene_id, base).script is not None and key in ("steps", "verify"):
            raise _invalid("section_script", t("error.section_script"))
        section = text.replace("\r\n", "\n").strip("\n")
        _check_section(key, section)
        files[SCENARIO_FILE] = replace_section(files[SCENARIO_FILE], key, section)
        return files

    def preview_section(self, scene_id: str, key: str, *, base: int, text: str) -> Scenario:
        """換掉一段之後的場景（不存檔）；有問題時 422，問題附上段落裡的行號。"""
        files = self._section_files(scene_id, key, base, text)
        checked = self.storage.check(files, scene_id=scene_id)
        if not checked.ok or checked.scenario is None:
            issues = [issue_json(issue) for issue in checked.issues]
            _section_lines(issues, files[SCENARIO_FILE], key)
            raise _invalid(
                "revision_invalid",
                t("error.revision_invalid", count=len(issues)),
                issues=issues,
            )
        return checked.scenario

    def save_section(
        self,
        scene_id: str,
        key: str,
        *,
        base: int,
        text: str,
        note: str | None = None,
    ) -> RevisionRecord:
        """直接編輯場景檔的一段（steps、verify、inputs、outputs）：只換掉這一段，存成新版本。

        ``text`` 是這一段的原文（以 ``key:`` 開頭）；空白時移除這一段。校驗問題的行號另外附上
        段落裡的行號（``sectionLine``），方便在只顯示這一段的編輯器裡對照。
        """
        files = self._section_files(scene_id, key, base, text)
        try:
            return self.save_revision(
                scene_id,
                base=base,
                files=files,
                note=note or t("revision.note_section", section=t(f"section.{key}")),
            )
        except ServiceError as error:
            issues = error.details.get("issues")
            if isinstance(issues, list):
                _section_lines(cast("list[dict[str, object]]", issues), files[SCENARIO_FILE], key)
            raise

    def rerun(self, run_id: str, *, idempotency_key: str | None = None) -> RunRecord:
        """用同樣的入參與選項再執行一次（例如登入之後）。驗證用同一個版本，正式執行用目前發布的版本；
        試驗場序列的節點只重新執行這一個節點（同一個版本），不接著執行序列，序列請從序列執行頁繼續。
        """
        run = self.get_run(run_id)
        return self.request_run(
            run.scene_id,
            purpose=run.purpose,
            number=run.revision_number if run.purpose != "execution" else None,
            inputs=run.input,
            engine=cast("Engine | None", run.engine),
            base_url=run.base_url,
            idempotency_key=idempotency_key,
            headless=run.headless if run.headless or self.display else True,
        )
