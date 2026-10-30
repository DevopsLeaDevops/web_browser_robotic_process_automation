"""執行一個場景：入參校驗 →（登入檢查）→ 自動化（子程序）→ 獨立斷言 → 出參校驗與發布（ADR 0009）。

- 入參有問題時不啟動瀏覽器。
- 場景有 login 時，先用子程序 ``python -m rpa_runner.login check`` 確認角色已登入
  （必要時自動登入）；沒登入就停在 needs_login，不執行任何步驟。登入狀態檔不複製進執行目錄。
- 自動化在子程序執行：DSL 場景是 ``python -m rpa_runner.child``，Python 腳本場景是 automation.py。
  子程序超過總期限（加上短暫的收尾時間）就終止整個程序群組。
- 獨立斷言：DSL 場景與用 verify 的 Python 節點在本程序比對 verify；用 assertion.py 的
  Python 節點再啟動一個 assertion.py 子程序（ADR 0020）。
- 只有每個階段都通過，才寫出 output.json；任何失敗都沒有成功出參。
- 每次執行一個目錄（見 files.py），最後一定寫出 result.json 與 report.html。
- 可以從別的執行緒取消（``cancel``，例如管理介面的 worker）：立即終止程序群組，狀態為 cancelled。
- ``record_video`` 時 DSL 場景的自動化階段錄影（M12，見 video.py）：終止時讓錄影寫完
  （:func:`_stop_gracefully`），結束後整理成 video.webm 與 video.json。
- 運行環境模式的 Python 節點（``script.runtime``，ADR 0020）：自動化之前多一個 runtime 階段，
  準備 RPA Python 運行環境（見 pyruntime.py；準備的時間不算進總期限）。腳本由
  ``python -E -s -X utf8 -m rpa_script`` 啟動，工作目錄是共用工作資料夾（``workspace``，組合運行
  的節點共用；單獨執行時是執行目錄旁邊的暫存資料夾，結束就刪），產出檔案在執行目錄的 outputs/。
- 檔案入參（M7c）：入參階段把檔案準備在執行目錄旁邊的暫存資料夾（見 inputfiles.py），
  input.json 只有名稱、大小與 sha256；結束時刪掉暫存資料夾。場景附件不複製進執行目錄的快照，
  雜湊照場景資料夾裡的原檔計算。
"""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, cast

from rpa_core.dsl import Issue, Scenario, validate_file
from rpa_core.dsl.files import MAX_FILE_BYTES, MAX_RUN_BYTES
from rpa_core.dsl.sources import attachment_files, scenario_digest, scenario_sources
from rpa_core.i18n import ENV_VAR, get_locale
from rpa_runner.browser import Deadline
from rpa_runner.commands import module_command, no_window_flags, script_command
from rpa_runner.contract import (
    CheckResult,
    Problem,
    build_outputs,
    check_candidate_outputs,
    check_inputs,
    run_verify,
)
from rpa_runner.files import (
    ASSERTION_LOG,
    AUTOMATION_LOG,
    CANDIDATE,
    DIAGNOSTIC,
    FACTS,
    INPUT,
    LOGIN,
    LOGIN_LOG,
    OUTPUT,
    OUTPUTS_DIR,
    REPORT,
    RESULT,
    SCENARIO_DIR,
    SCREENSHOT,
    STEPS,
    VIDEO_TMP,
    read_json,
    read_json_or,
    write_json,
)
from rpa_runner.i18n import t
from rpa_runner.inputfiles import (
    PATHS_FILE,
    FileSources,
    env_folders,
    prepare_files,
    remove_staging,
)
from rpa_runner.installed import missing_browser_hint
from rpa_runner.login import ENV_LOGIN, EXIT_NEEDS_LOGIN, LoginSettings
from rpa_runner.proctree import descendants, terminate, wait_exit
from rpa_runner.pyruntime import (
    PreparedRuntime,
    RuntimeUnavailableError,
    clean_environment,
    platform_family,
    platform_tag,
    script_library,
)
from rpa_runner.pyruntime import prepare as prepare_runtime
from rpa_runner.report import render_report
from rpa_runner.secrets import mask, missing_secrets, read_secrets
from rpa_runner.video import VIDEO_STOP
from rpa_runner.video import finalize as finalize_video

# scenario_digest、scenario_sources 在 rpa-core（領域資料夾的校驗也要用，M11），這裡照舊匯出
__all__ = [
    "DEFAULT_DEADLINE_MS",
    "RunResult",
    "RunStatus",
    "ScenarioInvalidError",
    "Stage",
    "StageName",
    "execute",
    "new_run_id",
    "scenario_digest",
    "scenario_sources",
]

