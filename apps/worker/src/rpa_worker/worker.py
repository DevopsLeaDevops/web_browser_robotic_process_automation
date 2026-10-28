"""背景 worker：從任務來源領取任務，一次執行一個。

- 任務來源（:class:`JobSource`）由使用的一方實作：本機是 rpa-server 的資料庫（M3），
  遠端 worker 是管理 Portal 的 Worker API（:mod:`rpa_worker.remote`，M9a）。
- 每個任務交給 :func:`rpa_runner.run.execute`：子程序、總期限、取消都由 runner 處理。
- 取消：:meth:`Worker.cancel` 讓執行中的任務立即終止程序群組；任務還沒開始時先記下來，
  一開始就取消（領取與開始執行之間的空檔不會漏掉）。
- 任務來源拋出的例外只記錄、不中斷迴圈；worker 一直跑到 :meth:`Worker.stop`。
- 檔案入參（M7c）：任務帶著上傳檔在這台的位置、允許的資料夾與上限（:class:`FileOptions`），
  只在有設定時才交給執行器（舊的執行器不必認得這些參數）。
"""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, TypedDict

from rpa_core.i18n import Locale, use_locale
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName, execute

__all__ = ["Executor", "FileOptions", "Job", "JobSource", "Worker"]

logger = logging.getLogger("rpa_worker")

POLL_SECONDS: Final = 2.0
"""沒有被喚醒時，每隔這麼久向任務來源要一次任務。"""


class FileOptions(TypedDict, total=False):
    """檔案入參的執行選項（M7c，見 :func:`rpa_runner.run.execute`）。"""

    uploads: Mapping[str, Path]
    """上傳檔代號 → 這台電腦上的檔案。"""
    input_folders: Sequence[Path] | None
    """path 值可以讀的資料夾；None 時用環境變數 RPA_INPUT_FOLDERS。"""
    max_file_bytes: int
    max_run_bytes: int


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
    headless: bool = True
    """無頭模式（不顯示瀏覽器視窗）；False 是有頭模式。"""
    login: LoginSettings | None = None
    """場景有 login 時，角色的登入設定。"""
    secrets: Mapping[str, str] = field(default_factory=dict[str, str])
    """Secrets 的值（只放在記憶體）；沒有的由 runner 從同名的環境變數找。"""
    locale: Locale | None = None
    """報告與訊息的語言；None 用 worker 的語言（遠端任務帶著管理 Portal 的語言，M9a）。"""
    record_video: bool = False
    """自動化階段錄影（M12，管理 Portal 的錄影設定）。"""
    uploads: Mapping[str, Path] = field(default_factory=dict[str, Path])
    """上傳檔代號 → 這台電腦上的檔案（M7c）。"""
    input_folders: Sequence[Path] | None = None
    """檔案入參的 path 可以讀的資料夾；None 時用環境變數 RPA_INPUT_FOLDERS。"""
    max_file_bytes: int | None = None
    max_run_bytes: int | None = None

    def file_options(self) -> FileOptions:
        """有設定的檔案選項（沒有的不放，執行器用自己的預設）。"""
        options: FileOptions = {}
        if self.uploads:
            options["uploads"] = self.uploads
        if self.input_folders is not None:
            options["input_folders"] = self.input_folders
        if self.max_file_bytes is not None:
            options["max_file_bytes"] = self.max_file_bytes
        if self.max_run_bytes is not None:
            options["max_run_bytes"] = self.max_run_bytes
        return options


class JobSource(Protocol):
    """任務來源：領取任務、回報進度與結果。方法會在 worker 的執行緒中呼叫。"""

    def claim(self) -> Job | None:
        """領取下一個待執行的任務；沒有就回傳 None。"""
        ...

    def progress(self, job: Job, stage: StageName) -> None:
        """任務進入某個階段（入參、登入檢查、自動化、斷言、出參）。"""
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
        max_file_bytes: int = ...,
        max_run_bytes: int = ...,
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
        locale = job.locale or self.locale
        if locale is None:
            self._execute(job)
        else:
            with use_locale(locale):
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
                headed=not job.headless,
                deadline_ms=job.deadline_ms,
                run_id=job.run_id,
                cancel=cancel,
                on_stage=lambda stage: self._report(self.source.progress, job, stage),
                login=job.login,
                secrets=job.secrets,
                record_video=job.record_video,
                **job.file_options(),
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
