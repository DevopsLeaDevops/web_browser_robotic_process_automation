"""rpa-worker：領取、執行、回報、取消、停止。

用記憶體裡的假任務來源；需要真實瀏覽器的情境只用 Chromium（兩種瀏覽器在 rpa-runner 已測過）。
"""

import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.run import RunResult, ScenarioInvalidError, StageName
from rpa_worker import Job, Worker
from testsite.browsers import require_engine
from testsite.server import running

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"


class FakeSource:
    """記憶體裡的任務來源：記下每一次回報。"""

    def __init__(self, *jobs: Job) -> None:
        self.jobs = deque(jobs)
        self.stages: dict[str, list[StageName]] = {}
        self.results: dict[str, RunResult] = {}
        self.errors: dict[str, Exception] = {}
        self.done = threading.Event()
        self.on_stage: dict[tuple[str, StageName], threading.Event] = {}

    def add(self, job: Job) -> None:
        self.jobs.append(job)

    def claim(self) -> Job | None:
        return self.jobs.popleft() if self.jobs else None

    def progress(self, job: Job, stage: StageName) -> None:
        self.stages.setdefault(job.run_id, []).append(stage)
        if (event := self.on_stage.get((job.run_id, stage))) is not None:
            event.set()

    def finish(self, job: Job, result: RunResult) -> None:
        self.results[job.run_id] = result
        self.done.set()

    def fail(self, job: Job, error: Exception) -> None:
        self.errors[job.run_id] = error
        self.done.set()


class BrokenSource(FakeSource):
    def progress(self, job: Job, stage: StageName) -> None:
        raise RuntimeError("回報進度失敗")


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def invalid_input_job(run_id: str, out: Path) -> Job:
    """入參不合規則：只跑入參校驗，不會啟動瀏覽器。"""
    return Job(run_id, BA_001, {"quantity": 100}, out_root=out)


def test_run_once_reports_progress_and_result(tmp_path: Path) -> None:
    source = FakeSource(invalid_input_job("run-1", tmp_path))
    worker = Worker(source)

    assert worker.run_once() is True
    assert worker.run_once() is False

    result = source.results["run-1"]
    assert result.status == "failed"
    assert result.directory == tmp_path / "run-1"
    assert source.stages["run-1"] == ["input"]
    assert worker.current is None


def test_scenario_that_cannot_run_is_reported_as_failure(tmp_path: Path) -> None:
    source = FakeSource(Job("run-2", tmp_path / "missing.yaml", out_root=tmp_path))

    Worker(source).run_once()

    assert isinstance(source.errors["run-2"], ScenarioInvalidError)
    assert "run-2" not in source.results


def test_source_errors_do_not_stop_the_worker(tmp_path: Path) -> None:
    source = BrokenSource(invalid_input_job("run-3", tmp_path))

    Worker(source).run_once()

    assert source.results["run-3"].status == "failed"


def test_cancel_before_start(tmp_path: Path) -> None:
    source = FakeSource(Job("run-4", BA_001, {"title": "甲", "quantity": 1}, out_root=tmp_path))
    worker = Worker(source)

    assert worker.cancel("run-4") is False
    worker.run_once()

    assert source.results["run-4"].status == "cancelled"
    assert source.stages.get("run-4", []) == []


def test_background_thread_wakes_up_for_new_jobs(tmp_path: Path) -> None:
    source = FakeSource()
    worker = Worker(source, poll_seconds=30)
    worker.start()
    try:
        source.add(invalid_input_job("run-5", tmp_path))
        worker.wake()
        assert source.done.wait(10), "worker 沒有被喚醒"
    finally:
        worker.stop()

    assert source.results["run-5"].status == "failed"
    assert not worker.alive


def test_locale_is_applied_to_reports(tmp_path: Path) -> None:
    source = FakeSource(invalid_input_job("run-6", tmp_path))

    Worker(source, locale="en").run_once()

    assert source.results["run-6"].problems == ["Input quantity does not satisfy maximum: 30"]


@pytest.mark.browser
def test_real_run_and_cancel_while_running(tmp_path: Path) -> None:
    engine = require_engine("chromium")
    with running() as site:
        source = FakeSource(
            Job("ok", BA_001, {"title": "worker", "quantity": 2}, tmp_path, engine, site),
            Job("stop", BA_001, {"title": "取消", "quantity": 2}, tmp_path, engine, site),
        )
        automation = threading.Event()
        source.on_stage[("stop", "automation")] = automation
        worker = Worker(source, poll_seconds=0.1)
        worker.start()
        try:
            assert automation.wait(60), "第二個任務沒有開始"
            time.sleep(1)
            assert worker.current == "stop"
            assert worker.cancel("stop") is True
            deadline = time.monotonic() + 30
            while "stop" not in source.results and time.monotonic() < deadline:
                time.sleep(0.1)
        finally:
            worker.stop()

    assert source.results["ok"].status == "passed", source.results["ok"].error
    assert source.results["ok"].output is not None
    assert source.results["stop"].status == "cancelled"