DEFAULT_DEADLINE_MS: Final = 120_000
"""場景沒有寫 deadline 時的總期限。"""
_GRACE_SECONDS: Final = 3.0
"""子程序在總期限後還有這麼多秒可以寫診斷與截圖，之後就被終止。"""
_VIDEO_GRACE_SECONDS: Final = 6.0
"""錄影時的收尾時間（多了關 context、把影片寫完）。"""
_GRACEFUL_STOP_SECONDS: Final = 8.0
"""Windows 上錄影時被終止：子程序結束後，最多再等錄影的 ffmpeg 這麼久把影片寫完。"""
_BROWSER_STOP_SECONDS: Final = 15.0
"""Windows 上錄影時被終止：結束瀏覽器後，最多等子程序這麼久自己結束。"""
_KEEP_RUNNING: Final = ("python", "node", "ffmpeg", "conhost")
"""Windows 上錄影時被終止：先不結束的程序（執行檔名稱的開頭，小寫）；其餘的是瀏覽器。"""
_EXIT_DEADLINE: Final = 3
_POLL_SECONDS: Final = 0.2
"""等待子程序時，每隔這麼久檢查一次是否被取消。"""
_LOG_TAIL_BYTES: Final = 64 * 1024
"""自動化失敗時，讀日誌最後這麼多位元組，找「瀏覽器還沒下載」的錯誤。"""

RunStatus = Literal["passed", "failed", "timed_out", "cancelled", "needs_login"]
StageName = Literal["input", "login", "runtime", "automation", "verify", "output"]
StageStatus = Literal["passed", "failed", "timed_out", "cancelled", "needs_login", "skipped"]
ENV_STORAGE_STATE: Final = "RPA_STORAGE_STATE"
"""Python 腳本場景從這個環境變數得知登入狀態檔（場景有 login 時）。"""


class ScenarioInvalidError(Exception):
    """場景檔沒有通過校驗，不能執行。"""

    def __init__(self, issues: Sequence[Issue]) -> None:
        super().__init__(f"{len(issues)} issue(s)")
        self.issues = tuple(issues)


@dataclass(slots=True)
class Stage:
    name: StageName
    status: StageStatus = "skipped"
    message: str | None = None
    duration_ms: int = 0

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "durationMs": self.duration_ms,
        }


@dataclass(slots=True)
class RunResult:
    """一次執行的結果，寫進 result.json。"""

    run_id: str
    scenario_id: str
    scenario_name: str
    scenario_hash: str
    kind: Literal["dsl", "script"]
    engine: str
    directory: Path
    started_at: str
    status: RunStatus = "failed"
    duration_seconds: float = 0.0
    input: dict[str, object] = field(default_factory=dict[str, object])
    output: dict[str, object] | None = None
    stages: list[Stage] = field(default_factory=list[Stage])
    steps: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    checks: list[CheckResult] = field(default_factory=list[CheckResult])
    problems: list[str] = field(default_factory=list[str])
    error: str | None = None
    role: str | None = None
    """以哪個角色登入（場景的 login.role）。"""
    login: dict[str, object] | None = None
    """登入檢查的結果（login.json）。"""
    python: dict[str, object] | None = None
    """Python 節點（ADR 0020）：模式（compatible／runtime）、運行環境版本、平台、沿用或新解壓。"""

    def stage(self, name: StageName) -> Stage:
        return next(stage for stage in self.stages if stage.name == name)

    @property
    def files(self) -> list[str]:
        return sorted(
            path.relative_to(self.directory).as_posix()
            for path in self.directory.rglob("*")
            if path.is_file() and path.name not in (REPORT,)
        )

    def to_json(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "scenarioId": self.scenario_id,
            "scenarioName": self.scenario_name,
            "scenarioHash": self.scenario_hash,
            "kind": self.kind,
            "engine": self.engine,
            "status": self.status,
            "startedAt": self.started_at,
            "durationSeconds": self.duration_seconds,
            "input": self.input,
            "output": self.output,
            "stages": [stage.to_json() for stage in self.stages],
            "steps": self.steps,
            "checks": [
                {
                    "name": check.name,
                    "comparison": check.comparison,
                    "actual": check.actual,
                    "expected": check.expected,
                    "passed": check.passed,
                    "error": check.error,
                }
                for check in self.checks
            ],
            "problems": self.problems,
            "error": self.error,
            "role": self.role,
            "login": self.login,
            "python": self.python,
        }


# ---------------------------------------------------------------- 子程序


class _StageFailedError(Exception):
    def __init__(self, status: StageStatus, message: str) -> None:
        super().__init__(message)
        self.status: StageStatus = status
        self.message: str = message


