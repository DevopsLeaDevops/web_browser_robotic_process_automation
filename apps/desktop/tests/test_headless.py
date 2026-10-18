"""``rpa-worker.exe --no-window``（rpa_desktop.headless）：結束碼與日誌。外部動作換成替身。"""

import logging
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from rpa_desktop import headless
from rpa_desktop.controller import Closable, Services
from rpa_desktop.credentials import MemoryStore
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.single_instance import InstanceLock
from rpa_worker.environment import WorkerInfo
from rpa_worker.pairing import App, Invite, PairResult
from rpa_worker.remote import Notify, WorkerClient

SERVER = "http://127.0.0.1:8081"
LINE = Invite(SERVER, "abcdefghijklmnopqrstuvwxyz012345", "worker").line()


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in root.handlers:
        if handler not in before and isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def services(runs: list[str]) -> Services:
    def pair(invite: Invite, app: App) -> PairResult:
        return PairResult(invite.server, "ci", "CI", "worker", "tok", 1, None, None)

    def missing(engines: Sequence[str]) -> list[str]:
        return []

    def download(
        engine: str, progress: Progress, environ: Mapping[str, str], cancel: threading.Event
    ) -> DownloadResult:
        return DownloadResult(0, "")

    def run(
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
        stop_seconds: Callable[[], float] = lambda: 120.0,
    ) -> str | None:
        runs.append(client.token or "")
        notify("online", {"worker": "ci", "sameVersion": True})
        return None  # 例如收到停止的要求

    def testsite(port: int) -> tuple[Closable | None, str, str]:
        return None, "running", ""

    def detect(name: str | None, fingerprint: str, version: str) -> WorkerInfo:
        return WorkerInfo(name="ci", fingerprint=fingerprint)

    return Services(
        pair=pair, missing=missing, download=download, run=run, testsite=testsite, detect=detect
    )


def test_invite_pairs_runs_and_logs(tmp_path: Path) -> None:
    runs: list[str] = []
    log = tmp_path / "out" / "worker.log"
    store = MemoryStore()
    code = headless.main(
        ["--invite", LINE, "--log", str(log)],
        environ={"RPA_WORKER_HOME": str(tmp_path / "home"), "RPA_LANG": "en"},
        store=store,
        services=services(runs),
    )
    assert code == 0
    assert runs == ["tok"]
    assert store.items == {f"ci@{SERVER}": "tok"}
    text = log.read_text(encoding="utf-8")
    assert "Paired" in text  # 訊息是 RPA_LANG 的語言
    assert "abcdefghijklmnop" not in text  # 日誌不記邀請代碼
    assert (tmp_path / "home" / "pairing.json").is_file()


def test_without_pairing_exits_2(tmp_path: Path) -> None:
    code = headless.main(
        ["--log", str(tmp_path / "w.log")],
        environ={"RPA_WORKER_HOME": str(tmp_path)},
        store=MemoryStore(),
        services=services([]),
    )
    assert code == 2


def test_second_copy_exits_4(tmp_path: Path) -> None:
    held = InstanceLock(tmp_path)
    assert held.acquire()
    try:
        code = headless.main(
            ["--log", str(tmp_path / "w.log")],
            environ={"RPA_WORKER_HOME": str(tmp_path)},
            store=MemoryStore(),
            services=services([]),
        )
    finally:
        held.release()
    assert code == 4
    assert "已經有一份 RPA Worker" in (tmp_path / "w.log").read_text(encoding="utf-8")


def test_stop_request_ends_the_worker_cleanly(tmp_path: Path) -> None:
    """--no-window 是視窗程式，收不到 Ctrl+C：自動化用資料夾的 stop.request 請它結束。"""
    home = tmp_path / "home"
    stopped: list[bool] = []
    base = services([])

    def run(
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
        stop_seconds: Callable[[], float] = lambda: 120.0,
    ) -> str | None:
        InstanceLock(home).request_stop()
        stopped.append(stop.wait(10))
        return None

    fake = Services(
        pair=base.pair,
        missing=base.missing,
        download=base.download,
        run=run,
        testsite=base.testsite,
        detect=base.detect,
    )
    code = headless.main(
        ["--invite", LINE, "--log", str(tmp_path / "w.log")],
        environ={"RPA_WORKER_HOME": str(home)},
        store=MemoryStore(),
        services=fake,
    )
    assert code == 0
    assert stopped == [True]
