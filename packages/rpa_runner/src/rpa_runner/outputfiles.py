"""產出的檔案（ADR 0020）：``type: file`` 的出參與 ``files.json``（檔案變化）。

``type: file`` 的出參：``from`` 或 assertion.py 給出的值可以是

- 路徑：相對路徑是相對於共用工作資料夾（Python 節點的工作目錄）；絕對路徑也要在共用工作
  資料夾或這次執行的 ``outputs/`` 裡；
- ``download`` 步驟的事實 ``{"workspace": "downloads/…", …}``，或 ``{"path": …}``。

出參階段（獨立斷言通過之後）把檔案複製進執行目錄的 ``outputs/``（跟著執行紀錄上傳，報告可以
下載），也確保它在共用工作資料夾裡（Python 節點寫在 ``outputs/`` 的，複製到
``.outputs/<執行編號>/``），值換成 ``{"workspace", "name", "size", "sha256"}``：同一次組合運行
的下游節點把它當成檔案入參。單檔與合計的上限沿用檔案入參（M7c）。

``files.json``：自動化前後，共用工作資料夾與 ``outputs/`` 裡新增、改變、刪除的檔案，報告的
「檔案變化」用；最多記 :data:`MAX_SCANNED` 個檔案。
"""

import os
import shutil
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

from rpa_core.dsl import Scenario
from rpa_core.dsl.files import clean_name, file_meta, format_size, is_workspace_ref
from rpa_runner.contract import Problem
from rpa_runner.files import OUTPUTS_DIR
from rpa_runner.i18n import t

__all__ = [
    "FILE_CHANGES",
    "MAX_SCANNED",
    "OUTPUT_COPIES",
    "FileState",
    "changes",
    "publish_file_outputs",
    "scan",
    "unique_path",
]

FILE_CHANGES: Final = "files.json"
"""執行目錄裡的檔案變化。"""
OUTPUT_COPIES: Final = ".outputs"
"""共用工作資料夾裡放 Python 節點 ``outputs/`` 產出檔案副本的資料夾。"""
MAX_SCANNED: Final = 5000
"""比較檔案變化時每邊最多看幾個檔案（太多時只記前面的，``truncated`` 是 true）。"""
_SKIPPED_DIRS: Final = frozenset({".tmp", "__pycache__", OUTPUT_COPIES})
"""不算檔案變化的資料夾：Python 節點的暫存、Python 的快取、產出檔案的副本。"""

Where = Literal["workspace", "outputs"]
FileState = dict[tuple[str, str], tuple[int, int]]
"""(位置, 相對路徑) → (大小, 修改時間 ns)。"""


def unique_path(folder: Path, name: str) -> Path:
    """``folder/name``；已經有同名的檔案時加上 -2、-3…。"""
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 2
    while target.exists():
        target = folder / f"{stem}-{number}{suffix}"
        number += 1
    return target


def _inside(path: Path, folder: Path) -> bool:
    try:
        return path.is_relative_to(folder.resolve())
    except OSError:
        return False


@dataclass(frozen=True, slots=True)
class _Source:
    path: Path | None
    problem: str | None = None


def _source(value: object, workspace: Path, outputs: Path) -> _Source:
    """出參的值 → 檔案；不認得或不在允許的位置時回傳問題（訊息鍵）。"""
    if isinstance(value, list):
        return _Source(None, "contract.file_output_one")
    raw: str | None = None
    if isinstance(value, str):
        raw = value
    elif isinstance(value, Mapping):
        data = cast("Mapping[str, object]", value)
        ref = data.get("workspace")
        if isinstance(ref, str):
            if not is_workspace_ref(ref):
                return _Source(None, "contract.file_output_value")
            raw = str(workspace / ref)
        elif isinstance(data.get("path"), str):
            raw = str(data["path"])
    if raw is None or not raw.strip():
        return _Source(None, "contract.file_output_value")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = workspace / path
    try:
        resolved = path.resolve()
    except OSError:
        return _Source(None, "contract.file_output_missing")
    if not (_inside(resolved, workspace) or _inside(resolved, outputs)):
        return _Source(None, "contract.file_output_outside")
    if not resolved.is_file():
        return _Source(None, "contract.file_output_missing")
    return _Source(resolved)


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)  # 同一個磁碟：不佔空間
    except OSError:
        shutil.copy2(source, target)


