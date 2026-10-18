"""遠端 worker 的執行迴圈（rpa_worker.service）：被拒時停止並回傳訊息、要求停止時正常結束。

真的連管理 Portal 的完整流程在 apps/server 的 test_remote_worker_flow.py。
"""

import threading
from collections.abc import Callable, Mapping
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


class _Recording(WorkerClient):
    """記下每個請求；hello 成功、claim 沒有任務。"""

    def __init__(self) -> None:
        super().__init__("http://x", "t")
        self.paths: list[str] = []

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
        self.paths.append(path)
        if path == "/hello":
            return {"worker": "box", "fingerprint": "f"}
        threading.Event().wait(0.02)  # 長輪詢沒有任務
        return {}


def _wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> bool:
    deadline = threading.Event()
    for _ in range(int(seconds / 0.02)):
        if condition():
            return True
        deadline.wait(0.02)
    return condition()


def test_paused_sends_nothing_and_resumes_with_hello(tmp_path: Path) -> None:
    client = _Recording()
    events: list[str] = []
    stop = threading.Event()
    paused = threading.Event()
    paused.set()

    def notify(event: str, details: Mapping[str, object]) -> None:
        events.append(event)

    thread = threading.Thread(
        target=run_remote_worker,
        args=(client, INFO, tmp_path),
        kwargs={
            "stop": stop,
            "notify": notify,
            "poll_seconds": 0.02,
            "paused": paused,
        },
    )
    thread.start()
    try:
        assert _wait_for(lambda: "paused" in events)
        threading.Event().wait(0.2)
        assert client.paths == []  # 暫停時不送任何請求：管理 Portal 會看到離線
        assert events.count("paused") == 1  # 只通知一次

        paused.clear()
        assert _wait_for(lambda: "/claim" in client.paths)
        assert client.paths[0] == "/hello"  # 恢復時先重新上線
        assert "online" in events

        paused.set()
        assert _wait_for(lambda: events.count("paused") == 2)
        paused.clear()
        assert _wait_for(lambda: client.paths.count("/hello") == 2)
    finally:
        stop.set()
        thread.join(10)
    assert not thread.is_alive()


def test_stop_seconds_is_read_when_stopping(tmp_path: Path) -> None:
    asked: list[bool] = []
    stop = threading.Event()
    stop.set()

    def seconds() -> float:
        asked.append(True)
        return 1.0

    run_remote_worker(
        _Offline("http://x", "t"),
        INFO,
        tmp_path,
        stop=stop,
        notify=lambda event, details: None,
        poll_seconds=0.02,
        stop_seconds=seconds,
    )
    assert asked == [True]
