"""服務層：場景、版本、執行的所有操作。API 與頁面都只呼叫這裡。

每個方法自己開一個資料庫交易，回傳 domain.py 的唯讀紀錄；錯誤以 :class:`ServiceError` 表示，
API 轉成 JSON、頁面轉成錯誤頁。

M11 起場景、版本、角色的定義在領域資料夾（packs.py），資料庫是它的索引：存檔、發布、封存、
搬領域都先寫資料夾再更新資料庫。發布門檻：磁碟上的內容雜湊 ＝ 版本說明檔的雜湊 ＝ 領域資料夾裡
某一份通過的驗證紀錄的雜湊（不管是哪一台伺服器驗證的）。改內容就是新版本，要重新驗證。

M4 的登入角色與 Secrets（roles.py）、錄製（recordings.py）、調試工作階段（debugging.py）
各自一個模組，由這裡建立：``services.roles``、``services.recordings``、``services.debug``；
M6 的自由試驗場序列（workflows.py）是 ``services.workflows``；專案空間的專案（projects.py）是
``services.projects``。
M14 的對外 Agent API 用戶端（agents.py）是 ``services.agents``；路由在 agent_api.py。
"""

import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

from sqlalchemy import and_, func, or_, select
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
from rpa_core.dsl.files import ATTACHMENT_DIR, is_attachment_path
from rpa_core.dsl.sources import attachment_files, scenario_sources
from rpa_core.i18n import DEFAULT_LOCALE, Locale
from rpa_core.pack import PackSource, PublishedRef, SceneManifest, parse_timestamp, timestamp
from rpa_runner.contract import prepare_inputs
from rpa_runner.files import RESULT, SCREENSHOT
from rpa_runner.run import new_run_id
from rpa_server.addresses import PortalAddress
from rpa_server.agents import AgentService
from rpa_server.composite_report import build_composite_report
from rpa_server.config import EXAMPLES_DOMAIN
from rpa_server.debugging import DebugManager
from rpa_server.device_updates import DeviceUpdates
from rpa_server.devices import RecorderHub
from rpa_server.dispatch import WorkerHub
from rpa_server.domain import (
    DOMAIN_ID,
    LOCAL_WORKER,
    TARGETS,
    DomainRecord,
    Engine,
    Purpose,
    RevisionRecord,
    RevisionStatus,
    RunRecord,
    RunStatus,
    SceneCard,
    SceneRecord,
    Target,
    VerificationRecord,
    issue_json,
    now,
)
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.gitsync import GitSource, GitSync
from rpa_server.i18n import follow_locale, t
from rpa_server.jobs import RunQueue
from rpa_server.models import Domain, Revision, Role, Run, Scene
from rpa_server.models import Workflow as WorkflowRow
from rpa_server.packs import COMPOSITES_DOMAIN, UNASSIGNED_DOMAIN, LoadReport, PackStore
from rpa_server.projects import ProjectService
from rpa_server.recordings import RecordingService
from rpa_server.replay import build_replay
from rpa_server.roles import RoleService
from rpa_server.secret_store import SecretStore
from rpa_server.storage import SCENARIO_FILE, Storage, new_scene_template
from rpa_server.uploads import UploadLimits, UploadService, definition_uploads
from rpa_server.videos import VideoService, VideoSettings, video_details
from rpa_server.workflows import WorkflowService
from rpa_worker.environment import external_url
from rpa_worker.pairing import Invite

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

