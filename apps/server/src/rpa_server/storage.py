"""資料目錄裡的檔案：領域資料夾裡的場景版本，以及執行目錄。

::

    <資料目錄>/
      rpa.db                    SQLite（預設）
      domains/<領域>/            領域資料夾（M11；格式見 rpa_core.pack，載入見 packs.py）
        scenes/<場景 id>/revisions/<版本>/   scenario.yaml；腳本場景另有兩支腳本
      runs/<執行編號>/           rpa-runner 的執行目錄（input.json、report.html…、run.json）
      roles/<角色>/state.json    角色的登入狀態（只有本人能讀寫，不經由網頁提供）
      recordings/<錄製編號>/     遮罩過的原始錄製稿 raw.py 與轉換結果 scenario.yaml
      debug/<工作階段>/          調試工作階段的入參、場景快照與截圖（工作階段結束就刪除）
      secrets.json              Secrets 的值（只有本人能讀寫）
      backups/                  遷移前、「以遠端為準」前的備份（M11）
      git/                      git 同步（M11 PR 3，見 gitsync.py）：repos/<領域>.git 裸倉庫、
                                credentials.json（HTTPS 權杖）、keys/<領域>（SSH 部署金鑰）、
                                known_hosts

版本一旦寫入就不再修改；改內容就是新版本。版本內容的雜湊與 rpa-runner 記在 result.json 的
scenarioHash 用同一個演算法（:func:`rpa_core.dsl.sources.scenario_digest`），發布門檻靠它確認
「通過驗證的就是要發布的版本」。

場景在哪個領域資料夾由 :meth:`Storage.place_scene` 登記（載入資料夾、新增場景、搬到其他領域時），
所以只知道場景 id 的地方（佇列、遠端分派）照樣用 :meth:`Storage.revision_dir` 找到版本目錄。
M11 之前的版本目錄在 ``scenes/<場景>/<版本>/``，第一次啟動時搬進領域資料夾（packs.py）。
"""

import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from rpa_core.dsl import Issue, Scenario, validate_file
from rpa_core.dsl.sources import scenario_digest, scenario_sources
from rpa_core.pack import COMPOSITES_DIR, REVISIONS_DIR, SCENES_DIR
from rpa_server.i18n import t

__all__ = [
    "SCENARIO_FILE",
    "CheckedRevision",
    "Storage",
    "StorageConflictError",
    "new_scene_template",
]

SCENARIO_FILE: Final = "scenario.yaml"
"""版本目錄裡場景檔的名稱。"""

_FILE_PATH: Final = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}(?:/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99})*"
)
_MAX_FILES: Final = 20
_MAX_BYTES: Final = 1_000_000


class StorageConflictError(Exception):
    """要寫入的版本目錄已經存在。"""


_NOWHERE: Final = ".missing"
"""還沒登記在任何領域的場景：版本目錄指到不存在的地方（讀不到，也不會寫進去）。"""


@dataclass(frozen=True, slots=True)
class CheckedRevision:
    """存檔前的檢查結果：沒有問題時 scenario 與 digest 才有值。"""

    files: dict[str, str]
    scenario: Scenario | None = None
    digest: str | None = None
    issues: tuple[Issue, ...] = field(default_factory=tuple[Issue, ...])

    @property
    def ok(self) -> bool:
        return self.scenario is not None and not self.issues


def _issue(code: str, message: str, path: tuple[str | int, ...] = ()) -> Issue:
    return Issue(code=code, message=message, path=path, position=None)