def _stop(process: subprocess.Popen[bytes], *, graceful: Path | None = None) -> None:
    """終止子程序與它開出的瀏覽器（整個程序群組）。

    ``graceful`` 是錄影時記錄終止經過的檔案（見 :func:`_stop_gracefully`）。
    """
    if graceful is not None:
        _stop_gracefully(process, graceful)
        return
    if os.name == "nt":  # pragma: no cover - Windows 在 CI 的安裝腳本測試涵蓋
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
            creationflags=no_window_flags(),
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def _stop_gracefully(process: subprocess.Popen[bytes], record: Path) -> None:
    """錄影時的終止：結束子程序與瀏覽器，但讓錄影的 ffmpeg 把影片寫完。

    其他系統和平常一樣終止程序群組就好：Playwright 把瀏覽器與 ffmpeg 放在自己的程序群組，
    不會被一起結束；ffmpeg 發現輸入斷了就自己收尾。Windows 見 :func:`_stop_browsers_first`。
    終止的經過寫在 ``record``（錄影的暫存資料夾裡），整理影片時放進 video.json，影片有問題時
    才查得到原因。
    """
    started = time.monotonic()
    details: dict[str, object]
    if os.name == "nt":  # pragma: no cover - Windows 在 CI 的 Worker 測試涵蓋
        details = _stop_browsers_first(process)
    else:
        _stop(process)
        details = {"method": "process_group"}
    details["stopMs"] = round((time.monotonic() - started) * 1000)
    with contextlib.suppress(OSError):
        record.parent.mkdir(parents=True, exist_ok=True)
        write_json(record, details)


def _stop_browsers_first(  # pragma: no cover - Windows
    process: subprocess.Popen[bytes],
) -> dict[str, object]:
    """Windows：先只結束瀏覽器，讓 Playwright 自己把錄影寫完，子程序隨後自己結束。

    不能直接結束 Node（Playwright 的 driver）：libuv 把 Node 開的子程序放進「Node 結束時一起結束」
    的 Job Object，ffmpeg 會跟著被結束，緩衝區還沒寫進檔案，影片是空的（2026-10-21 在 CI 實測：
    只留下 ffmpeg、結束其他程序，ffmpeg 6～11 ms 後也結束了）。瀏覽器結束時，Playwright 照常替
    每個頁面收尾錄影（補最後一格、關掉 ffmpeg 的輸入、等它寫完）；子程序的步驟因為頁面關了而失敗，
    自己結束。最多等一陣子，子程序還沒結束才結束整個程序樹（這時影片可能沒寫完，整理時再修復）。
    還沒開瀏覽器時（沒有錄影要保護）照平常的方式立即終止。回傳終止的經過。
    """
    try:
        tree = descendants(process.pid)
    except OSError as error:
        _stop(process)
        return {"method": "taskkill", "error": str(error)}
    names = sorted({item.name for item in tree})
    browsers = [item for item in tree if not item.name.lower().startswith(_KEEP_RUNNING)]
    if not browsers:
        _stop(process)
        return {"method": "taskkill", "processes": names}
    for item in browsers:
        terminate(item.pid)
    started = time.monotonic()
    try:
        process.wait(timeout=_BROWSER_STOP_SECONDS)
    except subprocess.TimeoutExpired:
        _stop(process)
        return {
            "method": "browsers_then_taskkill",
            "processes": names,
            "browsers": len(browsers),
        }
    exited = round((time.monotonic() - started) * 1000)
    ffmpeg = [item.pid for item in tree if item.name.lower().startswith("ffmpeg")]
    left = wait_exit(ffmpeg, _GRACEFUL_STOP_SECONDS)
    for pid in left:
        terminate(pid)
    return {
        "method": "browsers_first",
        "processes": names,
        "browsers": len(browsers),
        "childExitedMs": exited,
        "ffmpegKilled": len(left),
    }


def _remove_leftover(path: Path, *, attempts: int = 30, delay: float = 0.1) -> None:
    """刪掉子程序留下的暫存檔。

    Windows 上 taskkill 回來時，程序樹裡剛被結束的程序可能還占著檔案（WinError 32），
    稍等重試；一直刪不掉就留著（只是一個暫存檔，不影響結果）。
    """
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            if attempt == attempts - 1:
                return
            time.sleep(delay)
        else:
            return


