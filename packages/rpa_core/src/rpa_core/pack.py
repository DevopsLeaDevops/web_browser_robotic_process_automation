"""領域資料夾（資料包）的格式：說明檔的模型、讀取與校驗、寫入（M11）。

一個領域一個資料夾，裡面是這個領域的全部定義；資料夾自己就能載入，也是 git 推送與拉取的單位::

    <領域資料夾>/
      pack.yaml                                    領域說明檔（必須有）
      scenes/<場景>/scene.yaml                      場景說明檔：封存、目前發布的版本
      scenes/<場景>/revisions/<n>/                  版本內容：scenario.yaml（腳本場景另有兩支腳本）
      scenes/<場景>/revisions/<n>.yaml              版本說明：雜湊、建立時間、建立者、伺服器、說明
      scenes/<場景>/verifications/<n>/<執行編號>.yaml 驗證紀錄：一次驗證一份，只新增不修改
      roles/<角色>.yaml                             登入角色的定義（不含登入狀態）

- 版本不可變：版本說明檔放在版本目錄旁邊，所以版本內容與雜湊和管理 Portal 以前的版本目錄完全一樣。
- 發布門檻（任何一台伺服器都一樣）：磁碟上的版本內容雜湊 ＝ 版本說明檔的雜湊 ＝ 某一份
  ``status: passed`` 驗證紀錄的雜湊。不成立時這個版本不算已發布。
- 資料夾裡沒有登入狀態、Secrets 的值、執行的入參與出參、截圖與錄製稿。

讀取時單一項目有問題只略過那一項，問題列在 :attr:`Pack.issues`；``pack.yaml`` 不見或不能讀時
整個資料夾不能用（:attr:`Pack.manifest` 是 None）。此模組不依賴資料庫或瀏覽器，管理 Portal 載入
資料夾與 ``rpa pack check`` 都用它。設計見 handoff/tasks/20261019-data-storage.html 第 4、8 節。
"""

import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from rpa_core.dsl.fields import DslModel, NonEmptyStr, Slug, catalog, dsl_error
from rpa_core.dsl.issues import (
    Issue,
    format_issue,
    issue_from_yaml_error,
    issues_from_validation_error,
)
from rpa_core.dsl.scenario import Scenario
from rpa_core.dsl.sources import scenario_digest, scenario_sources
from rpa_core.dsl.validation import validate_data, validate_file
from rpa_core.dsl.yaml_loader import YamlLoadError, load_yaml
from rpa_core.dsl.yaml_writer import block, key

__all__ = [
    "PACK_FILE",
    "REVISIONS_DIR",
    "ROLES_DIR",
    "SCENARIO_FILE",
    "SCENES_DIR",
    "SCENE_FILE",
    "SPEC_VERSION",
    "VERIFICATIONS_DIR",
    "Pack",
    "PackIssue",
    "PackManifest",
    "PackRequirement",
    "PackSource",
    "PublishedRef",
    "RevisionEntry",
    "RevisionInfo",
    "RoleDefinition",
    "RoleEntry",
    "RunRef",
    "SceneEntry",
    "SceneManifest",
    "ServerRef",
    "Verification",
    "VerificationEntry",
    "VerificationStatus",
    "VerificationSummary",
    "WorkerRef",
    "dump_model",
    "is_sensitive",
    "parse_timestamp",
    "read_pack",
    "role_problems",
    "timestamp",
    "write_model",
]

SPEC_VERSION: Final = 1
"""資料夾格式的版本（pack.yaml 的 specVersion）。"""

PACK_FILE: Final = "pack.yaml"
SCENE_FILE: Final = "scene.yaml"
SCENARIO_FILE: Final = "scenario.yaml"
SCENES_DIR: Final = "scenes"
ROLES_DIR: Final = "roles"
REVISIONS_DIR: Final = "revisions"
VERIFICATIONS_DIR: Final = "verifications"

