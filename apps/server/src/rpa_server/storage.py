"""資料目錄裡的檔案：場景版本與執行目錄。

::

    <資料目錄>/
      rpa.db                    SQLite（預設）
      scenes/<場景 id>/<版本>/   scenario.yaml；腳本場景另有兩支腳本
      runs/<執行編號>/           rpa-runner 的執行目錄（input.json、report.html…）

版本一旦寫入就不再修改；改內容就是新版本。版本內容的雜湊與 rpa-runner 記在 result.json 的
scenarioHash 用同一個演算法（:func:`rpa_runner.run.scenario_digest`），發布門檻靠它確認
「通過驗證的就是要發布的版本」。
"""

import json
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from rpa_core.dsl import Issue, Scenario, validate_file
from rpa_runner.run import scenario_digest, scenario_sources
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
        self.root = root
        self.scenes = root / "scenes"
        self.runs = root / "runs"

    def ensure(self) -> None:
        for folder in (self.scenes, self.runs):
            folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 版本

    def revision_dir(self, scene_id: str, number: int) -> Path:
        return self.scenes / scene_id / str(number)

    def scenario_path(self, scene_id: str, number: int) -> Path:
        return self.revision_dir(scene_id, number) / SCENARIO_FILE

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
        """寫入新版本（先寫暫存目錄再改名，不會留下寫到一半的版本）。"""
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
