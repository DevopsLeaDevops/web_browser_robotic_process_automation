"""領域資料夾（M11）：伺服器代號、資料夾的寫入、載入成資料庫的索引、驗證紀錄、run.json、舊資料遷移。

資料夾的格式與校驗在 :mod:`rpa_core.pack`；這裡負責管理 Portal 這一側：

- **伺服器代號**：第一次啟動時產生（UUID），名稱預設是主機名稱，可以改。驗證、發布、版本的紀錄
  都寫上它；M8 有登入之前，操作者名稱也是伺服器的名稱。
- **寫入**：存檔、發布、封存、搬領域、角色的增刪改都先寫資料夾，再更新資料庫的索引。
- **載入**：伺服器啟動時載入全部領域，「重新載入」時載入一個領域。逐項校驗後在一個交易裡更新索引；
  單一項目有問題只略過那一項，問題記在領域的 problems；pack.yaml 不見或代號不同時，整個領域
  保持上一次的索引。代號全域唯一（D8）：另一個領域已經有同一個代號時，後來的那個不載入。
- **驗證紀錄**：驗證執行結束時寫 ``verifications/<n>/<執行編號>.yaml``（通過、失敗都寫）。
- **run.json**：每個執行目錄自己說明自己（伺服器、領域、場景、版本、雜湊、時間、檔案與 sha256），
  不看資料庫也知道是什麼執行（D4 回看的預留）。
- **遷移**（D7）：M11 之前的 ``scenes/`` 與資料庫，第一次啟動時搬進領域資料夾，先備份。

寫入與載入都持有 :attr:`PackStore.lock`，同一時間只有一個。設計見
handoff/tasks/20261019-data-storage.html 第 4～6、8、9、12 節。
"""

import hashlib
import json
import logging
import platform
import shutil
import socket
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import validate_file
from rpa_core.pack import (
    PACK_FILE,
    REVISIONS_DIR,
    ROLES_DIR,
    SCENE_FILE,
    SCENES_DIR,
    SPEC_VERSION,
    VERIFICATIONS_DIR,
    PackIssue,
    PackManifest,
    PackRequirement,
    PublishedRef,
    RevisionInfo,
    RoleDefinition,
    RoleEntry,
    RunRef,
    SceneEntry,
    SceneManifest,
    ServerRef,
    Verification,
    VerificationStatus,
    VerificationSummary,
    WorkerRef,
    parse_timestamp,
    read_model,
    read_pack,
    read_scene,
    timestamp,
    write_model,
)
from rpa_server.domain import FINISHED, LOCAL_WORKER, now
from rpa_server.i18n import t
from rpa_server.models import Domain, RemoteWorker, Revision, Role, Run, Scene, Setting
from rpa_server.storage import SCENARIO_FILE, Storage

__all__ = [
    "LAYOUT_VERSION",
    "RUN_MANIFEST",
    "UNASSIGNED_DOMAIN",
    "LoadReport",
    "PackStore",
]

logger = logging.getLogger("rpa_server")

UNASSIGNED_DOMAIN: Final = "unassigned"
"""「未分類」領域：遷移時沒有領域的場景、沒有場景用到的角色放這裡（D7）。"""
RUN_MANIFEST: Final = "run.json"
"""執行目錄的說明檔。"""
RUN_MANIFEST_VERSION: Final = 1
LAYOUT_VERSION: Final = 2
"""資料目錄的格式：1 是 M11 之前（scenes/），2 是領域資料夾（domains/）。"""
_SERVER_SETTING: Final = "server"
_LAYOUT_SETTING: Final = "storage_layout"
_ROLE_FILE_SUFFIX: Final = ".yaml"