def _check_cancelled(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise _StageFailedError("cancelled", t("run.cancelled"))


def _wait(
    process: subprocess.Popen[bytes],
    seconds: float,
    cancel: threading.Event | None,
    *,
    graceful: Path | None = None,
) -> int:
    """等子程序結束；超過 seconds 或被取消時終止整個程序群組。"""
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        try:
            return process.wait(timeout=max(0.0, min(_POLL_SECONDS, left)))
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                _stop(process, graceful=graceful)
                raise _StageFailedError("cancelled", t("run.cancelled")) from None
            if left <= 0:
                _stop(process, graceful=graceful)
                raise _StageFailedError("timed_out", t("run.deadline_killed")) from None


def _log_tail(log: Path, size: int = _LOG_TAIL_BYTES) -> str:
    """日誌的最後 size 位元組（腳本可能印很多東西，錯誤在最後面）；讀不到時回傳空字串。"""
    try:
        with log.open("rb") as file:
            file.seek(max(0, log.stat().st_size - size))
            return file.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _run_process(
    command: Sequence[str],
    log: Path,
    deadline: Deadline,
    env: Mapping[str, str],
    cancel: threading.Event | None = None,
    special: Mapping[int, _StageFailedError] | None = None,
    *,
    video: Path | None = None,
    cwd: Path | None = None,
) -> None:
    """執行子程序直到結束；``special`` 是有特別意義的結束碼（例如需要登入）。

    ``video`` 是錄影時記錄終止經過的檔案：子程序在錄影，收尾時間長一點，終止時先讓錄影寫完。
    """
    _check_cancelled(cancel)
    remaining = deadline.remaining_ms() / 1000
    if remaining <= 0:
        raise _StageFailedError("timed_out", t("run.deadline_before_stage"))
    with log.open("wb") as output:
        process = subprocess.Popen(
            list(command),
            stdout=output,
            stderr=subprocess.STDOUT,
            env=dict(env),
            start_new_session=os.name != "nt",
            creationflags=no_window_flags(),
            cwd=cwd,
        )
        grace = _VIDEO_GRACE_SECONDS if video is not None else _GRACE_SECONDS
        try:
            code = _wait(process, remaining + grace, cancel, graceful=video)
        except _StageFailedError:
            raise
        except BaseException:
            _stop(process, graceful=video)
            raise
    if code == _EXIT_DEADLINE:
        raise _StageFailedError("timed_out", t("run.deadline_in_stage"))
    if special and code in special:
        raise special[code]
    if code != 0:
        raise _StageFailedError("failed", t("run.process_failed", code=code, log=log.name))


# ---------------------------------------------------------------- 執行


def new_run_id(scenario_id: str, now: datetime | None = None) -> str:
    """執行編號：``<場景 id>-<UTC 日期>-<時間>-<6 碼亂數>``，同時是執行目錄的名稱。"""
    moment = now or datetime.now(UTC)
    return f"{scenario_id}-{moment:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _snapshot(path: Path, scenario: Scenario, folder: Path) -> tuple[Path, str]:
    """把場景檔（與腳本）複製進執行目錄，回傳 (快照路徑, 雜湊)。

    場景附件（M7c）不複製：執行目錄會上傳回伺服器、一直保留，附件每次都一樣；
    雜湊照場景資料夾裡的原檔計算（同一組位元組，結果相同）。
    """
    target = folder / SCENARIO_DIR
    target.mkdir()
    attachments = set(attachment_files(path.parent))
    for relative in scenario_sources(path, scenario):
        if relative in attachments:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path.parent / relative, destination)
    snapshot = target / path.name
    return snapshot, scenario_digest(path, scenario)


def _environment(
    secrets: Mapping[str, str],
    deadline: Deadline,
    engine: str | None = None,
    headed: bool | None = None,
    storage_state: Path | None = None,
) -> dict[str, str]:
    """子程序的環境變數：Secrets、剩餘秒數 RPA_DEADLINE_SECONDS、瀏覽器 RPA_BROWSER。

    另外用 RPA_LANG 傳入目前的語言，子程序的日誌與它一致；自動化階段再用 RPA_HEADLESS
    （1 無頭、0 有頭）告訴 Python 腳本要不要顯示瀏覽器視窗，RPA_STORAGE_STATE 告訴它登入狀態檔。
    """
    env = {**os.environ, **secrets, "PYTHONIOENCODING": "utf-8", ENV_VAR: get_locale()}
    env["RPA_DEADLINE_SECONDS"] = f"{max(0, deadline.remaining_ms()) / 1000:.3f}"
    if engine:
        env["RPA_BROWSER"] = engine
    if headed is not None:
        env["RPA_HEADLESS"] = "0" if headed else "1"
    env.pop(ENV_STORAGE_STATE, None)
    env.pop(ENV_LOGIN, None)
    if storage_state is not None:
        env[ENV_STORAGE_STATE] = str(storage_state)
    return env


