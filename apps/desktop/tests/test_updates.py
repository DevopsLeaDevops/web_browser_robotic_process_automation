"""桌面 App 跟著管理 Portal 的版本更新（ADR 0018 第二階段）：下載與安裝（rpa_desktop.updates），
以及 RPA Worker 閒置時重新啟動、RPA 錄製端下次開啟時套用（兩個 controller）。

真的打包版裝更新檔、重新啟動與退回在 CI 的桌面端建置（.github/workflows/desktop.yml）。
"""

import hashlib
import queue
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from rpa_core.i18n import use_locale
from rpa_desktop import updates
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import Closable, Services, WorkerController
from rpa_desktop.credentials import Credentials, MemoryStore
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.i18n import t
from rpa_desktop.recorder_controller import Notify, RecorderController, RecorderServices, wait_for
from rpa_desktop.updates import DOWNLOADS_DIR, Checked, DeviceUpdater, Offer
from rpa_update import ed25519
from rpa_update.errors import UpdateError
from rpa_update.layers import read_active
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import Runtime
from rpa_worker.environment import WorkerInfo
from rpa_worker.pairing import App, Invite, PairResult
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient

SERVER = "http://192.168.1.10:8081"
SEED = bytes(range(32))
RUNTIME = Runtime(
    "worker-windows-x64", "0123456789abcdef", (ed25519.public_key(SEED),), release="0.5.0-0000001"
)
READY = Checked(Offer("available", "0.6.0", "0.6.0-0000002", 10, "0" * 64), ready=True)


def make_update(tmp_path: Path, commit: str = "0000002") -> Path:
    source = tmp_path / f"source-{commit}"
    (source / "app" / "rpa_core").mkdir(parents=True)
    (source / "app" / "rpa_core" / "__init__.py").write_text(f"COMMIT = {commit!r}\n")
    files = scan_tree(source)
    manifest = Manifest(
        version="0.6.0",
        commit=commit,
        built_at="2026-10-25T09:00:00+00:00",
        fingerprint="f" * 16,
        protocol=1,
        features=(),
        runtimes={RUNTIME.target: RUNTIME.id},
        files=files,
    )
    path = tmp_path / f"update-{commit}.zip"
    write_update(path, manifest, {name: source / name for name in files}, SEED)
    return path