@dataclass(frozen=True, slots=True)
class LoadReport:
    """載入一個領域資料夾的結果。"""

    domain_id: str
    applied: bool
    """有沒有更新索引；pack.yaml 不見或不能讀時是 False（保持上一次的索引）。"""
    issues: list[PackIssue] = field(default_factory=list[PackIssue])
    scenes: int = 0
    roles: int = 0

    def to_json(self) -> dict[str, object]:
        return {
            "domainId": self.domain_id,
            "applied": self.applied,
            "scenes": self.scenes,
            "roles": self.roles,
            "issues": [issue.to_json() for issue in self.issues],
        }


def _hostname() -> str:
    name = socket.gethostname().split(".")[0].strip()
    return name[:100] or "rpa-server"


def _issue(path: str, code: str, **params: object) -> PackIssue:
    return PackIssue(path, f"server.{code}", t(f"packs.{code}", **params))


def _moment(value: str | None, default: datetime) -> datetime:
    if value is None:
        return default
    try:
        return parse_timestamp(value)
    except ValueError:
        return default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def _remove_tree(folder: Path) -> None:
    """刪除資料夾（版本檔案是唯讀的，Windows 上要先改成可寫）。"""

    def retry(function: Callable[..., object], path: str, _error: BaseException) -> None:
        Path(path).chmod(0o700)
        function(path)

    if folder.exists():
        shutil.rmtree(folder, onexc=retry)