def execute(
    path: Path,
    inputs: Mapping[str, object],
    *,
    out_root: Path,
    base_url: str | None = None,
    engine: str | None = None,
    headed: bool = False,
    deadline_ms: int | None = None,
    run_id: str | None = None,
    cancel: threading.Event | None = None,
    on_stage: Callable[[StageName], None] | None = None,
    login: LoginSettings | None = None,
    secrets: Mapping[str, str] | None = None,
    record_video: bool = False,
    uploads: Mapping[str, Path] | None = None,
    input_folders: Sequence[Path] | None = None,
    any_path: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_run_bytes: int = MAX_RUN_BYTES,
    workspace: Path | None = None,
) -> RunResult:
    """執行場景檔，回傳結果；場景本身沒通過校驗時拋出 ScenarioInvalidError。

    - ``run_id``：指定執行編號（例如管理介面排入佇列時就決定好）；沒指定時用 :func:`new_run_id`。
    - ``cancel``：別的執行緒設定這個事件就取消執行。
    - ``on_stage``：每個階段開始時呼叫，用來回報進度。
    - ``login``：場景有 login 時，這個角色的登入設定（管理 Portal 登記的角色）。
    - ``secrets``：Secrets 的值（例如管理 Portal 保存的）；沒有的再從同名的環境變數找。
    - ``record_video``：自動化階段錄影（M12；只有 DSL 場景，Python 腳本場景不錄）。
    - 檔案入參（M7c）：``uploads`` 是上傳檔代號 → 這台電腦上的檔案；``path`` 值只能在
      ``input_folders`` 裡（沒給時用環境變數 RPA_INPUT_FOLDERS），``any_path`` 時不限（命令列）；
      ``max_file_bytes``、``max_run_bytes`` 是單檔與合計的上限。
    - ``workspace``：組合運行的共用工作資料夾（ADR 0020）；沒給時 Python 節點用執行目錄旁邊的
      暫存資料夾，結束就刪除。
    """
    validated = validate_file(path)
    if validated.scenario is None:
        raise ScenarioInvalidError(validated.issues)
    scenario = validated.scenario
    started = time.monotonic()
    now = datetime.now(UTC)
    run_id = run_id or new_run_id(scenario.id, now)
    folder = out_root / run_id
    folder.mkdir(parents=True)
    staging = out_root / f".files-{run_id}"
    # 組合運行的共用工作資料夾也算允許的資料夾：上一個節點下載、產出的檔案可以當 path 入參
    shared = (workspace,) if workspace is not None else ()
    sources = FileSources(
        scenario_dir=path.parent,
        uploads=uploads or {},
        folders=None
        if any_path
        else (*(input_folders if input_folders is not None else env_folders()), *shared),
        max_file=max_file_bytes,
        max_total=max_run_bytes,
    )
    snapshot, digest = _snapshot(path, scenario, folder)
    script = scenario.script
    uses_runtime = script is not None and script.uses_runtime
    own_workspace = uses_runtime and workspace is None
    work = workspace if workspace is not None else out_root / f".work-{run_id}"
    result = RunResult(
        run_id=run_id,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        scenario_hash=digest,
        kind="script" if scenario.script is not None else "dsl",
        engine=engine or scenario.browser.engine,
        directory=folder,
        started_at=now.isoformat(timespec="seconds"),
        stages=[
            Stage("input"),
            *([Stage("login")] if scenario.login is not None else []),
            *([Stage("runtime")] if uses_runtime else []),
            Stage("automation"),
            Stage("verify"),
            Stage("output"),
        ],
        role=scenario.login.role if scenario.login is not None else None,
        python=None if script is None else {"mode": "runtime" if uses_runtime else "compatible"},
    )
    environ = {**os.environ, **(secrets or {})}
    login_secrets = {
        name: environ[name] for name in (login.secrets if login else ()) if name in environ
    }
    secrets = read_secrets(scenario, environ)
    video = record_video and scenario.script is None
    deadline = Deadline.after((deadline_ms or scenario.deadline or DEFAULT_DEADLINE_MS) / 1000)
    current: Stage = result.stage("input")

    def enter(name: StageName) -> None:
        nonlocal current
        current = result.stage(name)
        _check_cancelled(cancel)
        if on_stage is not None:
            on_stage(name)

    node: _PythonNode | None = None
    try:
        enter("input")
        _input_stage(scenario, inputs, result, folder, environ, sources, staging)
        state: Path | None = None
        if scenario.login is not None:
            enter("login")
            state = _login_stage(
                folder,
                deadline,
                login_secrets,
                engine or scenario.browser.engine,
                login,
                cancel,
                result,
            )
        if uses_runtime:
            enter("runtime")
            node, deadline = _runtime_stage(scenario, result, deadline, work, folder, staging)
        enter("automation")
        _automation_stage(
            scenario,
            snapshot,
            folder,
            deadline,
            secrets,
            base_url,
            engine,
            headed,
            cancel,
            result,
            state,
            video=video,
            files=staging / PATHS_FILE,
            node=node,
        )
        enter("verify")
        _verify_stage(scenario, snapshot, folder, deadline, secrets, cancel, result, node)
        enter("output")
        _output_stage(scenario, folder, deadline, secrets, result)
        result.status = "passed"
    except _StageFailedError as failure:
        current.status = failure.status
        current.message = mask(failure.message, secrets)
        result.status = (
            failure.status
            if failure.status in ("timed_out", "cancelled", "needs_login")
            else "failed"
        )
        # 子程序寫在 diagnostic.json 的錯誤（例如找不到元素）比階段說明更具體，一併保留
        detail = result.error if failure.status not in ("cancelled", "needs_login") else None
        result.error = f"{current.message}；{detail}" if detail else current.message
    except KeyboardInterrupt:
        current.status = "cancelled"
        current.message = t("run.cancelled")
        result.status = "cancelled"
        result.error = current.message
    finally:
        remove_staging(staging)
        if own_workspace:
            shutil.rmtree(work, ignore_errors=True)
        if video:
            finalize_video(folder, engine=result.engine)
        (folder / CANDIDATE).unlink(missing_ok=True)
        for leftover in folder.glob(".*.tmp"):  # 子程序寫到一半被終止時留下的暫存檔
            _remove_leftover(leftover)
        if result.status != "passed":
            (folder / OUTPUT).unlink(missing_ok=True)
            result.output = None
        steps = read_json_or(folder / STEPS, [])
        if isinstance(steps, list):
            result.steps = cast("list[dict[str, object]]", steps)
        result.duration_seconds = round(time.monotonic() - started, 3)
        write_json(folder / RESULT, result.to_json())
        (folder / REPORT).write_text(render_report(result), encoding="utf-8")
    return result


