"""檔案入參（M7c）：把入參的值換成這台電腦上的檔案，交給瀏覽器。

值的寫法見 :mod:`rpa_core.dsl.files`。執行前（入參階段，啟動瀏覽器之前）：

1. 找到檔案：上傳檔由呼叫的人給（Worker 下載好、管理 Portal 本機執行時是伺服器的檔案區）；
   場景附件在場景資料夾的 ``files/``；``path`` 是那台電腦上的路徑，管理 Portal 交來的只能在
   允許的資料夾裡（``folders``），命令列不限；``workspace`` 是上游節點產出、在組合運行的共用
   工作資料夾裡的檔案（ADR 0020）。
2. 檢查：存在、單檔大小（場景的 maxSize 與上限取小的）、類型（accept）、合計大小。
3. 以網頁要看到的檔名放進暫存資料夾（硬連結，不行就複製），算 sha256。

表達式、input.json 與報告只拿到 ``{"name", "size", "sha256"}``；本機路徑寫在暫存資料夾的
``paths.json``，只給自動化子程序。暫存資料夾不在執行目錄裡，不會跟著執行目錄上傳。

允許的資料夾（D5）：Worker App、錄製端 App 依自己的設定設好環境變數 ``RPA_INPUT_FOLDERS``
（以 ``os.pathsep`` 分隔），它開的子程序都會繼承；管理 Portal 本機執行時由伺服器設定帶入。
"""

import contextlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

from rpa_core.dsl import Scenario
from rpa_core.dsl.files import (
    MAX_FILE_BYTES,
    MAX_RUN_BYTES,
    FileValue,
    FileValueError,
    accepts,
    file_meta,
    file_values,
    format_size,
    inside_folders,
)
from rpa_runner.contract import Problem
from rpa_runner.i18n import t

__all__ = [
    "ENV_INPUT_FOLDERS",
    "PATHS_FILE",
    "FileSources",
    "PreparedFiles",
    "env_folders",
    "given_files",
    "prepare_files",
    "read_paths",
    "remove_staging",
    "session_files",
]

PATHS_FILE: Final = "paths.json"
"""暫存資料夾裡的本機路徑對照：入參名稱 → 檔案路徑清單。"""
ENV_INPUT_FOLDERS: Final = "RPA_INPUT_FOLDERS"
"""``path`` 值可以讀的資料夾（以 os.pathsep 分隔）；Worker／錄製端 App 依設定設好。"""