def offer_for(path: Path, **changes: object) -> dict[str, object]:
    data = path.read_bytes()
    reply: dict[str, object] = {
        "status": "available",
        "version": "0.6.0",
        "release": "0.6.0-0000002",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    reply.update(changes)
    return reply


class FakeClient(WorkerClient):
    """管理 Portal 的替身：``POST /update`` 回 ``reply``，``GET /update/file`` 給 ``file``。"""

    def __init__(self, reply: Mapping[str, object], file: Path | None = None) -> None:
        super().__init__(SERVER, "tok")
        self.reply = dict(reply)
        self.file = file
        self.calls: list[tuple[str, str, object]] = []
        self.downloads = 0

    def call(
        self, method: str, path: str, payload: object = None, **options: object
    ) -> dict[str, object]:
        self.calls.append((method, path, payload))
        return dict(self.reply)

    def download(
        self, path: str, destination: Path, *, limit: int, timeout: float | None = None
    ) -> int:
        assert path == "/update/file"
        assert self.file is not None
        self.downloads += 1
        data = self.file.read_bytes()
        if len(data) > limit:
            raise ConnectionLostError(f"larger than {limit} bytes")
        destination.write_bytes(data)
        return len(data)


# ---------------------------------------------------------------- 下載與安裝


def test_downloads_installs_and_reports(tmp_path: Path) -> None:
    root = tmp_path / "home" / "app"
    updater = DeviceUpdater("worker", RUNTIME, root, version="0.5.0", current=RUNTIME.release)
    assert updater.report() == {
        "app": "worker",
        "target": RUNTIME.target,
        "runtime": RUNTIME.id,
        "release": "0.5.0-0000001",
        "version": "0.5.0",
        "failed": None,
    }
    update = make_update(tmp_path)
    client = FakeClient(offer_for(update), update)
    checked = updater.check(client)
    assert checked.ready
    assert checked.offer.release == "0.6.0-0000002"
    assert client.calls == [("POST", "/update", updater.report())]
    active = read_active(root)
    assert (active.release, active.pending) == ("0.6.0-0000002", True)
    assert list((root / DOWNLOADS_DIR).iterdir()) == []  # 裝好就刪掉
    # 之前裝好、還沒重新啟動：不再下載
    assert updater.check(client).ready
    assert client.downloads == 1


def test_bad_download_is_not_installed(tmp_path: Path) -> None:
    root = tmp_path / "app"
    updater = DeviceUpdater("worker", RUNTIME, root, version="0.5.0", current=RUNTIME.release)
    update = make_update(tmp_path)
    with pytest.raises(UpdateError, match="download_mismatch"):
        updater.check(FakeClient(offer_for(update, sha256="0" * 64), update))
    with pytest.raises(UpdateError, match="update_too_large"):
        updater.check(FakeClient(offer_for(update, size=updates.MAX_UPDATE_BYTES + 1), update))
    with pytest.raises(ConnectionLostError):
        updater.check(FakeClient(offer_for(update, size=10), update))
    assert read_active(root).release is None
    assert list((root / DOWNLOADS_DIR).iterdir()) == []


@pytest.mark.parametrize("status", ["current", "full", "failed", "off", "unavailable"])
def test_other_replies_download_nothing(tmp_path: Path, status: str) -> None:
    updater = DeviceUpdater("worker", RUNTIME, tmp_path, version="0.5.0", current=RUNTIME.release)
    client = FakeClient({"status": status, "version": "0.6.0", "release": "0.6.0-0000002"})
    checked = updater.check(client)
    assert (checked.offer.status, checked.ready, client.downloads) == (status, False, 0)


def test_offer_ignores_bad_values() -> None:
    assert Offer.from_json({"status": "available", "size": True, "sha256": "AB"}) == Offer(
        "available", sha256="ab"
    )


def test_only_packaged_apps_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "load_runtime", lambda: None)
    assert updates.detect_updater("worker", "0.5.0") is None
    monkeypatch.setattr(updates, "load_runtime", lambda: RUNTIME)
    monkeypatch.setenv("RPA_WORKER_HOME", str(tmp_path))
    found = DeviceUpdater.detect("worker", "0.5.0")
    assert found is not None
    assert (found.root, found.current) == (tmp_path / "app", RUNTIME.release)


# ---------------------------------------------------------------- RPA Worker