class Storage:
    def __init__(self, root: Path) -> None:
        # 絕對路徑：交給子程序的路徑（錄製稿、登入狀態）不受子程序的工作目錄影響
        root = root.absolute()
        self.root = root
        self.domains = root / "domains"
        self.legacy_scenes = root / "scenes"
        """M11 之前的版本目錄；遷移完成後移除。"""
        self.backups = root / "backups"
        self.runs = root / "runs"
        self.roles = root / "roles"
        self.recordings = root / "recordings"
        self.debug = root / "debug"
        self.secrets = root / "secrets.json"
        self.work = root / "work"
        """本機執行中的版本檔案快照（M11 收尾）：work/<執行編號>/，結束就刪。"""
        self.workflow_runs = root / "workflow-runs"
        """組合場景的執行紀錄（M11 PR 2）：workflow-runs/<編號>/run.json。"""
        self._places: dict[str, str] = {}
        self._composites: dict[str, str] = {}
        self._places_lock = threading.Lock()

    def ensure(self) -> None:
        for folder in (self.domains, self.runs, self.roles, self.recordings, self.debug):
            folder.mkdir(parents=True, exist_ok=True)
        # 上次沒刪掉的快照（伺服器在執行中停了）：啟動時沒有執行中的任務，整個清掉
        _remove_tree(self.work)
        if os.name != "nt":
            self.roles.chmod(0o700)

    # ------------------------------------------------------------ 領域資料夾

    def domain_dir(self, domain_id: str) -> Path:
        return self.domains / domain_id

    def place_scene(self, scene_id: str, domain_id: str) -> None:
        """登記場景在哪個領域資料夾。"""
        with self._places_lock:
            self._places[scene_id] = domain_id

    def forget_scene(self, scene_id: str, domain_id: str | None = None) -> None:
        """取消登記（domain_id 有指定時，只在還登記在那個領域時取消）。"""
        with self._places_lock:
            if domain_id is None or self._places.get(scene_id) == domain_id:
                self._places.pop(scene_id, None)

    def scene_domain(self, scene_id: str) -> str | None:
        """場景在哪個領域資料夾；沒有登記時到磁碟上找一次。"""
        with self._places_lock:
            found = self._places.get(scene_id)
        if found is not None:
            return found
        for candidate in sorted(self.domains.glob(f"*/{SCENES_DIR}/{scene_id}")):
            if candidate.is_dir() and not candidate.parts[-3].startswith("."):
                domain_id = candidate.parts[-3]
                self.place_scene(scene_id, domain_id)
                return domain_id
        return None

    def scene_dir(self, scene_id: str) -> Path:
        """場景的資料夾 domains/<領域>/scenes/<場景>/。"""
        domain_id = self.scene_domain(scene_id) or _NOWHERE
        return self.domains / domain_id / SCENES_DIR / scene_id

    def place_composite(self, code: str, domain_id: str) -> None:
        """登記組合場景在哪個領域資料夾（M11 PR 2）。"""
        with self._places_lock:
            self._composites[code] = domain_id

    def forget_composite(self, code: str, domain_id: str | None = None) -> None:
        with self._places_lock:
            if domain_id is None or self._composites.get(code) == domain_id:
                self._composites.pop(code, None)

    def composite_domain(self, code: str) -> str | None:
        """組合場景在哪個領域資料夾；沒有登記時到磁碟上找一次。"""
        with self._places_lock:
            found = self._composites.get(code)
        if found is not None:
            return found
        for candidate in sorted(self.domains.glob(f"*/{COMPOSITES_DIR}/{code}")):
            if candidate.is_dir() and not candidate.parts[-3].startswith("."):
                domain_id = candidate.parts[-3]
                self.place_composite(code, domain_id)
                return domain_id
        return None

    def composite_dir(self, code: str) -> Path:
        """組合場景的資料夾 domains/<領域>/composites/<代號>/。"""
        domain_id = self.composite_domain(code) or _NOWHERE
        return self.domains / domain_id / COMPOSITES_DIR / code

    # ------------------------------------------------------------ 角色、錄製、調試

    def role_state(self, role_id: str) -> Path:
        """角色的登入狀態檔（可能還不存在）。"""
        return self.roles / role_id / "state.json"

    def recording_dir(self, recording_id: str) -> Path:
        return self.recordings / recording_id

    def recording_file(self, recording_id: str, name: str) -> Path | None:
        """錄製目錄裡的檔案；不存在時回傳 None。"""
        if name not in ("raw.py", "scenario.yaml"):
            return None
        path = self.recording_dir(recording_id) / name
        return path if path.is_file() else None

    def debug_dir(self, session_id: str) -> Path:
        return self.debug / session_id

    def debug_file(self, session_id: str, name: str) -> Path | None:
        """調試工作階段的截圖；路徑不合規則或不存在時回傳 None。"""
        if not re.fullmatch(r"shot-\d{4,}\.png", name):
            return None
        path = self.debug_dir(session_id) / name
        return path if path.is_file() else None

    # ------------------------------------------------------------ 版本

    def revision_dir(self, scene_id: str, number: int) -> Path:
        return self.scene_dir(scene_id) / REVISIONS_DIR / str(number)

    def scenario_path(self, scene_id: str, number: int) -> Path:
        return self.revision_dir(scene_id, number) / SCENARIO_FILE

    def snapshot(self, scene_id: str, number: int, run_id: str) -> Path:
        """本機執行開始時把版本檔案複製到 work/<執行編號>/（任務紀錄第 6 節）：執行中拉取、
        重新載入或刪除領域資料夾都不影響這次執行，和遠端 worker 自帶檔案一致。回傳場景檔。"""
        target = self.work / run_id
        _remove_tree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.revision_dir(scene_id, number), target)
        for path in target.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        return target / SCENARIO_FILE

    def drop_snapshot(self, run_id: str) -> None:
        _remove_tree(self.work / run_id)

    def check(self, files: Mapping[str, str], *, scene_id: str | None = None) -> CheckedRevision:
        """檢查一組版本檔案：路徑、場景校驗、場景 id、是否有多餘的檔案。"""
        problems = self._check_paths(files)
        if problems:
            return CheckedRevision(dict(files), issues=tuple(problems))
        with tempfile.TemporaryDirectory(prefix="rpa-revision-") as temp:
            folder = Path(temp)
            _write_files(folder, files)
            validated = validate_file(folder / SCENARIO_FILE)
            scenario = validated.scenario
            if scenario is None:
                return CheckedRevision(dict(files), issues=validated.issues)
            issues: list[Issue] = []
            if scene_id is not None and scenario.id != scene_id:
                issues.append(
                    _issue("server.id_mismatch", t("revision.id_mismatch", id=scene_id), ("id",))
                )
            used = set(scenario_sources(folder / SCENARIO_FILE, scenario))
            issues += [
                _issue("server.extra_file", t("revision.extra_file", path=path))
                for path in sorted(set(files) - used)
            ]
            if issues:
                return CheckedRevision(dict(files), issues=tuple(issues))
            digest = scenario_digest(folder / SCENARIO_FILE, scenario)
        return CheckedRevision(dict(files), scenario=scenario, digest=digest)

    @staticmethod
    def _check_paths(files: Mapping[str, str]) -> list[Issue]:
        problems: list[Issue] = []
        if SCENARIO_FILE not in files:
            problems.append(_issue("server.no_scenario", t("revision.no_scenario")))
        if len(files) > _MAX_FILES:
            problems.append(_issue("server.too_many_files", t("revision.too_many_files")))
        for path, text in files.items():
            if not _FILE_PATH.fullmatch(path):
                problems.append(_issue("server.bad_path", t("revision.bad_path", path=path)))
            elif len(text.encode("utf-8")) > _MAX_BYTES:
                problems.append(_issue("server.too_large", t("revision.too_large", path=path)))
        return problems

    def save(self, scene_id: str, number: int, files: Mapping[str, str]) -> Path:
        """寫入新版本（先寫暫存目錄再改名，不會留下寫到一半的版本）。

        場景要先用 :meth:`place_scene` 登記在某個領域資料夾。
        """
        if self.scene_domain(scene_id) is None:
            raise LookupError(f"scene {scene_id} is not placed in any domain")
        target = self.revision_dir(scene_id, number)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f".{number}-{uuid.uuid4().hex[:8]}")
        _write_files(staging, files)
        try:
            if target.exists():
                raise StorageConflictError(str(target))
            staging.rename(target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return target

    def discard(self, scene_id: str, number: int) -> None:
        """移除沒有寫進資料庫的版本目錄（例如資料庫交易失敗）。"""
        shutil.rmtree(self.revision_dir(scene_id, number), ignore_errors=True)

    def load(self, scene_id: str, number: int) -> dict[str, str]:
        folder = self.revision_dir(scene_id, number)
        return {
            path.relative_to(folder).as_posix(): _read_text(path)
            for path in sorted(folder.rglob("*"))
            if path.is_file()
        }

    def digest(self, scene_id: str, number: int) -> str | None:
        """從磁碟重新計算版本的雜湊；檔案不見或不再通過校驗時回傳 None。"""
        path = self.scenario_path(scene_id, number)
        scenario = validate_file(path).scenario
        if scenario is None:
            return None
        try:
            return scenario_digest(path, scenario)
        except OSError:
            return None

    # ------------------------------------------------------------ 執行目錄

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id

    def run_file(self, run_id: str, relative: str) -> Path | None:
        """執行目錄裡的檔案；路徑不合規則、跳出執行目錄或不存在時回傳 None。"""
        if not _FILE_PATH.fullmatch(relative):
            return None
        folder = self.run_dir(run_id).resolve()
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            return None
        return path

    def run_files(self, run_id: str) -> list[str]:
        folder = self.run_dir(run_id)
        if not folder.is_dir():
            return []
        return sorted(
            path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()
        )


def _read_text(path: Path) -> str:
    """讀回原本的內容（保留換行字元，不轉換 CRLF）。"""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_files(folder: Path, files: Mapping[str, str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for relative, text in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    if os.name != "nt":
        # 版本內容寫入後就不再修改
        for path in folder.rglob("*"):
            if path.is_file():
                path.chmod(0o444)


def _remove_tree(folder: Path) -> None:
    """刪除資料夾（版本檔案是唯讀的，Windows 上要先改成可寫）；不存在就算了。"""

    def retry(function: Callable[..., object], path: str, _error: BaseException) -> None:
        Path(path).chmod(0o700)
        function(path)

    if folder.exists():
        shutil.rmtree(folder, onexc=retry)


def _yaml_string(value: str) -> str:
    """YAML 的雙引號字串（JSON 字串也是合法的 YAML）。"""
    return json.dumps(value, ensure_ascii=False)


def new_scene_template(scene_id: str, name: str, category: str | None) -> str:
    """新場景的第一個版本：一個能通過校驗的最小場景，使用者再改成真正的步驟。"""
    lines = [
        f"# {t('template.comment')}",
        "schemaVersion: 1",
        f"id: {scene_id}",
        f"name: {_yaml_string(name)}",
    ]
    if category:
        lines.append(f"category: {_yaml_string(category)}")
    lines += [
        "",
        "browser:",
        "  baseUrl: https://example.com",
        "",
        "steps:",
        "  - id: open",
        "    action: goto",
        "    url: /",
        "",
    ]
    return "\n".join(lines)