def _timed(stage: Stage, started: float) -> None:
    stage.duration_ms = int((time.monotonic() - started) * 1000)


def _input_stage(
    scenario: Scenario,
    inputs: Mapping[str, object],
    result: RunResult,
    folder: Path,
    environ: Mapping[str, str],
    sources: FileSources,
    staging: Path,
) -> None:
    started = time.monotonic()
    resolved, problems = check_inputs(scenario, inputs)
    if not problems and any(spec.type == "file" for spec in scenario.inputs.values()):
        prepared = prepare_files(scenario, resolved, sources, staging)
        resolved.update(prepared.meta)
        problems += prepared.problems
    problems += [
        Problem(name, t("contract.secret_missing", name=name))
        for name in missing_secrets(scenario, environ)
    ]
    result.input = resolved
    write_json(folder / INPUT, resolved)
    _timed(result.stage("input"), started)
    if problems:
        result.problems = [problem.message for problem in problems]
        key = "run.input_failed_script" if scenario.script is not None else "run.input_failed"
        raise _StageFailedError("failed", t(key, count=len(problems)))
    result.stage("input").status = "passed"


def _login_stage(
    folder: Path,
    deadline: Deadline,
    secrets: Mapping[str, str],
    engine: str,
    login: LoginSettings | None,
    cancel: threading.Event | None,
    result: RunResult,
) -> Path:
    """確認角色已登入（必要時自動登入），回傳要給自動化載入的登入狀態檔。"""
    started = time.monotonic()
    stage = result.stage("login")
    try:
        if login is None:
            raise _StageFailedError("failed", t("run.login_missing", role=result.role or "?"))
        if login.check_url is None:
            # 只給了登入狀態檔（例如命令列 --storage-state）：直接載入，不檢查
            if not login.state.is_file():
                raise _StageFailedError("failed", t("run.login_state_missing", role=login.label))
            stage.status = "passed"
            stage.message = t("run.login_not_checked")
            return login.state
        missing = [name for name in login.secrets if name not in secrets]
        if missing:
            raise _StageFailedError(
                "failed", t("run.login_secret_missing", role=login.label, names=", ".join(missing))
            )
        command = module_command(
            "rpa_runner.login",
            [
                "check",
                "--out",
                str(folder),
                "--deadline",
                f"{max(0, deadline.remaining_ms()) / 1000:.3f}",
                "--engine",
                engine,
            ],
        )
        env = _environment(secrets, deadline, engine)
        env[ENV_LOGIN] = json.dumps(login.to_json(), ensure_ascii=False)
        needs = _StageFailedError("needs_login", t("run.needs_login", role=login.label))
        _run_process(
            command, folder / LOGIN_LOG, deadline, env, cancel, special={EXIT_NEEDS_LOGIN: needs}
        )
    finally:
        _timed(stage, started)
        details = read_json_or(folder / LOGIN, None)
        if isinstance(details, dict):
            result.login = cast("dict[str, object]", details)
            error = result.login.get("error")
            if error:
                result.error = mask(str(error), secrets)
    stage.status = "passed"
    if result.login is not None and result.login.get("refreshed"):
        stage.message = t("run.login_refreshed", role=login.label)
    return login.state


_LAUNCHER: Final = (
    "import runpy, sys; sys.path.append(sys.argv.pop(1)); "
    "runpy.run_module('rpa_script', run_name='__main__', alter_sys=True)"
)
"""運行環境模式的自動化：把 Runner 的 rpa_script 加在 import 路徑最後，再執行它的啟動器
（等於 ``python -m rpa_script 腳本 參數…``）。"""