_NAME: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
"""場景、角色、領域代號的規則（與 DSL 的 id 相同）。"""
_NUMBER: Final = re.compile(r"[1-9][0-9]{0,8}")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
_URL: Final = re.compile(r"https?://[^\s/]+\S*")
_SECRET_REFERENCE: Final = re.compile(
    r"secrets\s*(?:\.\s*([A-Z][A-Z0-9_]*)|\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\])"
)
_SENSITIVE: Final = re.compile(
    r"(?:state\.json|secrets[^/]*\.json|\.env(?:\..*)?|.*\.(?:pem|key|p12|pfx)"
    r"|id_(?:rsa|dsa|ecdsa|ed25519))",
    re.IGNORECASE,
)
"""看起來是登入狀態、Secrets 或私鑰的檔名：不能出現在領域資料夾裡。"""


# ---------------------------------------------------------------- 欄位型別


def parse_timestamp(value: str) -> datetime:
    """紀錄裡的時間（ISO 8601、帶 UTC 偏移）→ datetime；格式不對時拋出 ValueError。"""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(value)
    return moment


def timestamp(moment: datetime) -> str:
    """寫進紀錄的時間：伺服器當地時間、到秒、帶 UTC 偏移，例如 2026-10-19T06:40:00-07:00。"""
    return moment.astimezone().isoformat(timespec="seconds")


def _check_timestamp(value: str) -> str:
    try:
        parse_timestamp(value)
    except ValueError:
        raise dsl_error("format.timestamp", value=value) from None
    return value


def _check_digest(value: str) -> str:
    if not _DIGEST.fullmatch(value):
        raise dsl_error("format.digest", value=value)
    return value


Timestamp = Annotated[str, AfterValidator(_check_timestamp)]
"""帶 UTC 偏移的時間（字串照原樣保留，寫回時不會改變）。"""
Digest = Annotated[str, AfterValidator(_check_digest)]
"""場景內容的 sha256（64 個小寫十六進位字元）。"""
RevisionNumber = Annotated[int, Field(ge=1)]
VerificationStatus = Literal["passed", "failed", "timed_out", "cancelled", "needs_login"]
"""驗證執行的結果，和執行的狀態相同。"""


# ---------------------------------------------------------------- 說明檔的模型


class _PackModel(DslModel):
    """說明檔的模型：和 DSL 一樣嚴格。程式裡可以用欄位名稱建立；讀檔時只認 camelCase。"""

    model_config = ConfigDict(validate_by_name=True)


class ServerRef(_PackModel):
    """哪一台伺服器（管理 Portal）：第一次啟動時產生的代號與可以改的名稱。"""

    id: NonEmptyStr
    name: NonEmptyStr


class PackSource(_PackModel):
    """依賴的領域從哪裡取得：用來預填「新增領域」，不含帳號密碼。"""

    repo: NonEmptyStr
    directory: str | None = None
    branch: str | None = None


class PackRequirement(_PackModel):
    domain: Slug
    source: PackSource | None = None


class PackManifest(_PackModel):
    """pack.yaml：領域說明檔。"""

    spec_version: Literal[1]
    id: Slug
    name: NonEmptyStr
    description: str | None = None
    requires: list[PackRequirement] = Field(default_factory=list[PackRequirement])


class PublishedRef(_PackModel):
    """scene.yaml 的 published：目前發布的版本，以及依據哪一份驗證紀錄。"""

    revision: RevisionNumber
    verification: str | None = None
    """依據的驗證紀錄（執行編號）；從舊版資料遷移而找不到依據時是 None。"""
    at: Timestamp
    by: NonEmptyStr
    server: ServerRef


class SceneManifest(_PackModel):
    """scenes/<場景>/scene.yaml：場景說明檔。"""

    id: Slug
    archived: bool = False
    published: PublishedRef | None = None


class RevisionInfo(_PackModel):
    """scenes/<場景>/revisions/<n>.yaml：版本說明檔。"""

    number: RevisionNumber
    hash: Digest
    created_at: Timestamp
    by: NonEmptyStr
    server: ServerRef
    note: str | None = None


class WorkerRef(_PackModel):
    """在哪台 worker 執行；管理 Portal 這台是 ``local``。"""

    id: NonEmptyStr
    os: str | None = None


