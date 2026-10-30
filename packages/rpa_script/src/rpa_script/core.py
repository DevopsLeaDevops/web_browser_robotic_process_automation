"""Python 節點的執行狀態：入參、事實、步驟、產出檔案、資料預覽與主控台輸出。

一次執行只有一個 :class:`Run`，由啟動器（``python -m rpa_script``）依命令列參數與環境變數
建立；腳本用 ``@automation`` 拿到它，或呼叫 :func:`current`。只用標準函式庫。

檔案契約和沒有用這個套件的腳本完全相同（ADR 0009、0020）：

- ``--input``：運行態入參（input.json）；``--facts``：要寫出的事實（facts.json）
- ``RPA_STEPS``：步驟紀錄（steps.json，格式同 DSL 場景）
- ``RPA_OUTPUT_DIR``：產出檔案的資料夾；``RPA_WORKSPACE``：共用工作資料夾（也是工作目錄）
- ``RPA_INPUT_FILES``：file 入參名稱 → 實際路徑清單（JSON 檔）
- ``RPA_SECRET_NAMES``：場景宣告的 Secrets 名稱（JSON 陣列），值在同名的環境變數
- ``RPA_DEADLINE_SECONDS``、``RPA_LANG``、``RPA_RUNTIME``、``RPA_PLATFORM``
"""

import json
import os
import re
import sys
import time
import traceback
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, TextIO, cast

__all__ = [
    "MASK",
    "Run",
    "StepError",
    "activate",
    "automation",
    "current",
    "registered",
    "text",
]

MASK: Final = "***"
"""Secrets 的值在輸出裡換成這個（長度 3 以下的值不遮罩，和 Runner 相同）。"""
_PREVIEW_ROWS: Final = 50
_PREVIEW_COLUMNS: Final = 30
_PREVIEW_CELL: Final = 200
_STEP_ID: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

_TEXTS: Final[dict[str, dict[str, str]]] = {
    "outside": {"zh-Hant": "步驟外的程式", "zh-Hans": "步骤外的程序", "en": "Code outside steps"},
    "step_id": {
        "zh-Hant": "步驟 id 只能用小寫英文字母、數字、_ 與 -：{id}",
        "zh-Hans": "步骤 id 只能用小写英文字母、数字、_ 与 -：{id}",
        "en": "Step ids use lowercase letters, digits, _ and - only: {id}",
    },
    "two_entries": {
        "zh-Hant": "一支腳本只能有一個 @automation",
        "zh-Hans": "一个脚本只能有一个 @automation",
        "en": "A script can have only one @automation",
    },
}


def text(key: str, **params: object) -> str:
    """這個套件自己的訊息，依 ``RPA_LANG``（Runner 給的介面語言）。"""
    lang = os.environ.get("RPA_LANG", "zh-Hant")
    table = _TEXTS[key]
    return table.get(lang, table["zh-Hant"]).format(**params)


class StepError(Exception):
    """預期中的失敗（找不到檔案、資料格式不對）：報告只顯示訊息，不顯示呼叫堆疊。"""


def _json_file(path: str | None) -> object:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass(slots=True)
class _Step:
    id: str
    name: str | None
    occurrence: int
    parent: str | None
    source: str | None
    started: float
    status: str = "running"
    duration_ms: int = 0
    error: str | None = None
    ended: float | None = None
    previews: list[str] = field(default_factory=list[str])
    files: dict[str, list[str]] | None = None

    def to_json(self) -> dict[str, object]:
        def moment(value: float | None) -> str | None:
            if value is None:
                return None
            stamp = datetime.fromtimestamp(value, UTC).isoformat(timespec="milliseconds")
            return stamp.replace("+00:00", "Z")

        return {
            "id": self.id,
            "action": "python",
            "name": self.name,
            "status": self.status,
            "durationMs": self.duration_ms,
            "error": self.error,
            "artifacts": [],
            "startedAt": moment(self.started),
            "endedAt": moment(self.ended),
            "occurrence": self.occurrence,
            "parent": self.parent,
            "source": self.source,
            "previews": self.previews,
            **({"files": self.files} if self.files else {}),
        }