def env_folders(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """環境變數 ``RPA_INPUT_FOLDERS`` 列的資料夾；沒有設定時是空的（不能用 path 值）。"""
    text = (os.environ if environ is None else environ).get(ENV_INPUT_FOLDERS, "")
    return tuple(Path(item).expanduser() for item in text.split(os.pathsep) if item.strip())


@dataclass(frozen=True, slots=True)
class FileSources:
    """檔案從哪裡來。"""

    scenario_dir: Path
    """場景資料夾：附件在它的 ``files/`` 底下。"""
    uploads: Mapping[str, Path] = field(default_factory=dict[str, Path])
    """上傳檔代號 → 這台電腦上的檔案（Worker 已下載並比對過 sha256）。"""
    folders: Sequence[Path] | None = None
    """``path`` 值可以讀的資料夾；None 不限（命令列 rpa run，使用者自己的電腦）。"""
    max_file: int = MAX_FILE_BYTES
    max_total: int = MAX_RUN_BYTES
    workspace: Path | None = None
    """組合運行的共用工作資料夾（ADR 0020）：``workspace`` 值在這裡找；None 時不能用。"""


@dataclass(slots=True)
class PreparedFiles:
    """準備好的檔案入參。"""

    meta: dict[str, object] = field(default_factory=dict[str, object])
    """入參名稱 → ``{"name", "size", "sha256"}``（multiple 時是清單）；
    取代 input.json 裡原本的值。"""
    paths: dict[str, list[Path]] = field(default_factory=dict[str, list[Path]])
    problems: list[Problem] = field(default_factory=list[Problem])


def _link(source: Path, target: Path) -> None:
    """硬連結（同一個磁碟、不佔空間）；不行（跨磁碟、網路磁碟、沒有權限）就複製。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def _locate(item: FileValue, sources: FileSources) -> tuple[Path | None, str | None]:
    """檔案在這台電腦的哪裡；找不到時回傳 (None, 訊息鍵)。"""
    match item.source:
        case "upload":
            path = sources.uploads.get(item.ref)
            return (path, None) if path is not None and path.is_file() else (None, "upload")
        case "attachment":
            path = sources.scenario_dir / item.ref
            return (path, None) if path.is_file() else (None, "attachment")
        case "workspace":
            if sources.workspace is None:
                return None, "no_workspace"
            path = sources.workspace / item.ref
            if not inside_folders(path, [sources.workspace]):
                return None, "not_found"
            return (path, None) if path.is_file() else (None, "not_found")
        case _:
            path = Path(item.ref).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            if sources.folders is not None and not inside_folders(path, sources.folders):
                return None, "not_allowed"
            return (path, None) if path.is_file() else (None, "not_found")


def prepare_files(
    scenario: Scenario,
    values: Mapping[str, object],
    sources: FileSources,
    staging: Path,
) -> PreparedFiles:
    """把 file 入參換成暫存資料夾裡的檔案；``values`` 是已經求過動態值的入參。

    有問題時記在 ``problems``（訊息是目前語言），沒有問題的入參照樣準備好。
    """
    prepared = PreparedFiles()
    total = 0
    for name, spec in scenario.inputs.items():
        if spec.type != "file" or name not in values:
            continue
        multiple = bool(spec.multiple)
        try:
            items = file_values(values[name], multiple=multiple)
        except FileValueError as error:
            prepared.problems.append(
                Problem(name, t("contract.input_invalid", name=name, rule=error.message))
            )
            continue
        limit = min(spec.max_bytes or sources.max_file, sources.max_file)
        metas: list[object] = []
        paths: list[Path] = []
        for index, item in enumerate(items):
            shown = item.display_name
            path, missing = _locate(item, sources)
            if path is None:
                label = item.name or item.ref
                prepared.problems.append(
                    Problem(name, t(f"contract.file_{missing}", name=name, file=label))
                )
                continue
            try:
                size = path.stat().st_size
            except OSError as error:
                prepared.problems.append(
                    Problem(
                        name,
                        t("contract.file_unreadable", name=name, file=shown, detail=error.strerror),
                    )
                )
                continue
            if size > limit:
                prepared.problems.append(
                    Problem(
                        name,
                        t(
                            "contract.file_too_large",
                            name=name,
                            file=shown,
                            size=format_size(size),
                            limit=format_size(limit),
                        ),
                    )
                )
                continue
            if not accepts(spec.accept, shown):
                prepared.problems.append(
                    Problem(
                        name,
                        t(
                            "contract.file_type",
                            name=name,
                            file=shown,
                            accept=", ".join(spec.accept or ()),
                        ),
                    )
                )
                continue
            total += size
            target = staging / name / str(index) / shown
            try:
                _link(path, target)
                meta = file_meta(target, shown)
            except OSError as error:
                prepared.problems.append(
                    Problem(
                        name,
                        t("contract.file_unreadable", name=name, file=shown, detail=error.strerror),
                    )
                )
                continue
            metas.append(meta.to_json())
            paths.append(target)
        prepared.meta[name] = metas if multiple else (metas[0] if metas else None)
        prepared.paths[name] = paths
    if total > sources.max_total:
        prepared.problems.append(
            Problem(
                "",
                t(
                    "contract.files_too_large",
                    size=format_size(total),
                    limit=format_size(sources.max_total),
                ),
            )
        )
    if prepared.paths:
        staging.mkdir(parents=True, exist_ok=True)
        (staging / PATHS_FILE).write_text(
            json.dumps(
                {name: [str(path) for path in items] for name, items in prepared.paths.items()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return prepared


def session_files(
    scenario: Scenario,
    values: Mapping[str, object],
    given: Mapping[str, Sequence[Path]],
    scenario_dir: Path,
    staging: Path,
) -> PreparedFiles:
    """調試與接著錄製：``given`` 是管理 Portal 已經準備好、以原始檔名送來的檔案（上傳檔與附件）；
    其他檔案入參（``path`` 值）在這台找，只能在 ``RPA_INPUT_FOLDERS`` 裡。"""
    prepared = PreparedFiles()
    rest: dict[str, object] = {}
    for name, spec in scenario.inputs.items():
        if spec.type != "file":
            continue
        if name in given:
            paths = list(given[name])
            metas: list[object] = [file_meta(path, path.name).to_json() for path in paths]
            prepared.meta[name] = metas if spec.multiple else (metas[0] if metas else None)
            prepared.paths[name] = paths
        elif name in values:
            rest[name] = values[name]
    if rest:
        local = prepare_files(
            scenario, rest, FileSources(scenario_dir=scenario_dir, folders=env_folders()), staging
        )
        prepared.meta.update(local.meta)
        prepared.paths.update(local.paths)
        prepared.problems += local.problems
    return prepared


def given_files(pairs: Sequence[Sequence[str]] | None) -> dict[str, list[Path]]:
    """命令列的 ``--file 入參 路徑``（可以重複，同一個入參依序）→ 入參名稱 → 檔案。"""
    result: dict[str, list[Path]] = {}
    for name, path in pairs or ():
        result.setdefault(name, []).append(Path(path))
    return result


def read_paths(path: Path | None) -> dict[str, list[Path]]:
    """讀 ``paths.json``（自動化子程序用）；沒有或格式不對時是空的。"""
    if path is None or not path.is_file():
        return {}
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    result: dict[str, list[Path]] = {}
    for name, items in cast("dict[object, object]", data).items():
        if isinstance(name, str) and isinstance(items, list):
            result[name] = [Path(str(item)) for item in cast("list[object]", items)]
    return result


def remove_staging(staging: Path) -> None:
    """刪掉暫存資料夾（Windows 上檔案可能還被瀏覽器開著，刪不掉就留著）。"""
    with contextlib.suppress(OSError):
        shutil.rmtree(staging)