class RunRef(_PackModel):
    """執行紀錄在哪裡：伺服器代號＋執行編號（之後歸檔、回看用）。"""

    server: NonEmptyStr
    id: NonEmptyStr


class VerificationSummary(_PackModel):
    """不含入參與出參的值，只有摘要。"""

    steps: int | None = None
    duration_seconds: float | None = None


class Verification(_PackModel):
    """scenes/<場景>/verifications/<n>/<執行編號>.yaml：一次驗證執行的紀錄。"""

    revision: RevisionNumber
    hash: Digest | None
    """執行時實際載入的場景雜湊（result.json 的 scenarioHash）；沒有載入場景就失敗時是 None。"""
    status: VerificationStatus
    started_at: Timestamp | None = None
    finished_at: Timestamp
    by: NonEmptyStr
    server: ServerRef
    worker: WorkerRef
    engine: str | None = None
    headless: bool | None = None
    run: RunRef
    summary: VerificationSummary | None = None


class RoleDefinition(_PackModel):
    """roles/<角色>.yaml：登入角色怎麼登入、怎麼判斷已登入（欄位和範例的 roles.json 相同）。"""

    id: Slug
    name: NonEmptyStr
    description: str | None = None
    login_url: NonEmptyStr
    check_url: str | None = None
    check: dict[str, object]
    """已登入時看得到的元素（DSL 定位器）。"""
    engine: Literal["chromium", "firefox"] = "chromium"
    auto_login: str | None = None
    """自動登入步驟（DSL 步驟清單的 YAML）；沒有代表只能人工登入。"""


# ---------------------------------------------------------------- 讀取的結果


@dataclass(frozen=True, slots=True)
class PackIssue:
    """領域資料夾的一個問題。path 相對於資料夾（用 / 分隔），整個資料夾的問題是空字串。"""

    path: str
    code: str
    message: str
    line: int | None = None
    column: int | None = None
    severity: Literal["error", "warning"] = "error"

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class VerificationEntry:
    id: str
    """檔名（執行編號）。"""
    record: Verification

    def proves(self, digest: str) -> bool:
        """是不是一份雜湊相符的通過紀錄（發布的依據）。"""
        return self.record.status == "passed" and self.record.hash == digest


@dataclass(slots=True)
class RevisionEntry:
    number: int
    folder: Path
    info: RevisionInfo | None = None
    scenario: Scenario | None = None
    digest: str | None = None
    """從磁碟重新計算的雜湊；場景沒有通過校驗時是 None。"""
    problem: str | None = None
    """使這個版本不能執行、不能發布的問題（問題代碼）；沒有問題時是 None。"""
    verifications: list[VerificationEntry] = field(default_factory=list[VerificationEntry])

    @property
    def usable(self) -> bool:
        return self.problem is None and self.info is not None and self.scenario is not None

    @property
    def kind(self) -> Literal["dsl", "script"]:
        return "script" if self.scenario is not None and self.scenario.script else "dsl"

    def proofs(self) -> list[VerificationEntry]:
        """雜湊相符的通過驗證紀錄，最新的在前。"""
        if not self.usable or self.info is None:
            return []
        digest = self.info.hash
        return [entry for entry in self.history() if entry.proves(digest)]

    def history(self) -> list[VerificationEntry]:
        """全部驗證紀錄，最新的在前（依結束時間，相同時依執行編號）。"""
        return sorted(
            self.verifications,
            key=lambda entry: (parse_timestamp(entry.record.finished_at), entry.id),
            reverse=True,
        )

    @property
    def status(self) -> Literal["draft", "passed", "failed"]:
        """最近一次驗證的結果；雜湊和版本不符的通過紀錄算失敗。沒有紀錄是草稿。"""
        history = self.history()
        if not history:
            return "draft"
        digest = self.info.hash if self.info is not None else None
        return "passed" if digest is not None and history[0].proves(digest) else "failed"