class Run:
    """一次執行：腳本與平台之間的一切。"""

    def __init__(
        self,
        *,
        inputs: Mapping[str, object],
        facts_path: Path | None,
        steps_path: Path | None,
        output_dir: Path,
        workspace: Path,
        input_files: Mapping[str, Sequence[str]],
        secrets: Mapping[str, str],
        deadline_seconds: float | None,
        script: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.inputs: Mapping[str, object] = dict(inputs)
        """運行態入參（和 input.json 同一份）。"""
        self.facts: dict[str, object] = {}
        """事實：結束時寫成 facts.json（失敗時也寫出已經有的部分）。"""
        self.output_dir = output_dir
        """產出檔案的資料夾：裡面的檔案跟著執行目錄上傳，報告可以下載。"""
        self.workspace = workspace
        """共用工作資料夾：同一次組合運行的節點都看得到，運行結束就清掉。"""
        self.input_files: Mapping[str, list[Path]] = {
            name: [Path(path) for path in paths] for name, paths in input_files.items()
        }
        """file 入參名稱 → 這台電腦上的檔案清單（單檔的入參也是只有一個的清單）。"""
        self.secrets: Mapping[str, str] = dict(secrets)
        self.facts_path = facts_path
        self.steps_path = steps_path
        self.script = script
        self._clock = clock
        self._started = clock()
        self._deadline = deadline_seconds
        self._steps: list[_Step] = []
        self._stack: list[_Step] = []
        self._counts: dict[str, int] = {}
        self._previews = 0
        self.step_error: BaseException | None = None
        """最近一次在步驟裡拋出的錯誤（啟動器用來判斷錯誤是不是發生在步驟外）。"""

    # ------------------------------------------------------------ 建立

    @classmethod
    def from_environment(
        cls, args: Mapping[str, str], environ: Mapping[str, str] | None = None
    ) -> "Run":
        """依啟動器讀到的命令列參數（input、facts）與環境變數建立。"""
        env = os.environ if environ is None else environ
        facts = args.get("facts")
        folder = Path(facts).parent if facts else Path.cwd()
        raw_inputs = _json_file(args.get("input"))
        raw_files = _json_file(env.get("RPA_INPUT_FILES"))
        try:
            raw_names: object = json.loads(env.get("RPA_SECRET_NAMES", "[]"))
        except ValueError:
            raw_names = []
        names = (
            [str(item) for item in cast("list[object]", raw_names)]
            if isinstance(raw_names, list)
            else []
        )
        files: dict[str, list[str]] = {}
        if isinstance(raw_files, dict):
            for name, value in cast("dict[str, object]", raw_files).items():
                items = cast("list[object]", value) if isinstance(value, list) else [value]
                files[name] = [str(item) for item in items]
        deadline = env.get("RPA_DEADLINE_SECONDS")
        try:
            seconds = float(deadline) if deadline else None
        except ValueError:
            seconds = None
        output = Path(env.get("RPA_OUTPUT_DIR") or folder / "outputs")
        workspace = Path(env.get("RPA_WORKSPACE") or Path.cwd())
        output.mkdir(parents=True, exist_ok=True)
        steps = env.get("RPA_STEPS")
        script = args.get("script")
        return cls(
            inputs=cast("dict[str, object]", raw_inputs) if isinstance(raw_inputs, dict) else {},
            facts_path=Path(facts) if facts else None,
            steps_path=Path(steps) if steps else None,
            output_dir=output,
            workspace=workspace,
            input_files=files,
            secrets={name: env[name] for name in names if name in env},
            deadline_seconds=seconds,
            script=Path(script) if script else None,
        )

    # ------------------------------------------------------------ 資訊

    @property
    def remaining_seconds(self) -> float | None:
        """總期限剩下的秒數；沒有期限時是 None。"""
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - (self._clock() - self._started))

    @property
    def platform(self) -> str:
        """``windows``、``macos`` 或 ``linux``。"""
        value = os.environ.get("RPA_PLATFORM", "")
        if value:
            return value.split("-", 1)[0]
        return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")

    @property
    def runtime(self) -> str | None:
        """RPA Python 運行環境的版本；不是在運行環境裡執行時是 None。"""
        return os.environ.get("RPA_RUNTIME") or None

    @property
    def lang(self) -> str:
        """介面語言（zh-Hant、zh-Hans、en）。"""
        return os.environ.get("RPA_LANG", "zh-Hant")

    def mask(self, value: str) -> str:
        """把文字裡的 Secrets 值換成 ***。"""
        for secret in sorted(self.secrets.values(), key=len, reverse=True):
            if len(secret) > 3:
                value = value.replace(secret, MASK)
        return value

    # ------------------------------------------------------------ 輸出

    def log(self, message: object) -> None:
        """寫一行到主控台輸出（automation.log），前面加上時間與目前的步驟。"""
        step = self._stack[-1].id if self._stack else "-"
        moment = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        sys.stdout.write(f"{moment}  [{step}]  {message}\n")
        sys.stdout.flush()

    @contextmanager
    def step(self, step_id: str, name: str | None = None) -> Generator[None]:
        """標出一步。迴圈裡同一個 id 記成第 n 次；可以巢狀。失敗的例外照樣往外拋。"""
        if not _STEP_ID.fullmatch(step_id):
            raise ValueError(text("step_id", id=step_id))
        self._counts[step_id] = self._counts.get(step_id, 0) + 1
        record = _Step(
            id=step_id,
            name=self.mask(name) if name else None,
            occurrence=self._counts[step_id],
            parent=self._stack[-1].id if self._stack else None,
            source=_caller_source(self.script),
            started=self._clock(),
        )
        self._steps.append(record)
        self._stack.append(record)
        self._write_steps()
        before = self._scan()
        try:
            yield
        except BaseException as error:
            record.status = "failed"
            record.error = self.mask(describe(error))
            self.step_error = error
            raise
        else:
            record.status = "passed"
        finally:
            record.ended = self._clock()
            record.duration_ms = int((record.ended - record.started) * 1000)
            record.files = _file_changes(before, self._scan()) or None
            self._stack.pop()
            self._write_steps()

    def _scan(self) -> dict[str, tuple[int, int]]:
        """共用工作資料夾與產出檔案資料夾裡的檔案（步驟前後比較，報告的「檔案變化」）。"""
        found: dict[str, tuple[int, int]] = {}
        for where, root in (("workspace", self.workspace), ("outputs", self.output_dir)):
            count = 0
            for current, dirs, files in os.walk(root):
                dirs[:] = sorted(item for item in dirs if item not in _SKIPPED_DIRS)
                for file_name in sorted(files):
                    if count >= MAX_SCANNED_FILES:
                        break
                    path = Path(current) / file_name
                    try:
                        info = path.stat()
                    except OSError:
                        continue
                    count += 1
                    relative = path.relative_to(root).as_posix()
                    found[f"{where}/{relative}"] = (info.st_size, info.st_mtime_ns)
        return found

    def preview(self, name: str, value: object) -> None:
        """留一份資料預覽（前 50 列、30 欄，每格 200 字），報告與回看會顯示。"""
        if self.facts_path is None:
            return
        folder = self.facts_path.parent / "previews"
        folder.mkdir(parents=True, exist_ok=True)
        self._previews += 1
        file_name = f"{self._previews:03d}.json"
        data = {"name": self.mask(name), **_preview(value, self.mask)}
        if self._stack:
            data["step"] = self._stack[-1].id
            self._stack[-1].previews.append(f"previews/{file_name}")
        _write_json(folder / file_name, data)
        self._write_steps()

    def outside_failure(self, error: BaseException) -> None:
        """步驟以外的程式拋出的錯誤：記成一個失敗的「步驟外的程式」，附行號。"""
        moment = self._clock()
        self._steps.append(
            _Step(
                id="script",
                name=text("outside"),
                occurrence=1,
                parent=None,
                source=_error_source(error, self.script),
                started=moment,
                status="failed",
                error=self.mask(describe(error)),
                ended=moment,
            )
        )
        self._write_steps()

    @property
    def has_failed_step(self) -> bool:
        """有一步記成失敗。"""
        return any(step.status == "failed" for step in self._steps)

    def _write_steps(self) -> None:
        if self.steps_path is not None:
            _write_json(self.steps_path, [step.to_json() for step in self._steps])

    def write_facts(self) -> None:
        """寫出 facts.json：腳本自己寫過的保留，再加上 ``run.facts``。"""
        if self.facts_path is None:
            return
        existing = _json_file(str(self.facts_path)) if self.facts_path.exists() else None
        if existing is not None and not self.facts:
            return
        merged: dict[str, object] = {}
        if isinstance(existing, dict):
            merged.update(cast("dict[str, object]", existing))
        merged.update(self.facts)
        _write_json(self.facts_path, merged)