def publish_file_outputs(
    scenario: Scenario,
    outputs: MutableMapping[str, object],
    folder: Path,
    workspace: Path,
    run_id: str,
    *,
    max_file: int,
    max_total: int,
) -> list[Problem]:
    """把 ``type: file`` 出參的檔案放進 ``outputs/`` 與共用工作資料夾，值換成檔案的說明。

    有問題時回傳問題（什麼都不發布，由呼叫的人處理）；``outputs`` 只在沒有問題時改寫。
    """
    target_dir = folder / OUTPUTS_DIR
    problems: list[Problem] = []
    found: dict[str, Path] = {}
    total = 0
    for name, spec in scenario.outputs.items():
        if spec.type != "file" or name not in outputs:
            continue
        source = _source(outputs[name], workspace, target_dir)
        if source.path is None:
            key = source.problem or "contract.file_output_value"
            problems.append(Problem(name, t(key, name=name)))
            continue
        size = source.path.stat().st_size
        if size > max_file:
            problems.append(
                Problem(
                    name,
                    t(
                        "contract.file_output_too_large",
                        name=name,
                        file=source.path.name,
                        size=format_size(size),
                        limit=format_size(max_file),
                    ),
                )
            )
            continue
        total += size
        found[name] = source.path
    if total > max_total:
        problems.append(
            Problem(
                "",
                t(
                    "contract.files_too_large",
                    size=format_size(total),
                    limit=format_size(max_total),
                ),
            )
        )
    if problems:
        return problems
    published: dict[str, object] = {}
    copies = workspace / OUTPUT_COPIES / run_id
    for name, path in found.items():
        if path.parent == target_dir.resolve():
            kept = path
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            kept = unique_path(target_dir, clean_name(path.name))
            _copy(path, kept)
        if _inside(path, workspace):
            ref = path.relative_to(workspace.resolve()).as_posix()
        else:
            copy = unique_path(copies, kept.name)
            copies.mkdir(parents=True, exist_ok=True)
            _copy(kept, copy)
            ref = copy.relative_to(workspace).as_posix()
        meta = file_meta(kept, kept.name)
        published[name] = {"workspace": ref, **meta.to_json()}
    outputs.update(published)
    return []


def scan(workspace: Path | None, outputs: Path) -> tuple[FileState, bool]:
    """共用工作資料夾與 ``outputs/`` 裡的檔案；第二個值是不是超過上限、沒有看完。"""
    state: FileState = {}
    truncated = False
    for where, root in (("workspace", workspace), ("outputs", outputs)):
        if root is None or not root.is_dir():
            continue
        count = 0
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(item for item in dirs if item not in _SKIPPED_DIRS)
            base = Path(current)
            for file_name in sorted(files):
                if count >= MAX_SCANNED:
                    truncated = True
                    break
                path = base / file_name
                try:
                    info = path.stat()
                except OSError:
                    continue
                count += 1
                state[(where, path.relative_to(root).as_posix())] = (info.st_size, info.st_mtime_ns)
            if truncated:
                break
    return state, truncated


def changes(before: FileState, after: FileState, *, truncated: bool) -> dict[str, object]:
    """兩次 :func:`scan` 的差異：新增、改變、刪除的檔案（位置、相對路徑、大小）。"""

    def item(key: tuple[str, str], size: int) -> dict[str, object]:
        return {"where": key[0], "path": key[1], "size": size}

    added = [item(key, after[key][0]) for key in sorted(after.keys() - before.keys())]
    removed = [item(key, before[key][0]) for key in sorted(before.keys() - after.keys())]
    changed = [
        item(key, after[key][0])
        for key in sorted(after.keys() & before.keys())
        if after[key] != before[key]
    ]
    return {"added": added, "changed": changed, "removed": removed, "truncated": truncated}