@dataclass(frozen=True, slots=True)
class _PythonNode:
    """運行環境模式的 Python 節點這次執行要用的：運行環境、共用工作資料夾、產出檔案、file 入參。"""

    runtime: PreparedRuntime
    library: Path
    """Runner 的 rpa_script 所在的資料夾（:func:`rpa_runner.pyruntime.script_library`）。"""
    workspace: Path
    outputs: Path
    input_files: Path | None

    def command(self, script: Path, args: Sequence[str], *, launcher: bool) -> list[str]:
        """運行環境的 Python 執行腳本：自動化經由 rpa_script 的啟動器，斷言直接執行。"""
        # -E -s：不讀 PYTHON* 環境變數與使用者的 site-packages；-B：不在快照裡寫 __pycache__
        base = [str(self.runtime.python), "-E", "-s", "-B", "-X", "utf8"]
        if launcher:
            return [*base, "-c", _LAUNCHER, str(self.library), str(script), *args]
        return [*base, str(script), *args]

    def environment(
        self, scenario: Scenario, secrets: Mapping[str, str], deadline: Deadline, folder: Path
    ) -> dict[str, str]:
        """子程序的環境：拿掉會影響 Python 的變數，加上 Python 節點的 RPA_* 與這次的 Secrets。"""
        env = clean_environment({**os.environ, **secrets}, keep=list(secrets))
        env.pop(ENV_STORAGE_STATE, None)
        env.pop(ENV_LOGIN, None)
        tmp = self.workspace / ".tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        env.update(
            {
                ENV_VAR: get_locale(),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "RPA_DEADLINE_SECONDS": f"{max(0, deadline.remaining_ms()) / 1000:.3f}",
                "RPA_WORKSPACE": str(self.workspace),
                "RPA_OUTPUT_DIR": str(self.outputs),
                "RPA_STEPS": str(folder / STEPS),
                "RPA_RUNTIME": self.runtime.version,
                "RPA_PLATFORM": self.runtime.platform,
                "RPA_SECRET_NAMES": json.dumps(list(scenario.secrets)),
                "TMPDIR": str(tmp),
                "TEMP": str(tmp),
                "TMP": str(tmp),
            }
        )
        if self.input_files is not None:
            env["RPA_INPUT_FILES"] = str(self.input_files)
        return env


def _runtime_stage(
    scenario: Scenario,
    result: RunResult,
    deadline: Deadline,
    workspace: Path,
    folder: Path,
    staging: Path,
) -> tuple[_PythonNode, Deadline]:
    """準備 RPA Python 運行環境（ADR 0020）。準備的時間不算進總期限：回傳順延後的期限。"""
    started = time.monotonic()
    stage = result.stage("runtime")
    script = scenario.script
    assert script is not None
    assert script.runtime is not None
    platforms = script.platforms
    tag = platform_tag()
    try:
        if platforms is not None and platform_family(tag) not in platforms:
            raise _StageFailedError(
                "failed", t("run.runtime_platform", platform=tag, platforms=", ".join(platforms))
            )
        try:
            runtime = prepare_runtime(script.runtime)
            library = script_library()
        except RuntimeUnavailableError as error:
            raise _StageFailedError(
                "failed", t("run.runtime_failed", major=script.runtime, detail=str(error))
            ) from error
    finally:
        _timed(stage, started)
    result.python = {"mode": "runtime", **runtime.to_json()}
    key = "run.runtime_reused" if runtime.reused else "run.runtime_prepared"
    stage.message = t(key, version=runtime.version, ms=runtime.prepared_ms)
    stage.status = "passed"
    workspace.mkdir(parents=True, exist_ok=True)
    outputs = folder / OUTPUTS_DIR
    outputs.mkdir(exist_ok=True)
    paths = staging / PATHS_FILE
    node = _PythonNode(runtime, library, workspace, outputs, paths if paths.is_file() else None)
    spent = time.monotonic() - started
    return node, Deadline(deadline.expires_at + spent)


def _automation_stage(
    scenario: Scenario,
    snapshot: Path,
    folder: Path,
    deadline: Deadline,
    secrets: Mapping[str, str],
    base_url: str | None,
    engine: str | None,
    headed: bool,
    cancel: threading.Event | None,
    result: RunResult,
    state: Path | None = None,
    *,
    video: bool = False,
    files: Path | None = None,
    node: _PythonNode | None = None,
) -> None:
    started = time.monotonic()
    stage = result.stage("automation")
    # 運行環境模式不開瀏覽器：沒有起始網址
    url = None if node is not None else base_url or scenario.browser.base_url
    arguments = [
        "--input",
        str(folder / INPUT),
        "--facts",
        str(folder / FACTS),
        "--screenshot",
        str(folder / SCREENSHOT),
        "--target-url",
        url or "",
    ]
    if node is not None and scenario.script is not None:
        script = snapshot.parent / scenario.script.automation
        command = node.command(script, arguments, launcher=True)
    elif scenario.script is not None:
        command = script_command(str(snapshot.parent / scenario.script.automation), arguments)
    else:
        command = module_command(
            "rpa_runner.child",
            [
                "--scenario",
                str(snapshot),
                "--input",
                str(folder / INPUT),
                "--out",
                str(folder),
                "--deadline",
                f"{max(0, deadline.remaining_ms()) / 1000:.3f}",
            ],
        )
        command += ["--engine", engine] if engine else []
        command += ["--base-url", base_url] if base_url else []
        command += ["--headed"] if headed else []
        command += ["--storage-state", str(state)] if state is not None else []
        command += ["--video"] if video else []
        command += ["--files", str(files)] if files is not None and files.is_file() else []
    hint: str | None = None
    record = folder / VIDEO_TMP / VIDEO_STOP if video else None
    try:
        if node is not None:
            env = node.environment(scenario, secrets, deadline, folder)
            _run_process(
                command, folder / AUTOMATION_LOG, deadline, env, cancel, cwd=node.workspace
            )
        else:
            env = _environment(secrets, deadline, engine or scenario.browser.engine, headed, state)
            _run_process(command, folder / AUTOMATION_LOG, deadline, env, cancel, video=record)
    except _StageFailedError as failure:
        # 瀏覽器還沒下載：DSL 場景與 Python 腳本場景都會把 Playwright 的錯誤印進日誌
        if failure.status == "failed":
            hint = missing_browser_hint(_log_tail(folder / AUTOMATION_LOG))
        if hint is None:
            raise
    finally:
        _timed(stage, started)
        details = read_json_or(folder / DIAGNOSTIC, None)
        # 錄影時被我們終止：子程序是因為瀏覽器被結束才失敗的（Windows 先結束瀏覽器），
        # 它寫的「頁面已關閉」不是真正的原因，不採用
        stopped = record is not None and record.is_file()
        if hint is None and not stopped and isinstance(details, dict):
            error = cast("dict[str, object]", details).get("error", "")
            result.error = mask(str(error), secrets) or None
        elif scenario.script is not None:
            result.error = _failed_step(folder, secrets) or result.error
    if hint is not None:
        # 不附上子程序結束碼與英文提示框，只說怎麼修；原始錯誤仍在 automation.log
        raise _StageFailedError("failed", hint)
    if not (folder / FACTS).exists():
        raise _StageFailedError("failed", t("run.facts_missing"))
    stage.status = "passed"