def describe(error: BaseException) -> str:
    """錯誤的一行說明：StepError 只有訊息，其他例外加上類型。"""
    if isinstance(error, StepError):
        return str(error)
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _caller_source(script: Path | None) -> str | None:
    """呼叫 run.step 的那一行：「檔名:行號」（只看場景自己的檔案）。"""
    frame = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
    root = script.resolve().parent if script is not None else None
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        if root is not None and _inside(path, root):
            return f"{path.resolve().relative_to(root).as_posix()}:{frame.f_lineno}"
        if root is None and "rpa_script" not in path.parts and "contextlib" not in path.name:
            return f"{path.name}:{frame.f_lineno}"
        frame = frame.f_back
    return None


def _error_source(error: BaseException, script: Path | None) -> str | None:
    root = script.resolve().parent if script is not None else None
    found: str | None = None
    tb: TracebackType | None = error.__traceback__
    while tb is not None:
        path = Path(tb.tb_frame.f_code.co_filename)
        if root is not None and _inside(path, root):
            found = f"{path.resolve().relative_to(root).as_posix()}:{tb.tb_lineno}"
        tb = tb.tb_next
    return found


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except (ValueError, OSError):
        return False
    return True


def _cell(value: object, mask: Callable[[str], str]) -> object:
    if value is None or isinstance(value, bool | int | float):
        if isinstance(value, float) and value != value:  # NaN
            return None
        return value
    shown = mask(str(value))
    return shown if len(shown) <= _PREVIEW_CELL else shown[: _PREVIEW_CELL - 1] + "…"


