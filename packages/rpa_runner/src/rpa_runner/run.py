"""執行一個場景：入參校驗 → 自動化（子程序）→ 獨立斷言 → 出參校驗與發布（ADR 0009）。

- 入參有問題時不啟動瀏覽器。
- 自動化在子程序執行：DSL 場景是 ``python -m rpa_runner.child``，Python 腳本場景是 automation.py。
  子程序超過總期限（加上短暫的收尾時間）就終止整個程序群組。
- 獨立斷言：DSL 場景在本程序比對 verify；腳本場景再啟動一個 assertion.py 子程序。
- 只有每個階段都通過，才寫出 output.json；任何失敗都沒有成功出參。
- 每次執行一個目錄（見 files.py），最後一定寫出 result.json 與 report.html。
- 可以從別的執行緒取消（``cancel``，例如管理介面的 worker）：立即終止程序群組，狀態為 cancelled。
"""

import contextlib
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, cast

from rpa_core.dsl import Issue, Scenario, validate_file
from rpa_runner.browser import Deadline
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
    OUTPUT,
    REPORT,
    RESULT,
    SCENARIO_DIR,
    SCREENSHOT,
    STEPS,
    read_json,
    read_json_or,
    write_json,
)
from rpa_runner.i18n import t
from rpa_runner.report import render_report
from rpa_runner.secrets import mask, missing_secrets, read_secrets

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
_EXIT_DEADLINE: Final = 3
_POLL_SECONDS: Final = 0.2
"""等待子程序時，每隔這麼久檢查一次是否被取消。"""

RunStatus = Literal["passed", "failed", "timed_out", "cancelled"]
StageName = Literal["input", "automation", "verify", "output"]
StageStatus = Literal["passed", "failed", "timed_out", "cancelled", "skipped"]


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
        }


# ---------------------------------------------------------------- 子程序


class _StageFailedError(Exception):
    def __init__(self, status: StageStatus, message: str) -> None:
        super().__init__(message)
        self.status: StageStatus = status
        self.message: str = message


def _stop(process: subprocess.Popen[bytes]) -> None:
    """終止子程序與它開出的瀏覽器（整個程序群組）。"""
    if os.name == "nt":  # pragma: no cover - Windows 在 CI 的安裝腳本測試涵蓋
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def _check_cancelled(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise _StageFailedError("cancelled", t("run.cancelled"))


def _wait(process: subprocess.Popen[bytes], seconds: float, cancel: threading.Event | None) -> int:
    """等子程序結束；超過 seconds 或被取消時終止整個程序群組。"""
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        try:
            return process.wait(timeout=max(0.0, min(_POLL_SECONDS, left)))
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                _stop(process)
                raise _StageFailedError("cancelled", t("run.cancelled")) from None
            if left <= 0:
                _stop(process)
                raise _StageFailedError("timed_out", t("run.deadline_killed")) from None


def _run_process(
    command: Sequence[str],
    log: Path,
    deadline: Deadline,
    env: Mapping[str, str],
    cancel: threading.Event | None = None,
) -> None:
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
        )
        try:
            code = _wait(process, remaining + _GRACE_SECONDS, cancel)
        except _StageFailedError:
            raise
        except BaseException:
            _stop(process)
            raise
    if code == _EXIT_DEADLINE:
        raise _StageFailedError("timed_out", t("run.deadline_in_stage"))
    if code != 0:
        raise _StageFailedError("failed", t("run.process_failed", code=code, log=log.name))


# ---------------------------------------------------------------- 執行


def scenario_sources(path: Path, scenario: Scenario) -> list[str]:
    """場景由哪些檔案組成（相對於場景檔所在的資料夾）：場景檔，加上腳本場景的兩支腳本。"""
    sources = [path.name]
    if scenario.script is not None:
        sources += [scenario.script.automation, scenario.script.assertion]
    return sources


def scenario_digest(path: Path, scenario: Scenario) -> str:
    """場景內容的雜湊（sha256），每次執行都記在 result.json 的 scenarioHash。

    管理介面的發布門檻用它確認「通過驗證的就是要發布的版本」。
    """
    digest = hashlib.sha256()
    for relative in scenario_sources(path, scenario):
        digest.update(relative.encode() + b"\0" + (path.parent / relative).read_bytes() + b"\0")
    return digest.hexdigest()


def new_run_id(scenario_id: str, now: datetime | None = None) -> str:
    """執行編號：``<場景 id>-<UTC 日期>-<時間>-<6 碼亂數>``，同時是執行目錄的名稱。"""
    moment = now or datetime.now(UTC)
    return f"{scenario_id}-{moment:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _snapshot(path: Path, scenario: Scenario, folder: Path) -> tuple[Path, str]:
    """把場景檔（與腳本）複製進執行目錄，回傳 (快照路徑, 雜湊)。"""
    target = folder / SCENARIO_DIR
    target.mkdir()
    for relative in scenario_sources(path, scenario):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path.parent / relative, destination)
    snapshot = target / path.name
    return snapshot, scenario_digest(snapshot, scenario)