def _failed_step(folder: Path, secrets: Mapping[str, str]) -> str | None:
    """Python 節點用 rpa_script 記了步驟時：失敗的那一步與錯誤（給報告的錯誤摘要）。"""
    steps = read_json_or(folder / STEPS, [])
    if not isinstance(steps, list):
        return None
    for item in reversed(cast("list[object]", steps)):
        if isinstance(item, dict):
            step = cast("dict[str, object]", item)
            if step.get("status") == "failed" and step.get("error"):
                label = step.get("name") or step.get("id")
                return mask(f"{label}：{step['error']}", secrets)
    return None


def _verify_stage(
    scenario: Scenario,
    snapshot: Path,
    folder: Path,
    deadline: Deadline,
    secrets: Mapping[str, str],
    cancel: threading.Event | None,
    result: RunResult,
    node: _PythonNode | None = None,
) -> None:
    started = time.monotonic()
    stage = result.stage("verify")
    if scenario.script is not None and scenario.script.assertion is not None:
        arguments = [
            "--input",
            str(folder / INPUT),
            "--facts",
            str(folder / FACTS),
            "--output",
            str(folder / CANDIDATE),
        ]
        assertion = snapshot.parent / scenario.script.assertion
        try:
            if node is not None:
                command = node.command(assertion, arguments, launcher=False)
                env = node.environment(scenario, secrets, deadline, folder)
                _run_process(
                    command, folder / ASSERTION_LOG, deadline, env, cancel, cwd=node.workspace
                )
            else:
                command = script_command(str(assertion), arguments)
                env = _environment(secrets, deadline)
                _run_process(command, folder / ASSERTION_LOG, deadline, env, cancel)
        finally:
            _timed(stage, started)
        stage.status = "passed"
        return
    if not scenario.verify:
        _timed(stage, started)
        return
    context = {
        "inputs": result.input,
        "secrets": secrets,
        "facts": read_json(folder / FACTS),
        "env": dict(os.environ),
    }
    result.checks = run_verify(scenario, context)
    _timed(stage, started)
    failed = [check for check in result.checks if not check.passed]
    if failed:
        raise _StageFailedError(
            "failed", t("run.verify_failed", count=len(failed), name=failed[0].name)
        )
    stage.status = "passed"


def _output_stage(
    scenario: Scenario,
    folder: Path,
    deadline: Deadline,
    secrets: Mapping[str, str],
    result: RunResult,
) -> None:
    started = time.monotonic()
    stage = result.stage("output")
    if scenario.script is not None and scenario.script.assertion is not None:
        candidate = folder / CANDIDATE
        if not candidate.exists():
            raise _StageFailedError("failed", t("run.candidate_missing"))
        outputs = cast("dict[str, object]", read_json(candidate))
        problems = check_candidate_outputs(scenario, outputs)
    else:
        context = {
            "inputs": result.input,
            "secrets": secrets,
            "facts": read_json(folder / FACTS),
            "env": dict(os.environ),
        }
        outputs, problems = build_outputs(scenario, context)
    _timed(stage, started)
    if problems:
        result.problems = [problem.message for problem in problems]
        raise _StageFailedError("failed", t("run.output_failed", count=len(problems)))
    if deadline.remaining_ms() <= 0:
        raise _StageFailedError("timed_out", t("run.deadline_before_publish"))
    write_json(folder / OUTPUT, outputs)
    result.output = outputs
    stage.status = "passed" if scenario.outputs else "skipped"