def _table(
    columns: Sequence[object],
    rows: Sequence[Sequence[object]],
    total: int | None,
    mask: Callable[[str], str],
) -> dict[str, object]:
    shown_columns = [mask(str(column)) for column in columns[:_PREVIEW_COLUMNS]]
    shown_rows = [
        [_cell(item, mask) for item in list(row)[:_PREVIEW_COLUMNS]] for row in rows[:_PREVIEW_ROWS]
    ]
    count = len(rows) if total is None else total
    return {
        "kind": "table",
        "columns": shown_columns,
        "rows": shown_rows,
        "rowCount": count,
        "columnCount": len(columns),
        "truncated": count > _PREVIEW_ROWS or len(columns) > _PREVIEW_COLUMNS,
    }


class _Values(Protocol):
    def tolist(self) -> list[list[object]]: ...


class _Frame(Protocol):
    """pandas.DataFrame 用到的部分。"""

    @property
    def columns(self) -> Sequence[object]: ...
    @property
    def values(self) -> _Values: ...
    def head(self, n: int) -> "_Frame": ...
    def __len__(self) -> int: ...


def _preview(value: object, mask: Callable[[str], str]) -> dict[str, object]:
    """資料預覽的內容：表格（DataFrame、list of dict、list of list）、JSON 或文字。"""
    if hasattr(value, "columns") and callable(getattr(value, "head", None)):
        frame = cast("_Frame", value)  # pandas.DataFrame（不 import pandas）
        rows = frame.head(_PREVIEW_ROWS).values.tolist()
        return _table(list(frame.columns), rows, len(frame), mask)
    items = cast("list[object]", value) if isinstance(value, list) else None
    if items and all(isinstance(item, dict) for item in items):
        records = cast("list[dict[str, object]]", items)
        names: list[str] = []
        for record in records[:_PREVIEW_ROWS]:
            names.extend(str(key) for key in record if str(key) not in names)
        rows = [[record.get(name) for name in names] for record in records]
        return _table(names, rows, None, mask)
    if items and all(isinstance(item, list | tuple) for item in items):
        lists = cast("list[Sequence[object]]", items)
        width = max(len(item) for item in lists[:_PREVIEW_ROWS])
        return _table([str(index + 1) for index in range(width)], lists, None, mask)
    if isinstance(value, dict | list | tuple):
        shown = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return {"kind": "json", "text": mask(shown[:20000])}
    return {"kind": "text", "text": mask(str(value)[:20000])}


