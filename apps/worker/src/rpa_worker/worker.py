"""背景 worker：從任務來源領取任務，一次執行一個。

- 任務來源（:class:`JobSource`）由使用的一方實作：M3 是 rpa-server 的資料庫，M9 換成分散式佇列。
- 每個任務交給 :func:`rpa_runner.run.execute`：子程序、總期限、取消都由 runner 處理。
- 取消：:meth:`Worker.cancel` 讓執行中的任務立即終止程序群組；任務還沒開始時先記下來，
  一開始就取消（領取與開始執行之間的空檔不會漏掉）。
- 任務來源拋出的例外只記錄、不中斷迴圈；worker 一直跑到 :meth:`Worker.stop`。
"""

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from rpa_core.i18n import Locale, use_locale
from rpa_runner.run import RunResult, StageName, execute

__all__ = ["Executor", "Job", "JobSource", "Worker"]

logger = logging.getLogger("rpa_worker")

POLL_SECONDS: Final = 2.0
"""沒有被喚醒時，每隔這麼久向任務來源要一次任務。"""


@dataclass(frozen=True, slots=True)
class Job:
    """一個待執行的任務：哪個場景檔、什麼入參、結果放哪裡。"""

    run_id: str
    scenario: Path
    inputs: Mapping[str, object] = field(default_factory=dict[str, object])
    out_root: Path = Path("runs")
    engine: str | None = None
    base_url: str | None = None
    deadline_ms: int | None = None


class JobSource(Protocol):
    """任務來源：領取任務、回報進度與結果。方法會在 worker 的執行緒中呼叫。"""

    def claim(self) -> Job | None:
        """領取下一個待執行的任務；沒有就回傳 None。"""
        ...

    def progress(self, job: Job, stage: StageName) -> None:
        """任務進入某個階段（入參、自動化、斷言、出參）。"""
        ...

    def finish(self, job: Job, result: RunResult) -> None:
        """任務執行完畢，不論通過、失敗、逾時或取消。"""
        ...

    def fail(self, job: Job, error: Exception) -> None:
        """任務沒辦法執行，例如場景檔沒有通過校驗或程式錯誤。"""
        ...


class Executor(Protocol):
    """執行一個任務的函式，預設是 :func:`rpa_runner.run.execute`；測試可以換成假的。"""

    def __call__(
        self,
        path: Path,
        inputs: Mapping[str, object],
        *,
        out_root: Path,
        base_url: str | None = None,
        engine: str | None = None,
        deadline_ms: int | None = None,
        run_id: str | None = None,
        cancel: threading.Event | None = None,
        on_stage: Callable[[StageName], None] | None = None,
    ) -> RunResult: ...


class Worker:
    """一次執行一個任務的背景執行緒。

    用法::

        worker = Worker(source)
        worker.start()
        worker.wake()          # 有新任務時叫醒，不必等下一次輪詢
        worker.cancel(run_id)  # 取消
        worker.stop()
    """

    def __init__(
        self,
        source: JobSource,
        *,
        poll_seconds: float = POLL_SECONDS,
        locale: Locale | None = None,
        executor: Executor = execute,
    ) -> None:
        self.source = source
        self.poll_seconds = poll_seconds
        self.locale: Locale | None = locale
        self._executor = executor
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: tuple[str, threading.Event] | None = None
        self._cancel_requests: set[str] = set()

    # ------------------------------------------------------------ 控制

    @property
    def current(self) -> str | None:
        """執行中任務的執行編號。"""
        with self._lock:
            return self._current[0] if self._current else None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.alive:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="rpa-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 30.0) -> None:
        """停止迴圈；執行中的任務會被取消。"""
        self._stopping.set()
        with self._lock:
            if self._current is not None:
                self._current[1].set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def wake(self) -> None:
        """有新任務了：不必等下一次輪詢。"""
        self._wake.set()

    def cancel(self, run_id: str) -> bool:
        """取消任務；回傳任務是否正在這個 worker 執行。

        還沒開始的任務先記下來：領取之後一開始就取消。
        """
        with self._lock:
            if self._current is not None and self._current[0] == run_id:
                self._current[1].set()
                return True
            self._cancel_requests.add(run_id)
            return False

    # ------------------------------------------------------------ 執行

    def run_once(self) -> bool:
        """領取並執行一個任務；沒有任務時回傳 False。"""
        try:
            job = self.source.claim()
        except Exception:
            logger.exception("領取任務失敗")
            return False
        if job is None:
            return False
        if self.locale is None:
            self._execute(job)
        else:
            with use_locale(self.locale):
                self._execute(job)
        return True

    def _loop(self) -> None:
        while not self._stopping.is_set():
            if self.run_once():
                continue
            self._wake.wait(self.poll_seconds)
            self._wake.clear()

    def _execute(self, job: Job) -> None:
        cancel = threading.Event()
        with self._lock:
            if job.run_id in self._cancel_requests or self._stopping.is_set():
                cancel.set()
            self._cancel_requests.discard(job.run_id)
            self._current = (job.run_id, cancel)
        try:
            result = self._executor(
                job.scenario,
                job.inputs,
                out_root=job.out_root,
                base_url=job.base_url,
                engine=job.engine,
                deadline_ms=job.deadline_ms,
                run_id=job.run_id,
                cancel=cancel,
                on_stage=lambda stage: self._report(self.source.progress, job, stage),
            )
        except Exception as error:
            logger.warning("任務 %s 無法執行：%s", job.run_id, error)
            self._report(self.source.fail, job, error)
        else:
            self._report(self.source.finish, job, result)
        finally:
            with self._lock:
                self._current = None

    @staticmethod
    def _report[*Args](callback: Callable[[*Args], None], *args: *Args) -> None:
        """呼叫任務來源；它拋出的例外只記錄，不影響 worker。"""
        try:
            callback(*args)
        except Exception:
            logger.exception("任務來源回報失敗")