@dataclass(slots=True)
class SceneEntry:
    id: str
    folder: Path
    manifest: SceneManifest
    revisions: dict[int, RevisionEntry] = field(default_factory=dict[int, RevisionEntry])
    published: int | None = None
    """符合發布門檻的發布版本；scene.yaml 寫了但不成立時是 None（問題列在 issues）。"""

    @property
    def latest(self) -> int:
        """最大的版本號碼（包含有問題的版本，新版本一律接在它後面）。"""
        return max(self.revisions, default=0)

    def latest_usable(self) -> RevisionEntry | None:
        usable = [entry for entry in self.revisions.values() if entry.usable]
        return max(usable, key=lambda entry: entry.number) if usable else None


@dataclass(frozen=True, slots=True)
class RoleEntry:
    id: str
    path: Path
    definition: RoleDefinition


@dataclass(slots=True)
class Pack:
    """讀取一個領域資料夾的結果。"""

    folder: Path
    manifest: PackManifest | None = None
    scenes: dict[str, SceneEntry] = field(default_factory=dict[str, SceneEntry])
    roles: dict[str, RoleEntry] = field(default_factory=dict[str, RoleEntry])
    issues: list[PackIssue] = field(default_factory=list[PackIssue])

    @property
    def errors(self) -> list[PackIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def ok(self) -> bool:
        """可以載入，而且沒有任何錯誤（警告不算）。"""
        return self.manifest is not None and not self.errors


# ---------------------------------------------------------------- 讀取


class _Reader:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.issues: list[PackIssue] = []

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.folder).as_posix()
        except ValueError:
            return path.as_posix()

    def add(
        self,
        path: Path | str,
        code: str,
        *,
        severity: Literal["error", "warning"] = "error",
        **params: object,
    ) -> None:
        self.record(path, code, params, severity=severity)

    def record(
        self,
        path: Path | str,
        code: str,
        params: Mapping[str, object],
        *,
        severity: Literal["error", "warning"] = "error",
    ) -> None:
        """記下一個問題；訊息是 rpa_core 訊息目錄的 ``pack.<code>``。"""
        where = path if isinstance(path, str) else self.relative(path)
        message = catalog(f"pack.{code}", **params)
        self.issues.append(PackIssue(where, f"pack.{code}", message, severity=severity))

    def add_issues(self, path: Path, issues: Sequence[Issue]) -> None:
        where = self.relative(path)
        for issue in issues:
            position = issue.position
            self.issues.append(
                PackIssue(
                    where,
                    issue.code,
                    _issue_text(issue),
                    position.line if position else None,
                    position.column if position else None,
                )
            )

    def model[M: BaseModel](self, path: Path, model: type[M]) -> M | None:
        """讀取並校驗一個說明檔；有問題時記下問題、回傳 None。"""
        try:
            raw = path.read_bytes()
        except OSError as error:
            self.add_issues(path, [_plain("file.unreadable", detail=error.strerror or error)])
            return None
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            self.add_issues(path, [_plain("file.encoding")])
            return None
        try:
            data, source = load_yaml(text)
        except YamlLoadError as error:
            self.add_issues(path, [issue_from_yaml_error(error)])
            return None
        version = _spec_version(data) if model is PackManifest else SPEC_VERSION
        if version != SPEC_VERSION:
            self.add(path, "spec_version", value=version, current=SPEC_VERSION)
            return None
        try:
            return model.model_validate(data, by_alias=True, by_name=False)
        except ValidationError as error:
            self.add_issues(path, issues_from_validation_error(error, data, source, model))
            return None


def _spec_version(data: object) -> object:
    """pack.yaml 寫的格式版本（沒寫時當成目前的版本，交給模型回報缺少欄位）。"""
    if not isinstance(data, dict):
        return SPEC_VERSION
    return cast("dict[str, object]", data).get("specVersion", SPEC_VERSION)


def _plain(code: str, **params: object) -> Issue:
    return Issue(code, catalog(f"dsl.{code}", **params), (), None)


def _issue_text(issue: Issue) -> str:
    return format_issue(issue)


def _children(folder: Path) -> Iterator[Path]:
    """資料夾裡的項目（依名稱排序，略過 . 開頭的隱藏檔，例如 .DS_Store、.git）。"""
    try:
        entries = sorted(folder.iterdir(), key=lambda path: path.name)
    except OSError:
        return
    yield from (entry for entry in entries if not entry.name.startswith("."))


