"""遠端 worker 的執行迴圈：``rpa worker`` 與打包的 RPA Worker 共用（M9a；M10.1 抽出）。

連上管理 Portal 的 Worker API，一次執行一個任務，直到 ``stop`` 被設定或管理 Portal 拒絕這台
worker（權杖不對、協定版本不同）。停止時取消執行中的任務並回報結果。
畫面上的文字由呼叫的人決定（``notify`` 收到事件，見 :class:`rpa_worker.remote.RemoteJobSource`）。
"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Final

from rpa_worker.environment import WorkerInfo
from rpa_worker.remote import Notify, RemoteJobSource, WorkerClient
from rpa_worker.worker import Worker

__all__ = ["STOP_SECONDS", "run_remote_worker"]

STOP_SECONDS: Final = 120.0
"""停止時最多等執行中的任務這麼久（取消後回報結果）。"""


def run_remote_worker(
    client: WorkerClient,
    info: WorkerInfo,
    work_dir: Path,
    *,
    stop: threading.Event,
    notify: Notify,
    keep_runs: bool = False,
    on_stopping: Callable[[], None] = lambda: None,
    poll_seconds: float = 0.5,
    paused: threading.Event | None = None,
    stop_seconds: Callable[[], float] = lambda: STOP_SECONDS,
) -> str | None:
    """執行到 ``stop`` 被設定為止；管理 Portal 拒絕這台 worker 時回傳拒絕的訊息，否則回傳 None。

    ``paused`` 設定時做完目前的任務後不再領取（Worker App 的「暫停接任務」）。
    ``stop_seconds`` 在停止時才呼叫：停止時最多等執行中的任務多久（Windows 關機時要很短）。
    """
    source = RemoteJobSource(
        client, info, work_dir, keep_runs=keep_runs, notify=notify, paused=paused
    )
    runner = Worker(source, poll_seconds=poll_seconds)
    source.on_cancel = runner.cancel
    fatal: list[str] = []

    def on_fatal(message: str) -> None:
        fatal.append(message)
        stop.set()

    source.on_fatal = on_fatal
    runner.start()
    try:
        while not stop.wait(0.5):
            if not runner.alive:
                break
    finally:
        on_stopping()
        runner.stop(timeout=stop_seconds())  # 執行中的任務被取消，結果照常回報
        source.close()
    return fatal[0] if fatal else None