logger = logging.getLogger("rpa_server.services")

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
        "accept",
        "maxSize",
        "multiple",
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
        missing=scene.missing,
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
        verified=revision.verified,
        problem=revision.problem,
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
        target=cast("Target", run.target),
        worker_id=run.worker_id,
        video=video_details(run),
        client_id=run.client_id,
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
        local_worker: bool = True,
        worker_port: int | None = None,
        worker_host: str = "0.0.0.0",
        portal_port: int | None = None,
        upload_limits: UploadLimits | None = None,
        input_folders: Sequence[Path] = (),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.uploads = UploadService(sessions, storage.root, upload_limits)
        """上傳的檔案（M7c）：檔案入參參照的檔案、執行前檢查與保留規則。"""
        self.examples_dir = examples_dir
        self.display = display
        """這台電腦能不能顯示瀏覽器視窗；能的話執行預設用有頭模式。"""
        self.local_worker = local_worker
        """這台電腦執不執行（rpa serve --no-local-worker 時不執行，只給遠端 worker；M9a）。"""
        self.worker_port = worker_port
        """對外埠（Worker API、Client API）；None 代表沒有開放（頁面提示怎麼開啟）。"""
        self.worker_host = worker_host
        self.portal_port = portal_port
        """管理頁面聽的埠（rpa serve 填入；測試是 None）：錄製的起始網址不能指向 Portal 自己。"""
        self._scene_cache: dict[tuple[str, int], tuple[str | None, tuple[str, ...]]] = {}
        self.packs = PackStore(sessions, storage)
        """領域資料夾：伺服器代號、寫入、載入、驗證紀錄、遷移（M11）。"""
        self.recorders = RecorderHub(sessions, locale=locale)
        """錄製端的登記、上線，以及交給它執行的互動子程序（M10.2）。"""
        self.device_updates = DeviceUpdates.detect(sessions)
        """裝置跟著伺服器的版本更新（ADR 0018）：更新檔、「自動更新裝置」與裝置的回報。"""
        self.roles = RoleService(
            sessions,
            storage,
            SecretStore(storage.secrets),
            display=display,
            locale=locale,
            scene_roles=self.scene_roles,
            hosts=self.recorders,
            packs=self.packs,
            default_domain=self.unassigned_domain,
        )
        self.git = GitSync(
            sessions,
            storage,
            lock=self.packs.lock,
            reload=self.reload_domain,
            secret_values=self.roles.secrets.values,
            operator=self.packs.operator,
            on_source=self.packs.refresh_sources,
        )
        """領域資料夾的 git 同步（M11 PR 3）。"""
        self.packs.source_of = self._pack_source
        self.recordings = RecordingService(
            sessions,
            storage,
            self,
            self.roles,
            display=display,
            locale=locale,
            hosts=self.recorders,
        )
        self.debug = DebugManager(
            storage, self, self.roles, display=display, locale=locale, hosts=self.recorders
        )
        self.projects = ProjectService(sessions)
        """專案空間的專案：組合場景的分組，只在資料庫（2026-10-23）。"""
        self.workflows = WorkflowService(sessions, self)
        # 組合場景節點固定值用到的上傳檔不因保留期限刪除（M7c D7）
        self.uploads.pinned = self._pinned_uploads
        self.videos = VideoService(sessions, storage)
        """錄影的設定、釘選與保留規則（M12）。"""
        self.queue = RunQueue(
            sessions,
            storage,
            self.roles,
            self.videos,
            uploads=self.uploads,
            input_folders=tuple(input_folders),
        )
        """執行佇列：本機 worker 的任務來源；遠端 worker 經由 workers 領取（M9a）。"""
        self.queue.on_finished = self.run_finished  # 試驗場序列：一個節點結束就排下一個（M6）
        self.workers = WorkerHub(
            sessions, storage, self.queue, self.roles, locale=locale, local_worker=local_worker
        )
        """遠端 worker 的登記與分派（M9a）。"""
        self.agents = AgentService(sessions)
        """對外 Agent API 的用戶端、金鑰、限額與稽核（M14）。"""
        self.on_queued: Callable[[], None] = lambda: None
        """有新的執行排入佇列（叫醒 worker）。"""
        self.on_cancel: Callable[[str], object] = lambda run_id: None
        """要求取消執行中的任務。"""

    # ------------------------------------------------------------ 領域資料夾（M11）

    def startup(self) -> list[LoadReport]:
        """伺服器啟動時：產生伺服器代號、遷移 M11 之前的資料（先備份）、載入全部領域資料夾。"""
        self.packs.server()
        self.packs.migrate_legacy(
            unassigned_name=t("domain.unassigned_name"),
            unassigned_description=t("domain.unassigned_description"),
            composites_name=t("domain.composites_name"),
            composites_description=t("domain.composites_description"),
        )
        reports = self.packs.load_all()
        self._scene_cache.clear()
        return reports

    def reload_domain(self, domain_id: str) -> LoadReport:
        """重新載入一個領域資料夾（在資料夾外面改了檔案之後，D10）。"""
        self.get_domain(domain_id)
        report = self.packs.load_domain(domain_id)
        self._scene_cache.clear()
        return report

    def server_info(self) -> dict[str, str]:
        server = self.packs.server()
        return {"id": server.id, "name": server.name}

    def rename_server(self, name: str) -> dict[str, str]:
        try:
            server = self.packs.rename_server(name)
        except ValueError:
            raise _invalid("server_name_missing", t("error.server_name_missing")) from None
        return {"id": server.id, "name": server.name}

    def unassigned_domain(self) -> str:
        """「未分類」領域；還沒有時建立（沒指定領域的場景與角色放這裡）。"""
        with self.packs.lock, self.sessions() as session:
            if session.get(Domain, UNASSIGNED_DOMAIN) is None:
                self._new_domain(
                    session,
                    UNASSIGNED_DOMAIN,
                    t("domain.unassigned_name"),
                    t("domain.unassigned_description"),
                )
                session.commit()
        return UNASSIGNED_DOMAIN

    def composites_domain(self) -> str:
        """「組合場景」領域；還沒有時建立（沒指定領域的新組合場景放這裡，M11 PR 2）。"""
        with self.packs.lock, self.sessions() as session:
            if session.get(Domain, COMPOSITES_DOMAIN) is None:
                self._new_domain(
                    session,
                    COMPOSITES_DOMAIN,
                    t("domain.composites_name"),
                    t("domain.composites_description"),
                )
                session.commit()
        return COMPOSITES_DOMAIN

    def _new_domain(
        self, session: Session, domain_id: str, name: str, description: str | None
    ) -> Domain:
        """新增領域：資料庫一列，加上領域資料夾的 pack.yaml（呼叫的人提交交易）。"""
        last = session.scalar(select(func.max(Domain.position)))
        domain = Domain(
            id=domain_id,
            name=name,
            description=description,
            position=(last if last is not None else -1) + 1,
            created_at=now(),
            problems=[],
            loaded_at=now(),
        )
        session.add(domain)
        session.flush()
        self.packs.write_pack(domain_id, name, description)
        return domain

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
            .where(
                Scene.domain_id == domain.id,
                Scene.archived.is_(False),
                Scene.missing.is_(False),
            )
        )
        roles = session.scalar(
            select(func.count())
            .select_from(Role)
            .where(Role.domain_id == domain.id, Role.missing.is_(False))
        )
        name, description = domain.name, domain.description
        # 系統建立的領域：沒改過名稱與說明就跟著介面語言
        if domain.id == EXAMPLES_DOMAIN:
            name = follow_locale(name, "domain.testsite_name") or name
            description = follow_locale(description, "domain.testsite_description")
        elif domain.id == UNASSIGNED_DOMAIN:
            name = follow_locale(name, "domain.unassigned_name") or name
            description = follow_locale(description, "domain.unassigned_description")
        elif domain.id == COMPOSITES_DOMAIN:
            name = follow_locale(name, "domain.composites_name") or name
            description = follow_locale(description, "domain.composites_description")
        return DomainRecord(
            id=domain.id,
            name=name,
            description=description,
            position=domain.position,
            scene_count=count or 0,
            created_at=domain.created_at,
            problems=tuple(domain.problems or ()),
            loaded_at=domain.loaded_at,
            role_count=roles or 0,
        )

    def list_domains(self) -> list[DomainRecord]:
        """全部領域，依排列順序；就是場景管理的二級選單。"""
        with self.sessions() as session:
            domains = session.scalars(select(Domain).order_by(Domain.position, Domain.created_at))
            return [self._domain_record(session, domain) for domain in domains]

    def get_domain(self, domain_id: str) -> DomainRecord:
        with self.sessions() as session:
            return self._domain_record(session, self._domain(session, domain_id))

    def reorder_domains(self, ids: Sequence[str]) -> list[DomainRecord]:
        """依 ``ids`` 重排全部領域（領域管理的上移、下移）；場景管理的領域選單照這個順序。

        順序只存在資料庫（domains.position），不寫進領域資料夾與 git。``ids`` 要剛好是現在的
        全部領域；有人在別處新增或刪除了領域時回 409，請重新整理再排。
        """
        with self.packs.lock, self.sessions() as session:
            domains = {domain.id: domain for domain in session.scalars(select(Domain))}
            if len(ids) != len(set(ids)) or set(ids) != set(domains):
                raise _conflict("domain_order_changed", t("error.domain_order_changed"))
            for position, domain_id in enumerate(ids):
                domains[domain_id].position = position
            session.commit()
        return self.list_domains()

    def create_domain(
        self, domain_id: str, name: str, description: str | None = None
    ) -> DomainRecord:
        domain_id, name = domain_id.strip(), name.strip()
        if not DOMAIN_ID.fullmatch(domain_id):
            raise _invalid("domain_id_invalid", t("error.domain_id_invalid", id=domain_id))
        if not name:
            raise _invalid("domain_name_missing", t("error.domain_name_missing"))
        with self.packs.lock, self.sessions() as session:
            # 資料夾已經有同代號的領域（例如從別處放進來、還沒載入）也算已經用過
            if session.get(Domain, domain_id) is not None or self.packs.manifest(domain_id):
                raise _conflict("domain_exists", t("error.domain_exists", id=domain_id))
            domain = self._new_domain(session, domain_id, name, (description or "").strip() or None)
            session.commit()
            return self._domain_record(session, domain)

    def _pack_source(self, domain_id: str) -> PackSource | None:
        """領域的 git 資料來源，寫成 pack.yaml requires 的 source（不含帳號與權杖）。"""
        try:
            source = self.git.source(domain_id)
        except ServiceError:
            return None
        if source is None:
            return None
        return PackSource(repo=source.url, directory=source.directory, branch=source.branch)

    def create_domain_from_git(
        self,
        domain_id: str,
        source: GitSource,
        *,
        name: str | None = None,
        description: str | None = None,
        token: str | None = None,
    ) -> DomainRecord:
        """從 git 新增領域（第 10.1 節）：遠端目錄裡有 pack.yaml 就用它的代號與名稱並拉取；
        目錄還不存在就建立空的領域，第一次推送時建立目錄。拉取失敗時領域照樣建立，錯誤記在同步狀態。
        """
        probe = self.git.probe(source, token)
        domain_id = domain_id.strip() or (probe.pack_id or "")
        if probe.pack_id is not None and probe.pack_id != domain_id:
            raise invalid(
                "sync_pack_id",
                t("error.sync_pack_id", id=domain_id, pack=probe.pack_id),
            )
        self.create_domain(
            domain_id,
            (name or "").strip() or probe.pack_name or domain_id,
            description if description is not None else probe.pack_description,
        )
        self.git.set_source(domain_id, source, token=token)
        try:
            if probe.state == "ready":
                self.git.pull(domain_id, prefer_remote=True)
            else:
                self.git.test(domain_id)
        except ServiceError as error:
            logger.warning("%s", t("sync.startup_pull_failed", id=domain_id, detail=error.message))
        return self.get_domain(domain_id)

    def update_domain(
        self, domain_id: str, *, name: str | None = None, description: str | None = None
    ) -> DomainRecord:
        """改名稱或說明（寫進 pack.yaml）；代號不能改（網址、場景與資料夾都用它）。"""
        with self.packs.lock, self.sessions() as session:
            domain = self._domain(session, domain_id)
            if name is not None:
                if not name.strip():
                    raise _invalid("domain_name_missing", t("error.domain_name_missing"))
                domain.name = name.strip()
            if description is not None:
                domain.description = description.strip() or None
            self.packs.write_pack(domain_id, domain.name, domain.description)
            session.commit()
            return self._domain_record(session, domain)

    def delete_domain(self, domain_id: str) -> None:
        """只能刪除沒有場景（包含封存的）與角色的領域；領域資料夾一起刪除。"""
        with self.packs.lock, self.sessions() as session:
            domain = self._domain(session, domain_id)
            used = session.scalar(
                select(func.count())
                .select_from(Scene)
                .where(Scene.domain_id == domain_id, Scene.missing.is_(False))
            )
            if used:
                raise _conflict(
                    "domain_not_empty", t("error.domain_not_empty", id=domain_id, count=used)
                )
            roles = session.scalar(
                select(func.count())
                .select_from(Role)
                .where(Role.domain_id == domain_id, Role.missing.is_(False))
            )
            if roles:
                raise _conflict(
                    "domain_has_roles", t("error.domain_has_roles", id=domain_id, count=roles)
                )
            composites = session.scalar(
                select(func.count())
                .select_from(WorkflowRow)
                .where(WorkflowRow.domain_id == domain_id, WorkflowRow.missing.is_(False))
            )
            if composites:
                raise _conflict(
                    "domain_has_composites",
                    t("error.domain_has_composites", id=domain_id, count=composites),
                )
            # 來源缺失的場景、角色、組合場景只剩執行紀錄引用，不再屬於任何領域
            for scene in session.scalars(select(Scene).where(Scene.domain_id == domain_id)):
                scene.domain_id = None
            for role in session.scalars(select(Role).where(Role.domain_id == domain_id)):
                role.domain_id = None
            for workflow in session.scalars(
                select(WorkflowRow).where(WorkflowRow.domain_id == domain_id)
            ):
                workflow.domain_id = None
            session.flush()
            session.delete(domain)
            session.commit()
            self.packs.remove_pack(domain_id)
        self.git.forget(domain_id)  # 權杖、金鑰與工作副本（遠端的資料不動）

    def seed_examples_domain(self) -> ImportReport | None:
        """還沒有任何領域時：建立「測試網站自動化」，把已經存在的範例場景放進去，再匯入其餘範例。"""
        with self.packs.lock, self.sessions() as session:
            existing = session.scalars(select(Domain.id)).all()
            if any(domain_id != UNASSIGNED_DOMAIN for domain_id in existing):
                return None
            self._new_domain(
                session,
                EXAMPLES_DOMAIN,
                t("domain.testsite_name"),
                t("domain.testsite_description"),
            )
            session.commit()
            example_ids = [scenario_id for scenario_id, _ in self._examples()]
            adopt = list(
                session.scalars(
                    select(Scene.id).where(
                        or_(Scene.domain_id.is_(None), Scene.domain_id == UNASSIGNED_DOMAIN),
                        Scene.id.in_(example_ids),
                    )
                )
            )
        for scene_id in adopt:  # 之前沒有領域時匯入的範例，放進「測試網站自動化」
            self.update_scene(scene_id, domain_id=EXAMPLES_DOMAIN)
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
        statement = select(Scene).where(Scene.missing.is_(False)).order_by(Scene.id)
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

    def worker_wait(self, run_id: str) -> dict[str, str | None] | None:
        """排隊中的執行是不是在等遠端 worker：沒有線上、可以接的 worker 時回傳提示用的資料（M9a）。

        回傳 ``{"worker": 名稱}``（指定給某台 worker，例如序列固定的那台）或 ``{"worker": None}``
        （任何一台遠端 worker）；本機會執行、已經有人領取或不是排隊中時回傳 None。
        """
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None or run.status != "queued" or run.worker_id is not None:
                return None
            target, required = run.target, run.required_worker
        if target == "local" or required == LOCAL_WORKER:
            return None
        if required is None and target == "any" and self.local_worker:
            return None
        records = self.workers.list_workers()
        ready = {record.id for record in records if record.status in ("online", "busy")}
        if required is not None:
            if required in ready:
                return None
            names = {record.id: record.name for record in records}
            return {"worker": names.get(required, required)}
        return None if ready else {"worker": None}

    def run_locations(self) -> list[tuple[str, str]]:
        """執行報告「執行位置」篩選的選項：本機、登記的 worker，以及執行過但已刪除的 worker。

        沒有任何遠端 worker 時回傳空清單（不顯示這個篩選）。
        """
        names = self.workers.names()
        with self.sessions() as session:
            used = session.scalars(
                select(Run.worker_id).where(Run.worker_id.is_not(None)).distinct()
            ).all()
        others = sorted({value for value in used if value} - names.keys())
        options = [(LOCAL_WORKER, names[LOCAL_WORKER])]
        options += sorted(
            ((key, name) for key, name in names.items() if key != LOCAL_WORKER),
            key=lambda item: item[1].casefold(),
        )
        options += [(value, value) for value in others]
        return options if len(options) > 1 else []

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
                .where(Revision.scene_id == scene_id, Revision.missing.is_(False))
                .order_by(Revision.number.desc())
            )
            return [revision_record(revision, scene) for revision in revisions]

    def verifications(self, scene_id: str) -> list[VerificationRecord]:
        """場景的驗證紀錄（領域資料夾裡的，不管是哪一台伺服器驗證的），最新的在前。"""
        self.get_scene(scene_id)
        entry, _ = self.packs.scene_entry(scene_id)
        if entry is None:
            return []
        records: list[tuple[str, VerificationRecord]] = []
        with self.sessions() as session:
            for number, revision in entry.revisions.items():
                digest = revision.info.hash if revision.info is not None else None
                for item in revision.verifications:
                    record = item.record
                    finished = parse_timestamp(record.finished_at)
                    here = (
                        record.server.id == self.packs.server().id
                        and session.get(Run, item.id) is not None
                    )
                    records.append(
                        (
                            f"{finished.timestamp():020.3f}{item.id}",
                            VerificationRecord(
                                id=item.id,
                                revision=number,
                                status=record.status,
                                matches=digest is not None and record.hash == digest,
                                finished_at=finished,
                                by=record.by,
                                server_id=record.server.id,
                                server_name=record.server.name,
                                worker=record.worker.id,
                                engine=record.engine,
                                headless=record.headless,
                                here=here,
                            ),
                        )
                    )
        return [record for _, record in sorted(records, key=lambda item: item[0], reverse=True)]

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
        note: str | None = None,
    ) -> SceneRecord:
        scene_id, name = scene_id.strip(), name.strip()
        category = (category or "").strip() or None
        if not SCENE_ID.fullmatch(scene_id):
            raise _invalid("scene_id_invalid", t("error.scene_id_invalid", id=scene_id))
        if not name:
            raise _invalid("scene_name_missing", t("error.scene_name_missing"))
        files = {SCENARIO_FILE: new_scene_template(scene_id, name, category)}
        return self.add_scene(
            scene_id, files, note=note or t("revision.note_created"), domain_id=domain_id
        )

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
        attachments: Mapping[str, bytes] | None = None,
    ) -> SceneRecord:
        attachments = dict(attachments or {})
        checked = self.storage.check(files, scene_id=scene_id, attachments=attachments)
        if not checked.ok or checked.scenario is None or checked.digest is None:
            raise _invalid(
                "revision_invalid",
                t("error.revision_invalid", count=len(checked.issues)),
                issues=[issue_json(issue) for issue in checked.issues],
            )
        scenario = checked.scenario
        if domain_id is None:
            domain_id = self.unassigned_domain()  # 每個場景都在某個領域資料夾裡（M11）
        with self.packs.lock, self.sessions() as session:
            self._domain(session, domain_id)
            if session.get(Scene, scene_id) is not None:
                raise _conflict("scene_exists", t("error.scene_exists", id=scene_id))
            if self.storage.scene_domain(scene_id) is not None:
                # 資料夾裡已經有同代號的場景（例如另一個領域的資料夾載入時略過的）
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
                missing=False,
            )
            revision = Revision(
                scene_id=scene_id,
                number=1,
                content_hash=checked.digest,
                kind="script" if scenario.script is not None else "dsl",
                status="draft",
                note=note,
                created_at=moment,
                missing=False,
                verified=False,
            )
            self.storage.place_scene(scene_id, domain_id)
            self._write_revision(
                session,
                scene_id,
                1,
                checked.files,
                [scene, revision],
                new_scene=True,
                attachments=attachments,
            )
            return scene_record(scene, revision)

    def _write_revision(
        self,
        session: Session,
        scene_id: str,
        number: int,
        files: Mapping[str, str],
        rows: Sequence[Scene | Revision],
        *,
        new_scene: bool = False,
        attachments: Mapping[str, bytes] | None = None,
    ) -> None:
        """寫入資料庫列與領域資料夾裡的版本，一起提交；任何一步失敗都不留下半個版本。

        先 flush 資料庫列：(場景, 版本號碼) 有唯一約束，flush 成功代表這個號碼只屬於本交易，
        這時版本目錄如果已經存在，只可能是之前中斷留下的殘留，可以安全移除。
        版本目錄旁邊寫版本說明檔（雜湊、時間、操作者、伺服器）；新場景另外寫 scene.yaml。
        呼叫的人要持有 ``packs.lock``，並先用 storage.place_scene 登記場景的領域。
        """
        try:
            for row in rows:  # 依外鍵順序寫入：場景、再版本
                session.add(row)
                session.flush()
        except IntegrityError:
            session.rollback()
            if new_scene:
                self.storage.forget_scene(scene_id)
            raise _conflict(
                "revision_conflict", t("error.revision_conflict", id=scene_id)
            ) from None
        revision = next(row for row in rows if isinstance(row, Revision))
        self.storage.discard(scene_id, number)
        try:
            self.storage.save(scene_id, number, files, attachments)
            self.packs.write_revision_info(
                scene_id, number, revision.content_hash, revision.note, revision.created_at
            )
            if new_scene:
                self.packs.write_scene(SceneManifest(id=scene_id))
            session.commit()
        except BaseException:
            session.rollback()
            self.packs.discard_revision(scene_id, number, new_scene=new_scene)
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
        if clear_domain:
            domain_id = self.unassigned_domain()  # 「沒有領域」就是「未分類」（M11）
        with self.packs.lock, self.sessions() as session:
            scene = self._scene(session, scene_id)
            if domain_id is not None and domain_id != scene.domain_id:
                target = self._domain(session, domain_id).id
                try:
                    self.packs.move_scene(scene_id, target)
                except FileExistsError:
                    raise _conflict("scene_exists", t("error.scene_exists", id=scene_id)) from None
                scene.domain_id = target
            if clear_base_url:
                scene.base_url = None
            elif base_url is not None:
                scene.base_url = _check_base_url(base_url)
            if archived is not None and archived != scene.archived:
                manifest = self.packs.scene_manifest(scene_id)
                self.packs.write_scene(manifest.model_copy(update={"archived": archived}))
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
        attachments: Mapping[str, bytes] | None = None,
    ) -> RevisionRecord:
        """以最新版本為基礎存成新版本；base 不是最新版本時回 409（別人已經存過）。

        ``attachments`` 是新版本的場景附件（M7c）；沒給時沿用 base 版本的附件（編輯場景檔不會
        弄丟附件）。
        """
        with self.packs.lock, self.sessions() as session:
            scene = self._scene(session, scene_id)
            if scene.archived:
                raise _conflict("scene_archived", t("error.scene_archived", id=scene_id))
            if base != scene.latest_number:
                raise _conflict(
                    "stale_base",
                    t("error.stale_base", base=base, latest=scene.latest_number),
                    latest=scene.latest_number,
                )
            if attachments is None:
                attachments = self.storage.load_attachments(scene_id, base)
            checked = self.storage.check(files, scene_id=scene_id, attachments=attachments)
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
                missing=False,
                verified=False,
            )
            scene.latest_number = number
            scene.name = scenario.name
            scene.category = scenario.category
            scene.description = scenario.description
            scene.updated_at = moment
            self._write_revision(
                session,
                scene_id,
                number,
                checked.files,
                [scene, revision],
                attachments=attachments,
            )
            return revision_record(revision, scene)

    # ------------------------------------------------------------ 場景附件（M7c）

    def _pinned_uploads(self) -> set[str]:
        """組合場景固定入參用到的上傳檔：每個組合場景的最新定義與已發布的版本（沒封存的）。"""
        with self.sessions() as session:
            columns = (WorkflowRow.definition, WorkflowRow.code, WorkflowRow.published_number)
            rows = session.execute(select(*columns).where(WorkflowRow.archived.is_(False))).all()
        found: set[str] = set()
        for definition, code, published in rows:
            found.update(definition_uploads(definition))
            if published is None:
                continue
            try:
                workflow = self.workflows.revision_workflow(code, published)
            except ServiceError:
                continue
            found.update(definition_uploads(workflow.model_dump(mode="json", by_alias=True)))
        return found

    def revision_attachments(self, scene_id: str, number: int) -> list[dict[str, object]]:
        """版本的場景附件：路徑、大小、sha256（給頁面與 API）。"""
        self.get_scene(scene_id)
        return [
            {
                "path": name,
                "name": name.removeprefix(f"{ATTACHMENT_DIR}/"),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in self.storage.load_attachments(scene_id, number).items()
        ]

    def attachment_path(self, scene_id: str, number: int, name: str) -> Path:
        """版本裡一個附件在伺服器的位置；不在時 404。"""
        self.get_scene(scene_id)
        relative = f"{ATTACHMENT_DIR}/{name}"
        path = self.storage.revision_dir(scene_id, number) / relative
        if not is_attachment_path(relative) or not path.is_file():
            raise _not_found("attachment_not_found", t("error.attachment_not_found", name=name))
        return path

    def save_attachment(
        self, scene_id: str, *, base: int, name: str, data: bytes, note: str | None = None
    ) -> RevisionRecord:
        """加上或換掉一個附件，存成新版本（場景檔不變；版本不可變，附件跟著版本）。"""
        relative = f"{ATTACHMENT_DIR}/{name}"
        if not is_attachment_path(relative):
            raise _invalid("attachment_name", t("error.attachment_name", name=name))
        attachments = self.storage.load_attachments(scene_id, base)
        attachments[relative] = data
        return self.save_revision(
            scene_id,
            base=base,
            files=self.revision_files(scene_id, base),
            note=note or t("revision.note_attachment_saved", name=name),
            attachments=attachments,
        )

    def delete_attachment(
        self, scene_id: str, *, base: int, name: str, note: str | None = None
    ) -> RevisionRecord:
        """拿掉一個附件，存成新版本；入參的預設值還在用時，校驗會指出。"""
        relative = f"{ATTACHMENT_DIR}/{name}"
        attachments = self.storage.load_attachments(scene_id, base)
        if relative not in attachments:
            raise _not_found("attachment_not_found", t("error.attachment_not_found", name=name))
        del attachments[relative]
        return self.save_revision(
            scene_id,
            base=base,
            files=self.revision_files(scene_id, base),
            note=note or t("revision.note_attachment_deleted", name=name),
            attachments=attachments,
        )

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
            sources = scenario_sources(path, scenario)
            attachments = set(attachment_files(path.parent))
            files = {
                (SCENARIO_FILE if relative == path.name else relative): (
                    path.parent / relative
                ).read_text(encoding="utf-8")
                for relative in sources
                if relative not in attachments
            }
            try:
                self.add_scene(
                    scenario.id,
                    files,
                    note=t("revision.note_imported", path=path.name),
                    domain_id=domain_id,
                    attachments={
                        relative: (path.parent / relative).read_bytes() for relative in attachments
                    },
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
            report.roles.extend(
                self.roles.import_examples(folder / ROLES_FILE, wanted, domain_id=domain_id)
            )
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
        target: Target | None = None,
        required_worker: str | None = None,
        client_id: str | None = None,
    ) -> RunRecord:
        """排入一次執行。驗證可以用任何版本（預設最新）；正式執行只用已發布版本；
        試驗場序列的節點（workflow）用序列固定的版本，只能是發布過的版本（M6）。

        target 是執行位置（M9a），沒指定時用預設執行位置；
        required_worker 指定只能由哪台 worker 執行；client_id 是觸發的 API 用戶端（M14）。
        headless 沒指定時：執行的地方能顯示瀏覽器視窗就用有頭模式，不能就用無頭模式。
        """
        inputs = dict(inputs or {})
        target = self.resolve_target(target)
        headless = self.resolve_headless(headless, target)
        key = (idempotency_key or "").strip() or None
        with self.sessions() as session:
            if key is not None:
                existing = session.scalars(select(Run).where(Run.idempotency_key == key)).first()
                if existing is not None:
                    return run_record(existing)
            scene = self._scene(session, scene_id)
            if scene.missing:
                raise _conflict("scene_missing", t("error.scene_missing", id=scene_id))
            if scene.archived:
                raise _conflict("scene_archived", t("error.scene_archived", id=scene_id))
            if purpose == "execution":
                if scene.published_number is None:
                    raise _conflict("not_published", t("error.not_published", id=scene_id))
                number = scene.published_number
            revision = self._revision(session, scene_id, number or scene.latest_number)
            self._check_usable(revision)
            if purpose == "workflow" and revision.published_at is None:
                raise _conflict(
                    "revision_unpublished",
                    t("error.revision_unpublished", id=scene_id, number=revision.number),
                )
            scenario = self._load_scenario(scene_id, revision.number)
            _, problems = prepare_inputs(scenario, inputs)
            if problems:
                raise _invalid(
                    "inputs_invalid",
                    t("error.inputs_invalid", count=len(problems)),
                    problems=[{"name": item.name, "message": item.message} for item in problems],
                )
            # 檔案入參（M7c）：上傳檔在不在、大小與類型；檔名、大小、sha256 以伺服器的為準
            inputs = self.uploads.require(
                scenario, inputs, self.storage.attachments(scene_id, revision.number)
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
                target=target,
                required_worker=required_worker,
                client_id=client_id,
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
        self.uploads.touch(inputs.values())
        self.on_queued()
        return record

    def resolve_target(self, target: Target | None) -> Target:
        """執行位置：沒指定時用預設；要遠端卻沒有登記任何遠端 worker 時拒絕（M9a）。"""
        if target is None:
            target = self.workers.default_target()
            if target == "local" and not self.local_worker:
                target = "any"
        if target == "local" and not self.local_worker:
            raise _conflict("local_worker_off", t("error.local_worker_off"))
        if target != "local" and not self.workers.has_remote() and not self.local_worker:
            raise _conflict("no_remote_worker", t("error.no_remote_worker"))
        if target == "remote" and not self.workers.has_remote():
            raise _conflict("no_remote_worker", t("error.no_remote_worker"))
        return target

    def display_here(self) -> bool:
        """操作的那台能不能開瀏覽器視窗（錄製、逐步調試、人工登入）。

        瀏覽器開在操作的那台：透過錄製端時看錄製端回報的（M10.2），否則看伺服器這台。
        伺服器是沒有畫面的 Linux 時，透過 Mac 的錄製端照樣可以錄製與人工登入。
        """
        via = self.recorders.current()
        return self.recorders.display(via) if via is not None else self.display

    def portal_address(self, host: str | None, received_port: int | None) -> PortalAddress:
        """操作者連到管理 Portal 的位址（請求的 Host 與收到請求的埠）：錄製的起始網址不能是它。"""
        return PortalAddress.of(
            host,
            (self.portal_port, self.worker_port, received_port),
            on_server=self.recorders.current() is None,
        )

    def can_display(self, target: Target) -> bool:
        """執行的地方能不能顯示瀏覽器視窗：本機看這台電腦，遠端看有沒有能顯示的 worker。"""
        local = self.display and self.local_worker
        if target == "local":
            return local
        remote = self.workers.has_remote() and self.workers.remote_display()
        return remote if target == "remote" else local or remote

    def locations(self) -> dict[str, object]:
        """執行表單的「執行位置」：有沒有遠端 worker、本機執不執行、預設、各位置能不能有頭模式。"""
        remote = self.workers.has_remote()
        default = self.workers.default_target()
        if default == "local" and not self.local_worker:
            default = "any"
        if default == "remote" and not remote:
            default = "local" if self.local_worker else "any"
        return {
            "remote": remote,
            "local": self.local_worker,
            "default": default,
            "display": {target: self.can_display(target) for target in TARGETS},
        }

    def external_url(self) -> str | None:
        """對外埠在區網上的網址（裝置邀請、worker 的 --server）；沒開對外埠時是 None。"""
        if self.worker_port is None:
            return None
        return external_url(self.worker_host, self.worker_port)

    def invite_device(self, worker_id: str) -> dict[str, object]:
        """產生裝置邀請（M10.1）：要先開對外埠，邀請裡帶它的網址。代碼只有這次拿得到。"""
        server = self.external_url()
        if server is None:
            raise _conflict("invite_needs_port", t("error.invite_needs_port"))
        invitation = self.workers.create_invite(worker_id)
        invite = Invite(server, invitation.code, "worker")
        return {
            "worker": invitation.worker.to_json(),
            "invite": {
                "line": invite.line(),
                "server": server,
                "code": invitation.code,
                "app": invitation.app,
                "expiresAt": invitation.expires_at.isoformat(timespec="seconds"),
            },
        }

    def invite_recorder(self, recorder_id: str) -> dict[str, object]:
        """產生錄製端的邀請（M10.2）：和 Worker 相同，要先開對外埠；代碼只有這次拿得到。"""
        server = self.external_url()
        if server is None:
            raise _conflict("invite_needs_port", t("error.invite_needs_port"))
        invitation = self.recorders.create_invite(recorder_id)
        invite = Invite(server, invitation.code, "recorder")
        return {
            "recorder": invitation.recorder.to_json(),
            "invite": {
                "line": invite.line(),
                "server": server,
                "code": invitation.code,
                "app": "recorder",
                "expiresAt": invitation.expires_at.isoformat(timespec="seconds"),
            },
        }

    def resolve_headless(self, headless: bool | None, target: Target) -> bool:
        if headless is None:
            return not self.can_display(target)
        if not headless and not self.can_display(target):
            raise _invalid("display_unavailable", t("error.display_unavailable"))
        return headless

    def publish(self, scene_id: str, number: int) -> SceneRecord:
        """發布版本（M11 的門檻，第 8 節）：磁碟上的內容雜湊 ＝ 版本說明檔的雜湊 ＝ 領域資料夾裡
        某一份通過的驗證紀錄的雜湊，不管是哪一台伺服器驗證的。寫進 scene.yaml 的 published。
        """
        with self.packs.lock, self.sessions() as session:
            scene = self._scene(session, scene_id)
            revision = self._revision(session, scene_id, number)
            if self.storage.digest(scene_id, number) != revision.content_hash:
                raise _conflict(
                    "content_changed", t("error.content_changed", id=scene_id, number=number)
                )
            self._check_usable(revision)
            entry, _ = self.packs.scene_entry(scene_id)
            target = entry.revisions.get(number) if entry is not None else None
            proofs = target.proofs() if target is not None else []
            if entry is None or not proofs:
                raise _conflict(
                    "not_validated", t("error.not_validated", id=scene_id, number=number)
                )
            moment = now()
            published = PublishedRef(
                revision=number,
                verification=proofs[0].id,
                at=timestamp(moment),
                by=self.packs.operator(),
                server=self.packs.server(),
            )
            self.packs.write_scene(entry.manifest.model_copy(update={"published": published}))
            scene.published_number = number
            scene.updated_at = moment
            revision.published_at = moment
            revision.verified = True
            session.commit()
            return scene_record(scene, self._latest(session, scene))

    @staticmethod
    def _check_usable(revision: Revision) -> None:
        """版本的來源缺失或有問題（例如內容和版本說明檔的雜湊不同）時，不能執行、不能發布。"""
        if revision.missing or revision.problem is not None:
            raise _conflict(
                "revision_unusable",
                t(
                    "error.revision_unusable",
                    id=revision.scene_id,
                    number=revision.number,
                    problem=revision.problem or "missing",
                ),
            )

    def list_runs(
        self,
        *,
        scenes: Sequence[str] = (),
        categories: Sequence[str] = (),
        statuses: Sequence[str] = (),
        purposes: Sequence[str] = (),
        workers: Sequence[str] = (),
        revision: int | None = None,
        limit: int = RUN_LIST_LIMIT,
        with_video: bool = False,
        client_id: str | None = None,
    ) -> list[RunRecord]:
        """運行清單（新的在前）；``with_video`` 時只列還有錄影的（運行回看頁，M12）；
        ``client_id`` 時只列那個 API 用戶端觸發的（M14）。"""
        statement = select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit)
        if with_video:
            statement = statement.where(
                Run.video_seconds.is_not(None), Run.video_deleted_at.is_(None)
            )
        if workers:
            # 執行位置（M9a）：已經有人領取的看 worker_id；還在排隊的看指定的 worker 或本機
            chosen = list(workers)
            waiting = Run.worker_id.is_(None)
            conditions = [
                Run.worker_id.in_(chosen),
                and_(waiting, Run.required_worker.in_(chosen)),
            ]
            if LOCAL_WORKER in chosen:
                conditions.append(and_(waiting, Run.target == "local"))
            statement = statement.where(or_(*conditions))
        if scenes:
            statement = statement.where(Run.scene_id.in_(list(scenes)))
        if categories:
            statement = statement.where(Run.category.in_(list(categories)))
        if statuses:
            statement = statement.where(Run.status.in_(list(statuses)))
        if purposes:
            statement = statement.where(Run.purpose.in_(list(purposes)))
        if revision is not None:
            statement = statement.where(Run.revision_number == revision)
        if client_id is not None:
            statement = statement.where(Run.client_id == client_id)
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

    # ------------------------------------------------------------ 錄影（M12）

    def replay(self, run_id: str) -> dict[str, object]:
        """回看頁的資料：錄影、換算成影片時間的步驟、斷言、階段、前後的運行（見 replay.py）。"""
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise _not_found("run_not_found", t("error.run_not_found", id=run_id))
            return {
                "run": run_record(run).to_json(),
                **build_replay(session, self.storage, run, self.videos.settings()),
            }

    def composite_report(self, run_id: str) -> dict[str, object]:
        """一次組合運行的匯總報告（見 composite_report.py）：組合運行頁、離線報告與 API 共用。"""
        record, workflow = self.workflows.get_run_with_definition(run_id)
        return build_composite_report(record, workflow, self.storage)

    def video_settings(self) -> dict[str, object]:
        """錄影設定，加上目前保存的錄影有幾段、多大。"""
        return {**self.videos.settings().to_json(), "usage": self.videos.usage()}

    def save_video_settings(self, settings: VideoSettings) -> dict[str, object]:
        """改錄影設定；之後新的任務照新設定，保留規則立刻套用（可能刪掉一些錄影）。"""
        self.videos.save_settings(settings)
        return self.video_settings()

    def pin_video(self, run_id: str, pinned: bool) -> RunRecord:
        """釘選的錄影不依保留規則刪除。"""
        run = self.videos.set_pinned(run_id, pinned)
        if run is None:
            raise _not_found("run_not_found", t("error.run_not_found", id=run_id))
        return run_record(run)

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
                # 本機的執行馬上通知 worker；遠端 worker 在下一次心跳得知（M9a）
                notify = run.worker_id in (None, LOCAL_WORKER)
            session.commit()
            record = run_record(run)
        if notify:
            self.on_cancel(run_id)
        if settled:
            self.run_finished(run_id)
        return record

    def run_finished(self, run_id: str) -> None:
        """一次執行結束了（worker 執行完、排隊中被取消）：寫執行目錄的 run.json，驗證執行另外寫
        領域資料夾的驗證紀錄（M11）；屬於試驗場序列時，接著排下一個節點。
        """
        self.packs.record_run(run_id)
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

    def busy(self) -> list[str]:
        """進行中、伺服器重新啟動會打斷的工作（ADR 0018）：錄製、逐步調試、人工登入。

        回傳要顯示的說明；空的代表可以重新啟動。遠端 worker 執行中的任務不算：重新啟動後
        :meth:`recover` 給它一次租約的時間重新報到。
        """
        reasons: list[str] = []
        if recordings := self.recordings.active:
            reasons.append(t("server.busy_recordings", count=len(recordings)))
        if sessions := self.debug.sessions():
            reasons.append(t("server.busy_debug", count=len(sessions)))
        if logins := self.roles.active_logins:
            reasons.append(t("server.busy_logins", count=len(logins)))
        return reasons

    def recover(self) -> int:
        """伺服器啟動時：上次執行到一半的任務標為失敗（排隊中的會繼續執行）。

        錄製到一半的也標為失敗（刪除可能含密碼的暫存原始稿），清掉上次調試留下的目錄。
        """
        self.recordings.recover()
        self.debug.remove_leftovers()
        # 遠端 worker 執行中的任務不受管理 Portal 重新啟動影響：給它一次租約的時間重新報到（M9a）
        self.workers.resume_after_restart()
        with self.sessions() as session:
            runs = list(
                session.scalars(
                    select(Run).where(
                        Run.status == "running",
                        or_(Run.worker_id.is_(None), Run.worker_id == LOCAL_WORKER),
                    )
                )
            )
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

    def contract_yaml_files(
        self,
        scene_id: str,
        *,
        base: int,
        inputs: str,
        outputs: str,
        renames: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """左右契約一起校驗、一起存檔；不因先存一欄而遺失另一欄的草稿。"""
        files = dict(self.revision_files(scene_id, base))
        for key, text in (("inputs", inputs), ("outputs", outputs)):
            section = text.replace("\r\n", "\n").strip("\n")
            _check_section(key, section)
            files[SCENARIO_FILE] = replace_section(files[SCENARIO_FILE], key, section)
        if renames:
            files[SCENARIO_FILE] = replace_contract(
                files[SCENARIO_FILE], inputs=None, outputs=None, renames=renames
            )
        checked = self.storage.check(files, scene_id=scene_id)
        if not checked.ok:
            issues = [issue_json(issue) for issue in checked.issues]
            for key in ("inputs", "outputs"):
                found = find_block(files[SCENARIO_FILE].splitlines(), key)
                for issue in issues:
                    line = issue.get("line")
                    if found and isinstance(line, int) and found[0] < line <= found[1]:
                        issue["section"] = key
                        issue["sectionLine"] = line - found[0]
            raise _invalid(
                "revision_invalid", t("error.revision_invalid", count=len(issues)), issues=issues
            )
        return files

    def _section_files(
        self,
        scene_id: str,
        key: str,
        base: int,
        text: str,
        files: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """換掉一段之後的版本檔案；``files`` 給了時在它上面換（一次換幾段），否則用 base 版本的。"""
        if key not in SECTION_KEYS:
            raise _not_found("section_unknown", t("error.section_unknown", key=key))
        files = dict(files if files is not None else self.revision_files(scene_id, base))
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

    def save_sections(
        self,
        scene_id: str,
        sections: Mapping[str, str],
        *,
        base: int,
        note: str | None = None,
    ) -> RevisionRecord:
        """一次換掉幾段（場景詳情頁的自動化腳本、斷言腳本一起存）：存成一個新版本。

        兩段一起校驗，步驟改了 extract 的名稱、斷言跟著改時不會卡在中間的版本。校驗問題落在哪一段，
        就附上那一段（``section``）與段落裡的行號（``sectionLine``）。
        """
        if not sections:
            raise _invalid("section_none", t("error.section_none"))
        files = dict(self.revision_files(scene_id, base))
        for key, text in sections.items():
            files[SCENARIO_FILE] = self._section_files(scene_id, key, base, text, files)[
                SCENARIO_FILE
            ]
        names = t("revision.section_separator").join(t(f"section.{key}") for key in sections)
        try:
            return self.save_revision(
                scene_id,
                base=base,
                files=files,
                note=note or t("revision.note_section", section=names),
            )
        except ServiceError as error:
            issues = error.details.get("issues")
            if isinstance(issues, list):
                found = cast("list[dict[str, object]]", issues)
                for key in sections:
                    before = {id(issue) for issue in found if "sectionLine" in issue}
                    _section_lines(found, files[SCENARIO_FILE], key)
                    for issue in found:
                        if id(issue) not in before and "sectionLine" in issue:
                            issue["section"] = key
            raise

    def rerun(
        self, run_id: str, *, idempotency_key: str | None = None, client_id: str | None = None
    ) -> RunRecord:
        """用同樣的入參與選項再執行一次（例如登入之後）。驗證用同一個版本，正式執行用目前發布的版本；
        試驗場序列的節點只重新執行這一個節點（同一個版本），不接著執行序列，序列請從序列執行頁繼續。
        ``client_id`` 是要求重跑的 API 用戶端（M14）。
        """
        run = self.get_run(run_id)
        target = run.target if run.target != "remote" or self.workers.has_remote() else "local"
        # 序列的節點跟著原本那台 worker（測試網站的資料、登入狀態一致）
        pinned = run.worker_id if run.purpose == "workflow" and target != "local" else None
        return self.request_run(
            run.scene_id,
            purpose=run.purpose,
            number=run.revision_number if run.purpose != "execution" else None,
            inputs=run.input,
            engine=cast("Engine | None", run.engine),
            base_url=run.base_url,
            idempotency_key=idempotency_key,
            headless=run.headless if run.headless or self.can_display(target) else True,
            target=target,
            required_worker=pinned,
            client_id=client_id,
        )
