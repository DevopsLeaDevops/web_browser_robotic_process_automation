"""遠端 worker 的執行迴圈（rpa_worker.service）：被拒時停止並回傳訊息、要求停止時正常結束。

真的連管理 Portal 的完整流程在 apps/server 的 test_remote_worker_flow.py。
"""

import threading
from pathlib import Path
from typing import IO

from rpa_worker.environment import WorkerInfo
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient
from rpa_worker.service import run_remote_worker

INFO = WorkerInfo(name="box", fingerprint="f")


class _Rejecting(WorkerClient):
    def call(
        self,
        method: str,
        path: str,
        payload: object = None,
        *,
        body: bytes | IO[bytes] | None = None,
        content_type: str | None = None,
        length: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        raise WorkerApiError(401, "worker_unauthorized", "權杖不對")


class _Offline(WorkerClient):
    def call(
        self,
        method: str,
        path: str,
        payload: object = None,
        *,
        body: bytes | IO[bytes] | None = None,
        content_type: str | None = None,
        length: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        raise ConnectionLostError("refused")


def test_rejection_stops_and_returns_the_message(tmp_path: Path) -> None:
    events: list[str] = []
    stop = threading.Event()
    stopping: list[bool] = []

    fatal = run_remote_worker(
        _Rejecting("http://x", "t"),
        INFO,
        tmp_path,
        stop=stop,
        notify=lambda event, details: events.append(event),
        on_stopping=lambda: stopping.append(True),
        poll_seconds=0.05,
    )

    assert fatal == "權杖不對"
    assert stop.is_set()
    assert "rejected" in events
    assert stopping == [True]


def test_stop_ends_the_loop_without_a_message(tmp_path: Path) -> None:
    stop = threading.Event()
    events: list[str] = []
    timer = threading.Timer(1.0, stop.set)
    timer.start()
    try:
        fatal = run_remote_worker(
            _Offline("http://x", "t"),
            INFO,
            tmp_path,
            stop=stop,
            notify=lambda event, details: events.append(event),
            poll_seconds=0.05,
        )
    finally:
        timer.cancel()

    assert fatal is None
    assert events[:1] == ["offline"]  # 連不上只通知一次，之後自動重試