@dataclass
class FakeUpdater:
    result: Checked | Exception = READY
    checks: int = 0

    def check(self, client: WorkerClient) -> Checked:
        self.checks += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class Harness:
    """接任務迴圈的替身：送出 :meth:`push` 的事件，暫停時像真的一樣回報 ``paused``。"""

    updater: FakeUpdater | None = field(default_factory=FakeUpdater)
    events: "queue.Queue[tuple[str, dict[str, object]]]" = field(
        default_factory=lambda: queue.Queue[tuple[str, dict[str, object]]]()
    )
    fatal: str | None = None
    restarts: list[str] = field(default_factory=lambda: [])

    def push(self, event: str, details: Mapping[str, object] | None = None) -> None:
        self.events.put((event, dict(details or {})))

    def restart(self) -> bool:
        self.restarts.append("restart")
        return True

    def services(self) -> Services:
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
            reported = False
            while not stop.wait(0.01):
                while not self.events.empty():
                    event, details = self.events.get()
                    notify(event, details)
                    if event == "rejected":
                        return self.fatal
                if paused is not None and paused.is_set():
                    if not reported:
                        notify("paused", {})
                    reported = True
                else:
                    reported = False
            return None

        def download(
            engine: str, progress: Progress, environ: Mapping[str, str], cancel: threading.Event
        ) -> DownloadResult:
            raise AssertionError("沒有缺瀏覽器")

        def missing(engines: Sequence[str]) -> list[str]:
            return []

        def testsite(port: int) -> tuple[Closable | None, str, str]:
            return None, "disabled", ""

        def detect(name: str | None, fingerprint: str, version: str) -> WorkerInfo:
            return WorkerInfo(name="box", fingerprint=fingerprint, version=version, display=True)

        def pair(invite: Invite, app: App) -> PairResult:
            raise AssertionError("已經配對")

        return Services(
            pair=pair,
            missing=missing,
            download=download,
            run=run,
            testsite=testsite,
            detect=detect,
            updater=lambda app, version: self.updater,
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def worker(tmp_path: Path, harness: Harness, store: MemoryStore) -> Iterator[WorkerController]:
    credentials = Credentials(tmp_path, store)
    credentials.save(PairResult(SERVER, "win-01", "Windows", "worker", "tok", 1, None, None))
    controller = WorkerController(
        home=tmp_path,
        build=BuildInfo(app="worker", version="0.5.0", fingerprint="fp", protocol=1),
        environ={},
        credentials=credentials,
        autostart=AutoStart(None, Path("C:/RPA/rpa-worker.exe")),
        services=harness.services(),
        testsite=False,
    )
    try:
        yield controller
    finally:
        controller.stop()
        controller.wait(10)


def message(controller: WorkerController | RecorderController) -> tuple[str, str] | None:
    value = controller.snapshot()["message"]
    if not isinstance(value, dict):
        return None
    shown = cast("dict[str, object]", value)
    return str(shown["text"]), str(shown["level"])


def text(controller: WorkerController | RecorderController, key: str, **params: object) -> str:
    with use_locale(controller.locale):
        return t(key, **(params or {"version": "0.6.0"}))


ONLINE = {"worker": "win-01", "sameVersion": False}


def test_restarts_when_idle(worker: WorkerController, harness: Harness) -> None:
    worker.on_update_ready = harness.restart
    worker.start()
    harness.push("online", ONLINE)
    assert wait_for(lambda: harness.restarts == ["restart"], 10)
    assert worker.paused  # 重新啟動前先停止領新任務
    assert message(worker) == (text(worker, "worker.update_restarting"), "info")
    assert worker.snapshot()["sameVersion"] is None  # 已經裝好，不用提示下載安裝檔


def test_waits_for_the_current_job(worker: WorkerController, harness: Harness) -> None:
    worker.on_update_ready = harness.restart
    worker.start()
    harness.push("online", ONLINE)
    harness.push("claimed", {"run": "r1", "headless": True, "engine": "chromium"})
    assert wait_for(lambda: worker.paused, 10)
    assert not wait_for(lambda: bool(harness.restarts), 1.5)
    harness.push("reported", {"run": "r1", "status": "passed"})
    assert wait_for(lambda: harness.restarts == ["restart"], 10)


def test_resume_cancels_the_restart(worker: WorkerController, harness: Harness) -> None:
    worker.on_update_ready = harness.restart
    worker.start()
    harness.push("online", ONLINE)
    harness.push("claimed", {"run": "r1", "headless": True, "engine": "chromium"})
    assert wait_for(lambda: worker.paused, 10)
    worker.set_paused(False)  # 使用者按了「繼續接任務」
    assert wait_for(
        lambda: message(worker) == (text(worker, "worker.update_next_start"), "info"), 10
    )
    harness.push("reported", {"run": "r1", "status": "passed"})
    harness.push("online", ONLINE)  # 再上線：同一個版本不再暫停
    assert harness.updater is not None
    assert wait_for(lambda: harness.updater is not None and harness.updater.checks == 2, 10)
    assert not wait_for(lambda: worker.paused or bool(harness.restarts), 1.5)


def test_next_start_without_a_window(worker: WorkerController, harness: Harness) -> None:
    worker.start()
    harness.push("online", ONLINE)
    assert wait_for(
        lambda: message(worker) == (text(worker, "worker.update_next_start"), "info"), 10
    )
    assert not worker.paused


def test_user_pause_is_kept(worker: WorkerController, harness: Harness) -> None:
    worker.on_update_ready = harness.restart
    worker.set_paused(True)
    worker.start()
    harness.push("online", ONLINE)
    assert wait_for(
        lambda: message(worker) == (text(worker, "worker.update_next_start"), "info"), 10
    )
    assert not wait_for(lambda: bool(harness.restarts), 1.5)


@pytest.mark.parametrize(
    ("result", "key", "params"),
    [
        (Checked(Offer("full", "0.6.0")), "worker.update_full", {}),
        (Checked(Offer("failed", "0.6.0")), "worker.update_failed", {}),
        (ConnectionLostError("timed out"), "worker.update_error", {"error": "timed out"}),
        (UpdateError("download_mismatch"), "worker.update_error", {"error": "download_mismatch"}),
        (WorkerApiError(500, "http_error", "boom"), "worker.update_error", {"error": "boom"}),
    ],
)
def test_problems_are_shown(
    worker: WorkerController,
    harness: Harness,
    result: Checked | Exception,
    key: str,
    params: dict[str, object],
) -> None:
    harness.updater = FakeUpdater(result)
    worker.start()
    harness.push("online", ONLINE)
    assert wait_for(lambda: message(worker) == (text(worker, key, **params), "warn"), 10)
    assert not worker.paused


def test_old_portal_without_updates_is_quiet(worker: WorkerController, harness: Harness) -> None:
    harness.updater = FakeUpdater(WorkerApiError(404, "http_error", "Not Found"))
    worker.start()
    harness.push("online", ONLINE)
    assert wait_for(lambda: harness.updater is not None and harness.updater.checks == 1, 10)
    assert not wait_for(lambda: message(worker) is not None, 0.5)


def test_protocol_mismatch_updates_and_restarts(worker: WorkerController, harness: Harness) -> None:
    worker.on_update_ready = harness.restart
    harness.fatal = "協定版本不同"
    worker.start()
    harness.push(
        "rejected", {"status": 409, "code": "protocol_mismatch", "message": "協定版本不同"}
    )
    assert wait_for(lambda: harness.restarts == ["restart"], 10)


# ---------------------------------------------------------------- RPA 錄製端


@dataclass
class FakeHost:
    notify: Notify
    events: Sequence[tuple[str, dict[str, object]]]

    def run(self, stop: threading.Event | None = None) -> str | None:
        assert stop is not None
        for event, details in self.events:
            self.notify(event, details)
        stop.wait(10)
        return None

    def active(self) -> int:
        return 0

    def stop_all(self) -> None:
        pass


def recorder(tmp_path: Path, store: MemoryStore, updater: FakeUpdater) -> RecorderController:
    credentials = Credentials(tmp_path, store)
    credentials.save(PairResult(SERVER, "mac-01", "Mac", "recorder", "tok", 1, None, None))
    events: list[tuple[str, dict[str, object]]] = [
        ("online", {"device": "mac-01", "sameVersion": False})
    ]

    def host(
        client: WorkerClient, info: Mapping[str, object], work: Path, notify: Notify
    ) -> FakeHost:
        return FakeHost(notify, events)

    worker_services = Harness().services()
    services = RecorderServices(
        pair=worker_services.pair,
        missing=worker_services.missing,
        download=worker_services.download,
        testsite=worker_services.testsite,
        detect=lambda name, fingerprint, version: WorkerInfo(
            name="mac", fingerprint=fingerprint, version=version, display=True
        ),
        host=host,
        updater=lambda app, version: updater,
    )
    return RecorderController(
        home=tmp_path,
        build=BuildInfo(app="recorder", version="0.5.0", fingerprint="fp", protocol=1),
        environ={},
        credentials=credentials,
        services=services,
        testsite=False,
    )


@pytest.mark.parametrize(
    ("result", "key", "level"),
    [
        (READY, "recorder.update_next_start", "info"),
        (Checked(Offer("full", "0.6.0")), "recorder.update_full", "warn"),
        (Checked(Offer("failed", "0.6.0")), "recorder.update_failed", "warn"),
    ],
)
def test_recorder_applies_next_time(
    tmp_path: Path, store: MemoryStore, result: Checked, key: str, level: str
) -> None:
    controller = recorder(tmp_path, store, FakeUpdater(result))
    controller.start()
    try:
        assert wait_for(lambda: message(controller) == (text(controller, key), level), 10)
        assert controller.snapshot()["sameVersion"] is (None if result.ready else False)
    finally:
        controller.stop()
        controller.wait(10)