MAX_SCANNED_FILES: Final = 2000
"""比較一步前後的檔案時，每個資料夾最多看幾個檔案。"""
MAX_LISTED_CHANGES: Final = 50
"""每一步的每種變化（新增、改變、刪除）最多列幾個檔案。"""
_SKIPPED_DIRS: Final = frozenset({".tmp", "__pycache__", ".outputs"})


def _file_changes(
    before: Mapping[str, tuple[int, int]], after: Mapping[str, tuple[int, int]]
) -> dict[str, list[str]]:
    """一步前後新增、改變、刪除的檔案（``workspace/…``、``outputs/…``）；沒有變化的種類不列。"""
    found = {
        "added": sorted(after.keys() - before.keys()),
        "changed": sorted(key for key in after.keys() & before.keys() if after[key] != before[key]),
        "removed": sorted(before.keys() - after.keys()),
    }
    return {kind: items[:MAX_LISTED_CHANGES] for kind, items in found.items() if items}


def _write_json(path: Path, data: object) -> None:
    """先寫暫存檔再改名：Runner 隨時讀都不會讀到寫到一半的內容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


# ---------------------------------------------------------------- 進入點與目前的執行

_CURRENT: list[Run] = []
_ENTRIES: list[Callable[[Run], object]] = []


def current() -> Run:
    """這次執行的 :class:`Run`；不是由啟動器執行時，依命令列與環境變數建立一個。"""
    if not _CURRENT:
        args: dict[str, str] = {}
        argv = sys.argv[1:]
        for index, item in enumerate(argv[:-1]):
            if item in ("--input", "--facts"):
                args[item[2:]] = argv[index + 1]
        if sys.argv and sys.argv[0]:
            args["script"] = sys.argv[0]
        _CURRENT.append(Run.from_environment(args))
    return _CURRENT[0]


def automation[F: Callable[[Run], object]](function: F) -> F:
    """標出腳本的進入點；啟動器執行完腳本後呼叫它，參數是這次的 :class:`Run`。"""
    if _ENTRIES:
        raise RuntimeError(text("two_entries"))
    _ENTRIES.append(function)
    return function


def registered() -> Callable[[Run], object] | None:
    """腳本用 ``@automation`` 標出的進入點；沒有時是 None。"""
    return _ENTRIES[0] if _ENTRIES else None


def activate(run: Run) -> None:
    """設定這次執行的 :class:`Run`（啟動器用）。"""
    _CURRENT.clear()
    _CURRENT.append(run)


class MaskedStream:
    """主控台輸出：寫出前遮罩 Secrets 的值（逐行寫出，Runner 讀 log 時看得到進度）。"""

    def __init__(self, target: TextIO, run: Run) -> None:
        self._target = target
        self._run = run

    def write(self, data: str) -> int:
        self._target.write(self._run.mask(data))
        return len(data)

    def flush(self) -> None:
        self._target.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._target, name)


def print_error(error: BaseException, script: Path | None) -> None:
    """失敗的說明寫到標準錯誤：StepError 只有訊息；其他例外加上場景自己的檔案那幾層呼叫堆疊。"""
    if isinstance(error, StepError):
        sys.stderr.write(f"{error}\n")
        return
    root = script.resolve().parent if script is not None else None
    frames = traceback.extract_tb(error.__traceback__)
    if root is not None:
        frames = traceback.StackSummary.from_list(
            [frame for frame in frames if _inside(Path(frame.filename), root)]
        )
    lines = ["Traceback (most recent call last):\n", *frames.format()]
    lines += traceback.format_exception_only(type(error), error)
    sys.stderr.write("".join(lines))