def read_pack(folder: Path, *, expected_id: str | None = None) -> Pack:
    """讀取並校驗一個領域資料夾。expected_id 有指定時，pack.yaml 的 id 必須是它。"""
    reader = _Reader(folder)
    pack = Pack(folder)
    if not folder.is_dir():
        reader.add("", "no_folder", folder=folder.as_posix())
        pack.issues = reader.issues
        return pack
    manifest_path = folder / PACK_FILE
    if not manifest_path.is_file():
        reader.add(PACK_FILE, "no_manifest")
    else:
        manifest = reader.model(manifest_path, PackManifest)
        if manifest is not None and expected_id is not None and manifest.id != expected_id:
            reader.add(manifest_path, "id_mismatch", id=manifest.id, expected=expected_id)
            manifest = None
        pack.manifest = manifest
    for scene_folder in _children(folder / SCENES_DIR):
        if not scene_folder.is_dir():
            continue
        if not _NAME.fullmatch(scene_folder.name):
            reader.add(scene_folder, "bad_name", severity="warning", name=scene_folder.name)
            continue
        scene = _read_scene(reader, scene_folder)
        if scene is not None:
            pack.scenes[scene.id] = scene
    for role_path in _children(folder / ROLES_DIR):
        role = _read_role(reader, role_path)
        if role is not None:
            pack.roles[role.id] = role
    for path in _all_files(folder):
        if is_sensitive(path.name):
            reader.add(path, "sensitive_file", file=reader.relative(path))
    pack.issues = reader.issues
    return pack