class PackStore:
    def __init__(self, sessions: sessionmaker[Session], storage: Storage) -> None:
        self.sessions = sessions
        self.storage = storage
        self.lock = threading.RLock()
        """寫入資料夾、載入資料夾時持有；同一時間只有一個。"""
        self._server: ServerRef | None = None

    # ------------------------------------------------------------ 伺服器代號

    def server(self) -> ServerRef:
        """這台伺服器的代號與名稱；第一次呼叫時產生並存進設定。"""
        if self._server is not None:
            return self._server
        with self.lock, self.sessions() as session:
            row = session.get(Setting, _SERVER_SETTING)
            value: Mapping[str, object] = row.value if row is not None else {}
            server_id = str(value.get("id") or "") or uuid.uuid4().hex
            name = str(value.get("name") or "") or _hostname()
            stored = {"id": server_id, "name": name}
            if row is None:
                session.add(Setting(key=_SERVER_SETTING, value=stored))
            elif dict(row.value) != stored:
                row.value = stored
            session.commit()
        self._server = ServerRef(id=server_id, name=name)
        return self._server

    def rename_server(self, name: str) -> ServerRef:
        """改這台伺服器的名稱（代號不變）；名稱會寫進之後的紀錄。"""
        name = name.strip()[:100]
        if not name:
            raise ValueError("name")
        current = self.server()
        with self.lock, self.sessions() as session:
            row = session.get(Setting, _SERVER_SETTING)
            stored = {"id": current.id, "name": name}
            if row is None:
                session.add(Setting(key=_SERVER_SETTING, value=stored))
            else:
                row.value = stored
            session.commit()
        self._server = ServerRef(id=current.id, name=name)
        return self._server

    def operator(self) -> str:
        """寫進紀錄的操作者：M8 有登入之前是伺服器的名稱。"""
        return self.server().name

    # ------------------------------------------------------------ 寫入資料夾

    def pack_dir(self, domain_id: str) -> Path:
        return self.storage.domain_dir(domain_id)

    def manifest(self, domain_id: str) -> PackManifest | None:
        path = self.pack_dir(domain_id) / PACK_FILE
        if not path.is_file():
            return None
        manifest, _ = read_model(path, PackManifest)
        return manifest

    def write_pack(self, domain_id: str, name: str, description: str | None) -> None:
        """寫 pack.yaml（保留原本的 requires）。"""
        existing = self.manifest(domain_id)
        manifest = PackManifest(
            spec_version=SPEC_VERSION,
            id=domain_id,
            name=name,
            description=description,
            requires=list(existing.requires) if existing is not None else [],
        )
        with self.lock:
            write_model(self.pack_dir(domain_id) / PACK_FILE, manifest)

    def add_requirement(self, domain_id: str, required: str) -> None:
        """pack.yaml 記下依賴另一個領域（例如用到它的角色）。"""
        existing = self.manifest(domain_id)
        if existing is None or any(item.domain == required for item in existing.requires):
            return
        requires = [*existing.requires, PackRequirement(domain=required)]
        with self.lock:
            write_model(
                self.pack_dir(domain_id) / PACK_FILE,
                existing.model_copy(update={"requires": requires}),
            )

    def remove_pack(self, domain_id: str) -> None:
        with self.lock:
            _remove_tree(self.pack_dir(domain_id))

    def scene_manifest(self, scene_id: str) -> SceneManifest:
        """scene.yaml；還沒有或讀不到時是預設值（沒有封存、沒有發布）。"""
        path = self.storage.scene_dir(scene_id) / SCENE_FILE
        manifest = read_model(path, SceneManifest)[0] if path.is_file() else None
        return manifest if manifest is not None else SceneManifest(id=scene_id)

    def write_scene(self, manifest: SceneManifest) -> None:
        with self.lock:
            write_model(self.storage.scene_dir(manifest.id) / SCENE_FILE, manifest)

    def write_revision_info(
        self, scene_id: str, number: int, digest: str, note: str | None, created_at: datetime
    ) -> None:
        info = RevisionInfo(
            number=number,
            hash=digest,
            created_at=timestamp(created_at),
            by=self.operator(),
            server=self.server(),
            note=note,
        )
        with self.lock:
            write_model(self._info_path(scene_id, number), info)

    def _info_path(self, scene_id: str, number: int) -> Path:
        return self.storage.scene_dir(scene_id) / REVISIONS_DIR / f"{number}.yaml"

    def discard_revision(self, scene_id: str, number: int, *, new_scene: bool) -> None:
        """存檔失敗時移除這次寫的版本（新場景連同場景資料夾）。"""
        with self.lock:
            if new_scene:
                _remove_tree(self.storage.scene_dir(scene_id))
                self.storage.forget_scene(scene_id)
                return
            self.storage.discard(scene_id, number)
            self._info_path(scene_id, number).unlink(missing_ok=True)

    def move_scene(self, scene_id: str, target: str) -> None:
        """把場景資料夾搬到另一個領域（版本、驗證紀錄、scene.yaml 一起）。"""
        with self.lock:
            source = self.storage.scene_dir(scene_id)
            destination = self.storage.domain_dir(target) / SCENES_DIR / scene_id
            if source == destination:
                return
            if destination.exists():
                raise FileExistsError(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                source.replace(destination)
            self.storage.place_scene(scene_id, target)

    def scene_entry(self, scene_id: str) -> tuple[SceneEntry | None, list[PackIssue]]:
        """讀取一個場景資料夾（版本、驗證紀錄、發布門檻）。"""
        folder = self.storage.scene_dir(scene_id)
        if not folder.is_dir():
            return None, []
        return read_scene(folder)

    # ------------------------------------------------------------ 角色

    def role_path(self, domain_id: str, role_id: str) -> Path:
        return self.pack_dir(domain_id) / ROLES_DIR / f"{role_id}{_ROLE_FILE_SUFFIX}"

    def write_role(self, role: Role) -> None:
        if role.domain_id is None:
            return
        definition = RoleDefinition(
            id=role.id,
            name=role.name,
            description=role.description,
            login_url=role.login_url,
            check_url=role.check_url,
            check=dict(role.check_locator),
            engine="firefox" if role.engine == "firefox" else "chromium",
            auto_login=role.auto_login,
        )
        with self.lock:
            write_model(self.role_path(role.domain_id, role.id), definition)

    def remove_role(self, domain_id: str | None, role_id: str) -> None:
        if domain_id is None:
            return
        with self.lock:
            self.role_path(domain_id, role_id).unlink(missing_ok=True)

    # ------------------------------------------------------------ 執行結束

    def record_run(self, run_id: str) -> None:
        """一次執行結束：寫 run.json；驗證執行另外寫驗證紀錄，更新版本的「有通過的驗證紀錄」。

        寫不進去只記日誌，不影響執行的結果。
        """
        try:
            self._record_run(run_id)
        except Exception:
            logger.exception("無法寫入執行 %s 的紀錄", run_id)

    def _record_run(self, run_id: str) -> None:
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None or run.status not in FINISHED:
                return
            scene = session.get(Scene, run.scene_id)
            revision = session.get(Revision, run.revision_id)
            domain_id = scene.domain_id if scene is not None else None
            self.write_run_manifest(run, domain_id, revision)
            if (
                run.purpose != "validation"
                or run.started_at is None
                or revision is None
                or domain_id is None
            ):
                return
            with self.lock:
                record = self.verification(session, run, by=self.operator())
                path = self.verification_path(run.scene_id, run.revision_number, run.id)
                write_model(path, record)
                passed = run.status == "passed" and run.scenario_hash == revision.content_hash
                if passed and revision.problem is None:
                    revision.verified = True
                    session.commit()

    def verification_path(self, scene_id: str, number: int, run_id: str) -> Path:
        folder = self.storage.scene_dir(scene_id) / VERIFICATIONS_DIR / str(number)
        return folder / f"{run_id}.yaml"

    def verification(self, session: Session, run: Run, *, by: str) -> Verification:
        """一次驗證執行的紀錄（不含入參與出參的值）。"""
        server = self.server()
        worker = run.worker_id or LOCAL_WORKER
        if worker == LOCAL_WORKER:
            system = platform.system().lower() or None
        else:
            row = session.get(RemoteWorker, worker)
            value = row.info.get("os") if row is not None else None
            system = str(value) if value else None
        scenario = validate_file(
            self.storage.revision_dir(run.scene_id, run.revision_number) / SCENARIO_FILE
        ).scenario
        engine = run.engine or (scenario.browser.engine if scenario is not None else None)
        steps = len(scenario.steps or []) if scenario is not None else None
        finished = run.finished_at or now()
        return Verification(
            revision=run.revision_number,
            hash=run.scenario_hash,
            status=_status(run.status),
            started_at=timestamp(run.started_at) if run.started_at is not None else None,
            finished_at=timestamp(finished),
            by=by,
            server=server,
            worker=WorkerRef(id=worker, os=system),
            engine=engine,
            headless=run.headless,
            run=RunRef(server=server.id, id=run.id),
            summary=VerificationSummary(steps=steps, duration_seconds=run.duration_seconds),
        )

    def write_run_manifest(
        self, run: Run, domain_id: str | None, revision: Revision | None
    ) -> None:
        """執行目錄的 run.json：不看資料庫也知道這是什麼執行（D4 回看的預留）。"""
        folder = self.storage.run_dir(run.id)
        folder.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, object]] = []
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(folder).as_posix()
            if not path.is_file() or relative == RUN_MANIFEST or path.name.startswith("."):
                continue
            files.append({"path": relative, "sha256": _sha256(path), "size": path.stat().st_size})
        server = self.server()
        data: dict[str, object] = {
            "specVersion": RUN_MANIFEST_VERSION,
            "kind": "scene",
            "id": run.id,
            "server": {"id": server.id, "name": server.name},
            "domain": domain_id,
            "scene": run.scene_id,
            "revision": run.revision_number,
            "hash": revision.content_hash if revision is not None else None,
            "scenarioHash": run.scenario_hash,
            "purpose": run.purpose,
            "status": run.status,
            "target": run.target,
            "worker": run.worker_id,
            "engine": run.engine,
            "headless": run.headless,
            "workflowRun": run.workflow_run_id,
            "node": run.node_id,
            "createdAt": timestamp(run.created_at),
            "startedAt": timestamp(run.started_at) if run.started_at else None,
            "finishedAt": timestamp(run.finished_at) if run.finished_at else None,
            "durationSeconds": run.duration_seconds,
            "files": files,
        }
        _write_json(folder / RUN_MANIFEST, data)

    # ------------------------------------------------------------ 載入

    def load_all(self) -> list[LoadReport]:
        """載入全部領域：資料庫裡的領域依排列順序，再加上資料夾裡有、資料庫還沒有的。"""
        with self.sessions() as session:
            known = list(
                session.scalars(select(Domain.id).order_by(Domain.position, Domain.created_at))
            )
        found = sorted(
            folder.name
            for folder in self.storage.domains.glob("*")
            if folder.is_dir()
            and not folder.name.startswith(".")
            and (folder / PACK_FILE).is_file()
        )
        order = known + [name for name in found if name not in known]
        return [self.load_domain(domain_id) for domain_id in order]

    def load_domain(self, domain_id: str) -> LoadReport:
        """載入一個領域資料夾，更新資料庫的索引。"""
        with self.lock:
            pack = read_pack(self.pack_dir(domain_id), expected_id=domain_id)
            with self.sessions() as session:
                domain = session.get(Domain, domain_id)
                issues = list(pack.issues)
                manifest = pack.manifest
                if manifest is None:
                    if domain is not None:
                        domain.problems = [issue.to_json() for issue in issues]
                        domain.loaded_at = now()
                        session.commit()
                    return LoadReport(domain_id, False, issues)
                if domain is None:
                    last = session.scalar(select(func.max(Domain.position)))
                    domain = Domain(
                        id=domain_id,
                        name=manifest.name[:100],
                        description=manifest.description,
                        position=(last if last is not None else -1) + 1,
                        created_at=now(),
                    )
                    session.add(domain)
                    session.flush()
                domain.name = manifest.name[:100]
                domain.description = manifest.description
                scenes = self._apply_scenes(session, domain_id, pack.scenes.values(), issues)
                roles = self._apply_roles(session, domain_id, pack.roles.values(), issues)
                domain.problems = [issue.to_json() for issue in issues]
                domain.loaded_at = now()
                session.commit()
            return LoadReport(domain_id, True, issues, scenes, roles)

    def _apply_scenes(
        self,
        session: Session,
        domain_id: str,
        entries: Iterable[SceneEntry],
        issues: list[PackIssue],
    ) -> int:
        indexed = {
            scene.id: scene
            for scene in session.scalars(select(Scene).where(Scene.domain_id == domain_id))
        }
        seen: set[str] = set()
        for entry in entries:
            scene = session.get(Scene, entry.id)
            if scene is not None and scene.domain_id not in (domain_id, None) and not scene.missing:
                where = f"{SCENES_DIR}/{entry.id}"
                issues.append(_issue(where, "duplicate_scene", id=entry.id, domain=scene.domain_id))
                continue
            seen.add(entry.id)
            self._apply_scene(session, domain_id, scene, entry)
        for scene_id, scene in indexed.items():
            if scene_id not in seen and not scene.missing:
                scene.missing = True
                self.storage.forget_scene(scene_id, domain_id)
        return len(seen)

    def _apply_scene(
        self, session: Session, domain_id: str, scene: Scene | None, entry: SceneEntry
    ) -> None:
        moment = now()
        latest = entry.latest_usable()
        scenario = latest.scenario if latest is not None else None
        name = (scenario.name if scenario is not None else None) or entry.id
        category = scenario.category if scenario is not None else None
        description = scenario.description if scenario is not None else None
        if scene is None:
            created = [
                _moment(revision.info.created_at, moment)
                for revision in entry.revisions.values()
                if revision.info is not None
            ]
            scene = Scene(
                id=entry.id,
                name=name[:200],
                category=category,
                description=description,
                domain_id=domain_id,
                latest_number=entry.latest,
                published_number=entry.published,
                archived=entry.manifest.archived,
                created_at=min(created, default=moment),
                updated_at=moment,
                missing=False,
            )
            session.add(scene)
            session.flush()
        else:
            values: dict[str, object] = {
                "name": name[:200],
                "category": category,
                "description": description,
                "domain_id": domain_id,
                "latest_number": entry.latest,
                "published_number": entry.published,
                "archived": entry.manifest.archived,
                "missing": False,
            }
            changed = False
            for key, value in values.items():
                if getattr(scene, key) != value:
                    setattr(scene, key, value)
                    changed = True
            if changed:
                scene.updated_at = moment
        self._apply_revisions(session, entry, moment)
        self.storage.place_scene(entry.id, domain_id)

    @staticmethod
    def _apply_revisions(session: Session, entry: SceneEntry, moment: datetime) -> None:
        rows = {
            row.number: row
            for row in session.scalars(select(Revision).where(Revision.scene_id == entry.id))
        }
        validating = set(
            session.scalars(
                select(Revision.number)
                .join(Run, Run.revision_id == Revision.id)
                .where(
                    Revision.scene_id == entry.id,
                    Run.purpose == "validation",
                    Run.status.in_(["queued", "running"]),
                )
            )
        )
        published = entry.manifest.published
        for number, revision in entry.revisions.items():
            info = revision.info
            note = info.note if info is not None else None
            values: dict[str, object] = {
                "content_hash": info.hash if info is not None else (revision.digest or ""),
                "kind": revision.kind,
                "status": "validating" if number in validating else revision.status,
                "note": note[:500] if note else None,
                "missing": False,
                "problem": revision.problem,
                "verified": bool(revision.proofs()),
            }
            row = rows.get(number)
            if row is None:
                created = _moment(info.created_at if info is not None else None, moment)
                row = Revision(scene_id=entry.id, number=number, created_at=created, **values)
                session.add(row)
            else:
                for key, value in values.items():
                    if getattr(row, key) != value:
                        setattr(row, key, value)
            if published is not None and number == entry.published:
                row.published_at = _moment(published.at, moment)
        for number, row in rows.items():
            if number not in entry.revisions:
                row.missing = True
                row.verified = False

    def _apply_roles(
        self,
        session: Session,
        domain_id: str,
        entries: Iterable[RoleEntry],
        issues: list[PackIssue],
    ) -> int:
        indexed = {
            role.id: role
            for role in session.scalars(select(Role).where(Role.domain_id == domain_id))
        }
        seen: set[str] = set()
        moment = now()
        for entry in entries:
            role = session.get(Role, entry.id)
            if role is not None and role.domain_id not in (domain_id, None) and not role.missing:
                where = f"{ROLES_DIR}/{entry.path.name}"
                issues.append(_issue(where, "duplicate_role", id=entry.id, domain=role.domain_id))
                continue
            seen.add(entry.id)
            definition = entry.definition
            values: dict[str, object] = {
                "name": definition.name[:100],
                "description": definition.description,
                "login_url": definition.login_url,
                "check_url": definition.check_url,
                "check_locator": dict(definition.check),
                "engine": definition.engine,
                "auto_login": definition.auto_login,
                "domain_id": domain_id,
                "missing": False,
            }
            if role is None:
                session.add(
                    Role(id=entry.id, status="none", created_at=moment, updated_at=moment, **values)
                )
                continue
            changed = False
            for key, value in values.items():
                if getattr(role, key) != value:
                    setattr(role, key, value)
                    changed = True
            if changed:
                role.updated_at = moment
        for role_id, role in indexed.items():
            if role_id not in seen:
                role.missing = True
        return len(seen)

    # ------------------------------------------------------------ 遷移（D7）

    def migrate_legacy(self, *, unassigned_name: str, unassigned_description: str) -> bool:
        """M11 之前的資料目錄 → 領域資料夾；已經遷移過或是新的資料目錄時什麼都不做。

        先把 rpa.db 與 scenes/ 備份到 backups/<時間>-before-domains/。每一步都可以重跑：
        中斷後下次啟動接著做，最後才記下「已經遷移」。回傳這次有沒有遷移。
        """
        with self.lock:
            with self.sessions() as session:
                layout = session.get(Setting, _LAYOUT_SETTING)
                state: dict[str, object] = dict(layout.value) if layout is not None else {}
                if state.get("version") == LAYOUT_VERSION:
                    return False
                has_data = bool(
                    session.scalar(select(func.count()).select_from(Scene))
                    or session.scalar(select(func.count()).select_from(Role))
                )
            if has_data or self.storage.legacy_scenes.exists():
                if not state.get("backup"):
                    state["backup"] = self._backup()
                    self._save_layout(state)
                self._migrate(unassigned_name, unassigned_description)
            state["version"] = LAYOUT_VERSION
            self._save_layout(state)
            return has_data

    def _save_layout(self, state: Mapping[str, object]) -> None:
        with self.sessions() as session:
            row = session.get(Setting, _LAYOUT_SETTING)
            if row is None:
                session.add(Setting(key=_LAYOUT_SETTING, value=dict(state)))
            else:
                row.value = dict(state)
            session.commit()

    def _backup(self) -> str:
        """備份資料庫（SQLite 才有檔案）與舊的版本目錄，回傳備份資料夾的名稱。"""
        name = f"{now().astimezone():%Y%m%d-%H%M%S}-before-domains"
        target = self.storage.backups / name
        target.mkdir(parents=True, exist_ok=True)
        with self.sessions() as session:
            url = session.get_bind().engine.url
        if url.drivername.startswith("sqlite") and url.database:
            source = sqlite3.connect(url.database)
            destination = sqlite3.connect(target / "rpa.db")
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
        if self.storage.legacy_scenes.is_dir():
            shutil.copytree(self.storage.legacy_scenes, target / "scenes")
        logger.warning("%s", t("packs.backup", path=target))
        return name

    def _migrate(self, unassigned_name: str, unassigned_description: str) -> None:
        by = t("packs.migrated_by")
        server = self.server()
        with self.sessions() as session:
            domains = list(session.scalars(select(Domain).order_by(Domain.position)))
            scenes = list(session.scalars(select(Scene).order_by(Scene.id)))
            roles = list(session.scalars(select(Role).order_by(Role.id)))
            role_domains = self._role_domains(scenes, [domain.id for domain in domains])
            needs_unassigned = any(scene.domain_id is None for scene in scenes) or any(
                role.id not in role_domains for role in roles
            )
            if needs_unassigned and session.get(Domain, UNASSIGNED_DOMAIN) is None:
                last = session.scalar(select(func.max(Domain.position)))
                unassigned = Domain(
                    id=UNASSIGNED_DOMAIN,
                    name=unassigned_name,
                    description=unassigned_description,
                    position=(last if last is not None else -1) + 1,
                    created_at=now(),
                )
                session.add(unassigned)
                session.flush()
                domains.append(unassigned)
            for domain in domains:
                if not (self.pack_dir(domain.id) / PACK_FILE).is_file():
                    self.write_pack(domain.id, domain.name, domain.description)
            for scene in scenes:
                scene.domain_id = scene.domain_id or UNASSIGNED_DOMAIN
                self._migrate_scene(session, scene, by, server)
            for role in roles:
                owner, others = role_domains.get(role.id, (UNASSIGNED_DOMAIN, []))
                role.domain_id = owner
                self.write_role(role)
                for other in others:
                    self.add_requirement(other, owner)
            session.commit()
            for run in session.scalars(select(Run).where(Run.status.in_(list(FINISHED)))):
                if (
                    self.storage.run_dir(run.id).is_dir()
                    and not (self.storage.run_dir(run.id) / RUN_MANIFEST).exists()
                ):
                    scene = session.get(Scene, run.scene_id)
                    revision = session.get(Revision, run.revision_id)
                    domain_id = scene.domain_id if scene is not None else None
                    self.write_run_manifest(run, domain_id, revision)
        _remove_tree(self.storage.legacy_scenes)

    def _role_domains(
        self, scenes: Iterable[Scene], order: list[str]
    ) -> dict[str, tuple[str, list[str]]]:
        """角色 → (放在哪個領域, 其他也用到它的領域)：用到它的場景所在、排序最前的領域。"""
        users: dict[str, set[str]] = {}
        for scene in scenes:
            if scene.domain_id is None:
                continue
            path = self.storage.legacy_scenes / scene.id / str(scene.latest_number) / SCENARIO_FILE
            if not path.is_file():
                path = (
                    self.storage.domain_dir(scene.domain_id)
                    / SCENES_DIR
                    / scene.id
                    / REVISIONS_DIR
                    / str(scene.latest_number)
                    / SCENARIO_FILE
                )
            scenario = validate_file(path).scenario
            if scenario is not None and scenario.login is not None:
                users.setdefault(scenario.login.role, set()).add(scene.domain_id)
        ranked = {domain_id: index for index, domain_id in enumerate(order)}
        placed: dict[str, tuple[str, list[str]]] = {}
        for role_id, domains in users.items():
            ordered = sorted(domains, key=lambda item: (ranked.get(item, len(order)), item))
            placed[role_id] = (ordered[0], ordered[1:])
        return placed

    def _migrate_scene(self, session: Session, scene: Scene, by: str, server: ServerRef) -> None:
        domain_id = scene.domain_id or UNASSIGNED_DOMAIN
        self.storage.place_scene(scene.id, domain_id)
        folder = self.storage.scene_dir(scene.id)
        revisions = list(
            session.scalars(
                select(Revision).where(Revision.scene_id == scene.id).order_by(Revision.number)
            )
        )
        for revision in revisions:
            source = self.storage.legacy_scenes / scene.id / str(revision.number)
            target = folder / REVISIONS_DIR / str(revision.number)
            if source.is_dir() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(source, target)
            info = target.with_name(f"{revision.number}.yaml")
            if not info.exists():
                write_model(
                    info,
                    RevisionInfo(
                        number=revision.number,
                        hash=revision.content_hash,
                        created_at=timestamp(revision.created_at),
                        by=by,
                        server=server,
                        note=revision.note,
                    ),
                )
            runs = session.scalars(
                select(Run).where(
                    Run.revision_id == revision.id,
                    Run.purpose == "validation",
                    Run.status.in_(list(FINISHED)),
                    Run.started_at.is_not(None),
                )
            )
            for run in runs:
                path = self.verification_path(scene.id, revision.number, run.id)
                if not path.exists():
                    write_model(path, self.verification(session, run, by=by))
        published = None
        if scene.published_number is not None:
            revision = next(
                (item for item in revisions if item.number == scene.published_number), None
            )
            proof = self._latest_proof(session, revision) if revision is not None else None
            moment = (revision.published_at if revision is not None else None) or scene.updated_at
            published = PublishedRef(
                revision=scene.published_number,
                verification=proof,
                at=timestamp(moment),
                by=by,
                server=server,
            )
        manifest = SceneManifest(id=scene.id, archived=scene.archived, published=published)
        if not (folder / SCENE_FILE).exists():
            write_model(folder / SCENE_FILE, manifest)

    @staticmethod
    def _latest_proof(session: Session, revision: Revision) -> str | None:
        """最近一次雜湊相符的通過驗證執行（發布的依據）。"""
        return session.scalar(
            select(Run.id)
            .where(
                Run.revision_id == revision.id,
                Run.purpose == "validation",
                Run.status == "passed",
                Run.scenario_hash == revision.content_hash,
            )
            .order_by(Run.finished_at.desc(), Run.id.desc())
            .limit(1)
        )


def _status(value: str) -> VerificationStatus:
    """執行的狀態 → 驗證紀錄的結果（執行結束後只會是這幾種）。"""
    if value in ("passed", "failed", "timed_out", "cancelled", "needs_login"):
        return cast("VerificationStatus", value)
    return "failed"