def _environment(
    secrets: Mapping[str, str], deadline: Deadline, engine: str | None = None
) -> dict[str, str]:
    """子程序的環境變數：Secrets、剩餘秒數 RPA_DEADLINE_SECONDS、瀏覽器 RPA_BROWSER。"""
    env = {**os.environ, **secrets, "PYTHONIOENCODING": "utf-8"}
    env["RPA_DEADLINE_SECONDS"] = f"{max(0, deadline.remaining_ms()) / 1000:.3f}"
    if engine:
        env["RPA_BROWSER"] = engine
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
) -> RunResult:
    """執行場景檔，回傳結果；場景本身沒通過校驗時拋出 ScenarioInvalidError。

    - ``run_id``：指定執行編號（例如管理介面排入佇列時就決定好）；沒指定時用 :func:`new_run_id`。
    - ``cancel``：別的執行緒設定這個事件就取消執行。
    - ``on_stage``：每個階段開始時呼叫，用來回報進度。
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
    snapshot, digest = _snapshot(path, scenario, folder)
    result = RunResult(
        run_id=run_id,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        scenario_hash=digest,
        kind="script" if scenario.script is not None else "dsl",
        engine=engine or scenario.browser.engine,
        directory=folder,
        started_at=now.isoformat(timespec="seconds"),
        stages=[Stage("input"), Stage("automation"), Stage("verify"), Stage("output")],
    )
    secrets = read_secrets(scenario)
    deadline = Deadline.after((deadline_ms or scenario.deadline or DEFAULT_DEADLINE_MS) / 1000)
    current: Stage = result.stage("input")

    def enter(name: StageName) -> None:
        nonlocal current
        current = result.stage(name)
        _check_cancelled(cancel)
        if on_stage is not None:
            on_stage(name)

    try:
        enter("input")
        _input_stage(scenario, inputs, result, folder)
        enter("automation")
        _automation_stage(
            scenario, snapshot, folder, deadline, secrets, base_url, engine, headed, cancel, result
        )
        enter("verify")
        _verify_stage(scenario, snapshot, folder, deadline, secrets, cancel, result)
        enter("output")
        _output_stage(scenario, folder, deadline, secrets, result)
        result.status = "passed"
    except _StageFailedError as failure:
        current.status = failure.status
        current.message = mask(failure.message, secrets)
        result.status = failure.status if failure.status in ("timed_out", "cancelled") else "failed"
        # 子程序寫在 diagnostic.json 的錯誤（例如找不到元素）比階段說明更具體，一併保留
        detail = result.error if failure.status != "cancelled" else None
        result.error = f"{current.message}；{detail}" if detail else current.message
    except KeyboardInterrupt:
        current.status = "cancelled"
        current.message = t("run.cancelled")
        result.status = "cancelled"
        result.error = current.message
    finally:
        (folder / CANDIDATE).unlink(missing_ok=True)
        for leftover in folder.glob(".*.tmp"):  # 子程序寫到一半被終止時留下的暫存檔
            leftover.unlink(missing_ok=True)
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
    scenario: Scenario, inputs: Mapping[str, object], result: RunResult, folder: Path
) -> None:
    started = time.monotonic()
    resolved, problems = check_inputs(scenario, inputs)
    problems += [
        Problem(name, t("contract.secret_missing", name=name)) for name in missing_secrets(scenario)
    ]
    result.input = resolved
    write_json(folder / INPUT, resolved)
    _timed(result.stage("input"), started)
    if problems:
        result.problems = [problem.message for problem in problems]
        raise _StageFailedError("failed", t("run.input_failed", count=len(problems)))
    result.stage("input").status = "passed"


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
) -> None:
    started = time.monotonic()
    stage = result.stage("automation")
    url = base_url or scenario.browser.base_url
    if scenario.script is not None:
        command = [
            sys.executable,
            str(snapshot.parent / scenario.script.automation),
            "--input",
            str(folder / INPUT),
            "--facts",
            str(folder / FACTS),
            "--screenshot",
            str(folder / SCREENSHOT),
            "--target-url",
            url or "",
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "rpa_runner.child",
            "--scenario",
            str(snapshot),
            "--input",
            str(folder / INPUT),
            "--out",
            str(folder),
            "--deadline",
            f"{max(0, deadline.remaining_ms()) / 1000:.3f}",
        ]
        command += ["--engine", engine] if engine else []
        command += ["--base-url", base_url] if base_url else []
        command += ["--headed"] if headed else []
    try:
        env = _environment(secrets, deadline, engine or scenario.browser.engine)
        _run_process(command, folder / AUTOMATION_LOG, deadline, env, cancel)
    finally:
        _timed(stage, started)
        details = read_json_or(folder / DIAGNOSTIC, None)
        if isinstance(details, dict):
            error = cast("dict[str, object]", details).get("error", "")
            result.error = mask(str(error), secrets) or None
    if not (folder / FACTS).exists():
        raise _StageFailedError("failed", t("run.facts_missing"))
    stage.status = "passed"


def _verify_stage(
    scenario: Scenario,
    snapshot: Path,
    folder: Path,
    deadline: Deadline,
    secrets: Mapping[str, str],
    cancel: threading.Event | None,
    result: RunResult,
) -> None:
    started = time.monotonic()
    stage = result.stage("verify")
    if scenario.script is not None:
        command = [
            sys.executable,
            str(snapshot.parent / scenario.script.assertion),
            "--input",
            str(folder / INPUT),
            "--facts",
            str(folder / FACTS),
            "--output",
            str(folder / CANDIDATE),
        ]
        try:
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
    if scenario.script is not None:
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