def _all_files(folder: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(name for name in dirs if name != ".git")
        for name in sorted(files):
            yield Path(root) / name


def is_sensitive(name: str) -> bool:
    """檔名看起來是登入狀態、Secrets 或私鑰。"""
    return _SENSITIVE.fullmatch(name) is not None


def _read_scene(reader: _Reader, folder: Path) -> SceneEntry | None:
    manifest_path = folder / SCENE_FILE
    if not manifest_path.is_file():
        reader.add(manifest_path, "scene_no_manifest", scene=folder.name)
        return None
    manifest = reader.model(manifest_path, SceneManifest)
    if manifest is None:
        return None
    if manifest.id != folder.name:
        reader.add(manifest_path, "scene_id_mismatch", id=manifest.id, expected=folder.name)
        return None
    scene = SceneEntry(manifest.id, folder, manifest)
    revisions = folder / REVISIONS_DIR
    for entry in _children(revisions):
        if entry.is_dir():
            if not _NUMBER.fullmatch(entry.name):
                reader.add(entry, "revision_bad_name", severity="warning", name=entry.name)
                continue
            number = int(entry.name)
            scene.revisions[number] = _read_revision(reader, scene.id, number, entry)
        elif entry.suffix == ".yaml" and not (revisions / entry.stem).is_dir():
            reader.add(entry, "revision_orphan_info", severity="warning", file=entry.name)
    if not scene.revisions:
        reader.add(folder, "scene_no_revisions", scene=scene.id)
        return None
    _read_verifications(reader, scene)
    _check_published(reader, scene, manifest_path)
    return scene


def _read_revision(reader: _Reader, scene_id: str, number: int, folder: Path) -> RevisionEntry:
    revision = RevisionEntry(number, folder)
    info_path = folder.with_name(f"{number}.yaml")
    if not info_path.is_file():
        reader.add(info_path, "revision_no_info", number=number, file=info_path.name)
        revision.problem = "pack.revision_no_info"
    else:
        info = reader.model(info_path, RevisionInfo)
        if info is None:
            revision.problem = "pack.revision_info_invalid"
        elif info.number != number:
            reader.add(info_path, "revision_number_mismatch", value=info.number, number=number)
            revision.problem = "pack.revision_number_mismatch"
        else:
            revision.info = info
    scenario_path = folder / SCENARIO_FILE
    result = validate_file(scenario_path)
    if result.scenario is None:
        reader.add(
            scenario_path, "revision_invalid", number=number, count=max(1, len(result.issues))
        )
        reader.add_issues(scenario_path, result.issues)
        revision.problem = revision.problem or "pack.revision_invalid"
        return revision
    scenario = result.scenario
    if scenario.id != scene_id:
        reader.add(
            scenario_path, "revision_scene_id", number=number, id=scenario.id, scene=scene_id
        )
        revision.problem = revision.problem or "pack.revision_scene_id"
        return revision
    revision.scenario = scenario
    try:
        revision.digest = scenario_digest(scenario_path, scenario)
    except OSError:
        revision.problem = revision.problem or "pack.revision_invalid"
        return revision
    used = set(scenario_sources(scenario_path, scenario))
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if path.is_file() and relative not in used and not path.name.startswith("."):
            reader.add(
                path, "revision_extra_file", severity="warning", number=number, file=relative
            )
    if revision.info is not None and revision.info.hash != revision.digest:
        reader.add(info_path, "revision_hash_mismatch", number=number)
        revision.problem = revision.problem or "pack.revision_hash_mismatch"
    return revision


def _read_verifications(reader: _Reader, scene: SceneEntry) -> None:
    for folder in _children(scene.folder / VERIFICATIONS_DIR):
        if not folder.is_dir() or not _NUMBER.fullmatch(folder.name):
            reader.add(folder, "verification_bad_folder", severity="warning", name=folder.name)
            continue
        number = int(folder.name)
        revision = scene.revisions.get(number)
        if revision is None:
            reader.add(folder, "verification_no_revision", severity="warning", number=number)
            continue
        for path in _children(folder):
            if path.suffix != ".yaml" or not path.is_file():
                continue
            record = reader.model(path, Verification)
            if record is None:
                continue
            if record.revision != number:
                reader.add(path, "verification_revision", value=record.revision, number=number)
                continue
            revision.verifications.append(VerificationEntry(path.stem, record))


def _check_published(reader: _Reader, scene: SceneEntry, manifest_path: Path) -> None:
    published = scene.manifest.published
    if published is None:
        return
    number = published.revision
    revision = scene.revisions.get(number)
    if revision is None:
        reader.add(manifest_path, "published_no_revision", number=number)
        return
    if revision.problem == "pack.revision_hash_mismatch":
        reader.add(manifest_path, "published_changed", number=number)
        return
    if not revision.usable:
        reader.add(manifest_path, "published_unusable", number=number)
        return
    proofs = revision.proofs()
    if not proofs:
        reader.add(manifest_path, "published_unverified", number=number)
        return
    if published.verification is not None and published.verification not in {
        entry.id for entry in proofs
    }:
        reader.add(
            manifest_path,
            "published_proof_missing",
            severity="warning",
            id=published.verification,
            number=number,
        )
    scene.published = number


def _read_role(reader: _Reader, path: Path) -> RoleEntry | None:
    if path.is_dir() or path.suffix != ".yaml":
        return None
    if not _NAME.fullmatch(path.stem):
        reader.add(path, "bad_name", severity="warning", name=path.name)
        return None
    definition = reader.model(path, RoleDefinition)
    if definition is None:
        return None
    if definition.id != path.stem:
        reader.add(path, "role_id_mismatch", id=definition.id, expected=path.stem)
        return None
    problems = role_problems(definition)
    for code, params in problems:
        reader.record(path, code, params)
    if problems:
        return None
    return RoleEntry(definition.id, path, definition)


# ---------------------------------------------------------------- 角色


def role_problems(definition: RoleDefinition) -> list[tuple[str, dict[str, object]]]:
    """角色定義的內容問題：網址、判斷已登入的定位器、自動登入步驟。回傳 (問題代碼, 參數)。"""
    problems: list[tuple[str, dict[str, object]]] = []
    for name, value in (("loginUrl", definition.login_url), ("checkUrl", definition.check_url)):
        if value is not None and not _URL.fullmatch(value):
            problems.append(("role_url_invalid", {"field": name, "value": value}))
    probe: dict[str, object] = {
        "schemaVersion": 1,
        "id": "check",
        "name": "check",
        "steps": [{"id": "check", "action": "waitFor", "target": definition.check}],
    }
    checked = validate_data(probe)
    if not checked.ok:
        detail = "; ".join(_issue_text(issue) for issue in checked.issues)
        problems.append(("role_check_invalid", {"detail": detail}))
    text = definition.auto_login
    if text is not None and text.strip():
        detail = _steps_problem(text)
        if detail is not None:
            problems.append(("role_steps_invalid", {"detail": detail}))
    return problems


def _steps_problem(text: str) -> str | None:
    try:
        data, _ = load_yaml(text)
    except YamlLoadError as error:
        return _issue_text(issue_from_yaml_error(error))
    if isinstance(data, dict) and "steps" in data:
        data = cast("dict[str, object]", data)["steps"]
    if not isinstance(data, list) or not data:
        return catalog("pack.role_steps_not_list")
    names = sorted({m.group(1) or m.group(2) for m in _SECRET_REFERENCE.finditer(text)})
    probe: dict[str, object] = {
        "schemaVersion": 1,
        "id": "login",
        "name": "login",
        "secrets": names,
        "steps": cast("list[object]", data),
    }
    checked = validate_data(probe)
    if checked.ok:
        return None
    return "; ".join(_issue_text(issue) for issue in checked.issues)


# ---------------------------------------------------------------- 寫入


def _prune(value: object, keep: frozenset[str] = frozenset()) -> object:
    """去掉值是 None 的欄位（keep 列出的最上層欄位保留，寫成 null）。"""
    if isinstance(value, dict):
        items = cast("dict[str, object]", value).items()
        return {key: _prune(item) for key, item in items if item is not None or key in keep}
    if isinstance(value, list):
        return [_prune(item) for item in cast("list[object]", value)]
    return value


_KEEP_NULL: Final[Mapping[type[BaseModel], frozenset[str]]] = {
    SceneManifest: frozenset({"published"}),
    Verification: frozenset({"hash"}),
}
"""沒有值也要寫出來的欄位：scene.yaml 沒有發布時寫 published: null。"""


_FLOW_KEYS: Final[Mapping[type[BaseModel], frozenset[str]]] = {
    RoleDefinition: frozenset({"check"}),
}
"""寫成一行流式寫法的欄位，例如角色的定位器 ``check: { testId: current-user }``。"""


def _literal(name: str, text: str) -> list[str] | None:
    """多行文字（例如自動登入步驟）寫成 ``|`` 區塊；寫不成區塊時回傳 None（改用雙引號）。"""
    if "\n" not in text or "\r" in text or text.startswith((" ", "\n")):
        return None
    if text.endswith("\n\n") or any(not char.isprintable() for char in text if char != "\n"):
        return None
    indicator = "|" if text.endswith("\n") else "|-"
    lines = [f"{key(name)}: {indicator}"]
    lines += [f"  {line}" if line else "" for line in text.removesuffix("\n").split("\n")]
    return lines


def dump_model(model: BaseModel) -> str:
    """說明檔或紀錄 → YAML 文字：欄位依模型順序、camelCase、沒有值的欄位不寫。

    用 :mod:`rpa_core.dsl.yaml_writer` 產生，和場景檔一樣能被 YAML 1.2 core 規則讀回同樣的值。
    """
    data = model.model_dump(mode="json", by_alias=True)
    pruned = cast("dict[str, object]", _prune(data, _KEEP_NULL.get(type(model), frozenset())))
    flow_keys = _FLOW_KEYS.get(type(model), frozenset())
    lines: list[str] = []
    for name, value in pruned.items():
        literal = _literal(name, value) if isinstance(value, str) else None
        lines += literal if literal is not None else block({name: value}, flow_keys=flow_keys)
    return "\n".join(lines) + "\n"


def write_model(path: Path, model: BaseModel) -> None:
    """寫入說明檔或紀錄：先寫暫存檔再改名，不會留下寫到一半的檔案；換行一律是 LF。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(dump_model(model))
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
