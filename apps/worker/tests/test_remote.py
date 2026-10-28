"""遠端 worker 的任務來源：對一個假的 Worker API（標準函式庫的 HTTP 伺服器）測試（M9a）。

不需要瀏覽器：入參不合規則的任務只跑入參校驗；要「執行很久」的情境用假的執行器。
"""

import base64
import hashlib
import io
import json
import threading
import time
import zipfile
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rpa_core.dsl import validate_file
from rpa_core.i18n import use_locale
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName, scenario_digest
from rpa_worker import Worker
from rpa_worker.environment import WorkerInfo
from rpa_worker.protocol import API_PREFIX, InputFile, JobPayload
from rpa_worker.remote import RemoteJobSource, WorkerClient

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"
TOKEN = "t0ken"


@dataclass
class FakeApi:
    """假的 Worker API：記下收到的請求，依測試設定回應。"""

    jobs: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    calls: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    hellos: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    heartbeats: list[tuple[str, object]] = field(default_factory=list[tuple[str, object]])
    artifacts: dict[str, dict[str, bytes]] = field(default_factory=dict[str, dict[str, bytes]])
    role_states: dict[str, bytes] = field(default_factory=dict[str, bytes])
    finished: dict[str, dict[str, object]] = field(default_factory=dict[str, dict[str, object]])
    failed: dict[str, dict[str, object]] = field(default_factory=dict[str, dict[str, object]])
    cancel: set[str] = field(default_factory=set[str])
    gone: set[str] = field(default_factory=set[str])
    """這些執行回 409（例如已經判定 worker 失聯）。"""
    downloads: dict[str, bytes] = field(default_factory=dict[str, bytes])
    """上傳檔（M7c）：代號 → 內容；GET /runs/<執行>/files/<代號> 回傳它。"""
    reject_token: bool = False
    fingerprint: str = "same"
    done: threading.Event = field(default_factory=threading.Event)

    def handle(self, method: str, path: str, body: bytes, token: str) -> tuple[int, object]:
        self.calls.append((method, path))
        if token != TOKEN or self.reject_token:
            return 401, {"error": {"code": "worker_unauthorized", "message": "bad token"}}
        if path == "/hello":
            self.hellos.append(json.loads(body))
            return 200, {"worker": "win-01", "fingerprint": self.fingerprint}
        if path == "/claim":
            if self.jobs:
                return 200, self.jobs.pop(0)
            time.sleep(0.05)
            return 204, None
        parts = path.split("/")  # ["", "runs", id, action]
        run_id, action = parts[2], parts[3]
        if run_id in self.gone:
            return 409, {"error": {"code": "run_not_assigned", "message": "gone"}}
        if method == "GET" and action == "files":
            content = self.downloads.get(parts[4])
            if content is None:
                return 404, {"error": {"code": "upload_not_found", "message": parts[4]}}
            return 200, content
        if action == "heartbeat":
            self.heartbeats.append((run_id, json.loads(body).get("stage")))
            return 200, {"cancel": run_id in self.cancel}
        if action == "artifacts":
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                self.artifacts[run_id] = {name: archive.read(name) for name in archive.namelist()}
            return 204, None
        if action == "role-state":
            self.role_states[run_id] = body
            return 204, None
        if action == "finish":
            self.finished[run_id] = json.loads(body)["result"]
            self.done.set()
            return 204, None
        if action == "fail":
            self.failed[run_id] = json.loads(body)
            self.done.set()
            return 204, None
        return 404, {"error": {"code": "not_found", "message": path}}


@contextmanager
def serving(api: FakeApi) -> Generator[str]:
    class Handler(BaseHTTPRequestHandler):
        def reply(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            path = self.path.removeprefix(API_PREFIX)
            status, data = api.handle(self.command, path, body, token)
            binary = isinstance(data, bytes)
            raw = (
                data
                if isinstance(data, bytes)
                else b""
                if data is None
                else json.dumps(data).encode()
            )
            self.send_response(status)
            self.send_header(
                "Content-Type", "application/octet-stream" if binary else "application/json"
            )
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            self.reply()

        def do_PUT(self) -> None:
            self.reply()

        def do_GET(self) -> None:
            self.reply()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def job_json(run_id: str, **changes: object) -> dict[str, object]:
    files = {"scenario.yaml": BA_001.read_bytes()}
    values: dict[str, object] = {
        "run_id": run_id,
        "files": files,
        "inputs": {"title": "遠端", "quantity": 100},  # 超過上限：只跑入參校驗
        "locale": "en",
    }
    values.update(changes)
    return JobPayload(**values).to_json()  # pyright: ignore[reportArgumentType]


INFO = WorkerInfo(name="win-01", fingerprint="same", browsers=("chromium",), display=True)


def make_source(
    url: str, tmp_path: Path, events: list[tuple[str, Mapping[str, object]]], **options: object
) -> RemoteJobSource:
    source = RemoteJobSource(
        WorkerClient(url, TOKEN, timeout=5),
        INFO,
        tmp_path / "work",
        notify=lambda event, details: events.append((event, details)),
        heartbeat_seconds=0.1,
        claim_wait_seconds=0.2,
        **options,  # pyright: ignore[reportArgumentType]
    )
    return source


def test_job_runs_and_reports_artifacts_and_result(tmp_path: Path) -> None:
    api = FakeApi(jobs=[job_json("ba-001-remote-1")])
    events: list[tuple[str, Mapping[str, object]]] = []
    with serving(api) as url:
        source = make_source(url, tmp_path, events)
        assert Worker(source).run_once() is True

    assert api.hellos[0]["name"] == "win-01"
    assert api.calls[0] == ("POST", "/hello")
    result = api.finished["ba-001-remote-1"]
    assert result["status"] == "failed"
    # 任務帶著管理 Portal 的語言
    assert result["problems"] == ["Input quantity does not satisfy maximum: 30"]
    # 雜湊對位元組算，和管理 Portal 的版本（scenario.yaml）一致
    copy = tmp_path / "copy" / "scenario.yaml"
    copy.parent.mkdir()
    copy.write_bytes(BA_001.read_bytes())
    scenario = validate_file(copy).scenario
    assert scenario is not None
    assert result["scenarioHash"] == scenario_digest(copy, scenario)
    files = api.artifacts["ba-001-remote-1"]
    assert {"result.json", "report.html", "input.json"} <= set(files)
    # 上傳後刪除本機的暫存與執行目錄
    assert not (tmp_path / "work" / "jobs" / "ba-001-remote-1").exists()
    assert not (tmp_path / "work" / "runs" / "ba-001-remote-1").exists()
    assert [event for event, _ in events] == ["online", "claimed", "reported", "done"]
    assert events[-1][1] == {"run": events[1][1]["run"]}  # 這台的執行結束了（不論有沒有送達）
    assert events[0][1]["sameVersion"] is True


def test_keep_runs_keeps_the_local_run_directory(tmp_path: Path) -> None:
    api = FakeApi(jobs=[job_json("ba-001-remote-2")])
    with serving(api) as url:
        source = make_source(url, tmp_path, [], keep_runs=True)
        Worker(source).run_once()

    assert (tmp_path / "work" / "runs" / "ba-001-remote-2" / "result.json").exists()


def test_no_job_returns_false(tmp_path: Path) -> None:
    api = FakeApi()
    with serving(api) as url:
        assert Worker(make_source(url, tmp_path, [])).run_once() is False


def test_fingerprint_mismatch_is_reported(tmp_path: Path) -> None:
    api = FakeApi(fingerprint="other")
    events: list[tuple[str, Mapping[str, object]]] = []
    with serving(api) as url:
        make_source(url, tmp_path, events).claim()

    assert events[0][0] == "online"
    assert events[0][1]["sameVersion"] is False


class SlowExecutor:
    """假的執行器：回報階段後一直等到被取消。"""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.started = threading.Event()
        self.state_seen: bytes | None = None
        self.new_state: bytes | None = None

    def __call__(
        self,
        path: Path,
        inputs: Mapping[str, object],
        *,
        out_root: Path,
        cancel: threading.Event | None = None,
        on_stage: Callable[[StageName], None] | None = None,
        login: LoginSettings | None = None,
        run_id: str | None = None,
        **_: object,
    ) -> RunResult:
        assert on_stage is not None
        assert cancel is not None
        assert run_id is not None
        if login is not None and login.state.exists():
            self.state_seen = login.state.read_bytes()
            if self.new_state is not None:
                login.state.write_bytes(self.new_state)
        on_stage("automation")
        self.started.set()
        cancelled = cancel.wait(10)
        folder = out_root / run_id
        folder.mkdir(parents=True)
        (folder / "result.json").write_text("{}", encoding="utf-8")
        return RunResult(
            run_id=run_id,
            scenario_id="ba-001",
            scenario_name="x",
            scenario_hash="h",
            kind="dsl",
            engine="chromium",
            directory=folder,
            started_at="2026-10-13T00:00:00+00:00",
            status="cancelled" if cancelled else "passed",
            role=login.role if login is not None else None,
        )


def test_heartbeat_reports_stage_and_cancel_request_stops_the_job(tmp_path: Path) -> None:
    api = FakeApi(jobs=[job_json("ba-001-remote-3")])
    executor = SlowExecutor(tmp_path)
    with serving(api) as url:
        source = make_source(url, tmp_path, [])
        worker = Worker(source, executor=executor)
        source.on_cancel = worker.cancel
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        assert executor.started.wait(10)
        deadline = time.monotonic() + 5
        while ("ba-001-remote-3", "automation") not in api.heartbeats:
            assert time.monotonic() < deadline, api.heartbeats
            time.sleep(0.05)
        api.cancel.add("ba-001-remote-3")
        thread.join(10)

    assert api.finished["ba-001-remote-3"]["status"] == "cancelled"


def test_run_taken_away_is_abandoned(tmp_path: Path) -> None:
    api = FakeApi(jobs=[job_json("ba-001-remote-4")])
    executor = SlowExecutor(tmp_path)
    events: list[tuple[str, Mapping[str, object]]] = []
    with serving(api) as url:
        source = make_source(url, tmp_path, events)
        worker = Worker(source, executor=executor)
        source.on_cancel = worker.cancel
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        assert executor.started.wait(10)
        api.gone.add("ba-001-remote-4")
        thread.join(10)

    assert "ba-001-remote-4" not in api.finished
    assert "ba-001-remote-4" not in api.artifacts
    assert [event for event, _ in events[-2:]] == ["abandoned", "done"]


def login_job(run_id: str) -> dict[str, object]:
    login = LoginSettings(role="clerk", state=Path("ignored"), check_url="http://x/")
    return job_json(run_id, login=login, login_state=b'{"cookies": [1]}')


def test_login_state_is_written_privately_and_returned_when_changed(tmp_path: Path) -> None:
    api = FakeApi(jobs=[login_job("ba-001-remote-5")])
    executor = SlowExecutor(tmp_path)
    executor.new_state = b'{"cookies": [2]}'
    with serving(api) as url:
        source = make_source(url, tmp_path, [])
        worker = Worker(source, executor=executor)
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        assert executor.started.wait(10)
        worker.cancel("ba-001-remote-5")
        thread.join(10)

    assert executor.state_seen == b'{"cookies": [1]}'
    assert api.role_states["ba-001-remote-5"] == b'{"cookies": [2]}'
    assert not (tmp_path / "work" / "jobs" / "ba-001-remote-5").exists()


def test_unchanged_login_state_is_not_sent(tmp_path: Path) -> None:
    api = FakeApi(jobs=[login_job("ba-001-remote-6")])
    executor = SlowExecutor(tmp_path)
    with serving(api) as url:
        source = make_source(url, tmp_path, [])
        worker = Worker(source, executor=executor)
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        assert executor.started.wait(10)
        worker.cancel("ba-001-remote-6")
        thread.join(10)

    assert "ba-001-remote-6" in api.finished
    assert api.role_states == {}


def test_scenario_that_cannot_run_is_reported_as_failure(tmp_path: Path) -> None:
    broken = {"scenario.yaml": base64.b64encode(b"id: [").decode()}
    api = FakeApi(jobs=[{**job_json("ba-001-remote-7"), "files": broken}])
    with serving(api) as url:
        Worker(make_source(url, tmp_path, [])).run_once()

    assert api.failed["ba-001-remote-7"]["kind"] == "scenario_invalid"


def test_unsafe_job_is_refused(tmp_path: Path) -> None:
    job = job_json("ba-001-remote-8")
    job["files"] = {"scenario.yaml": "eA==", "../evil.py": "eA=="}
    api = FakeApi(jobs=[job])
    with serving(api) as url:
        assert Worker(make_source(url, tmp_path, [])).run_once() is False

    assert api.failed["ba-001-remote-8"]["kind"] == "crashed"
    assert not (tmp_path / "work" / "evil.py").exists()


def test_rejected_token_stops_the_worker(tmp_path: Path) -> None:
    api = FakeApi(reject_token=True)
    events: list[tuple[str, Mapping[str, object]]] = []
    fatal: list[str] = []
    with serving(api) as url:
        source = make_source(url, tmp_path, events)
        source.on_fatal = fatal.append
        assert source.claim() is None
        assert source.claim() is None  # 被拒之後不再連線

    assert fatal == ["bad token"]
    assert [event for event, _ in events] == ["rejected"]
    assert api.calls == [("POST", "/hello")]


def test_offline_server_is_retried_and_reported_once(tmp_path: Path) -> None:
    events: list[tuple[str, Mapping[str, object]]] = []
    with serving(FakeApi()) as url:
        pass  # 取得一個沒有人在聽的埠號
    source = make_source(url, tmp_path, events)
    source._backoff = 0.01  # pyright: ignore[reportPrivateUsage]
    with use_locale("en"):
        assert source.claim() is None
        assert source.claim() is None

    assert [event for event, _ in events] == ["offline"]


# ---------------------------------------------------------------- 上傳檔（M7c）

FILE_ID = "0123456789abcdef0123456789abcdef"
ORDERS = "編號,數量\nA-1,2\n".encode()


class FileExecutor:
    """假的執行器：記下收到的上傳檔位置與內容（檔案入參的 kwargs）。"""

    def __init__(self) -> None:
        self.seen: dict[str, bytes] = {}
        self.options: dict[str, object] = {}

    def __call__(
        self,
        path: Path,
        inputs: Mapping[str, object],
        *,
        out_root: Path,
        run_id: str | None = None,
        uploads: Mapping[str, Path] | None = None,
        **options: object,
    ) -> RunResult:
        assert run_id is not None
        self.seen = {key: value.read_bytes() for key, value in (uploads or {}).items()}
        self.options = dict(options)
        folder = out_root / run_id
        folder.mkdir(parents=True)
        return RunResult(
            run_id=run_id,
            scenario_id="ba-001",
            scenario_name="x",
            scenario_hash="h",
            kind="dsl",
            engine="chromium",
            directory=folder,
            started_at="2026-10-27T00:00:00+00:00",
            status="passed",
        )


def file_job(run_id: str, content: bytes = ORDERS) -> dict[str, object]:
    digest = hashlib.sha256(content).hexdigest()
    return job_json(
        run_id,
        inputs={"orders": {"file": FILE_ID, "name": "訂單.csv"}},
        input_files=(InputFile(FILE_ID, len(content), digest),),
        max_file_bytes=1024,
    )


def test_input_files_are_downloaded_before_the_run(tmp_path: Path) -> None:
    api = FakeApi(jobs=[file_job("ba-001-files-1")], downloads={FILE_ID: ORDERS})
    executor = FileExecutor()
    with serving(api) as url:
        assert Worker(make_source(url, tmp_path, []), executor=executor).run_once()

    assert ("GET", f"/runs/ba-001-files-1/files/{FILE_ID}") in api.calls
    assert executor.seen == {FILE_ID: ORDERS}
    assert executor.options["max_file_bytes"] == 1024
    assert "max_run_bytes" not in executor.options  # 沒給的不傳，runner 用自己的預設
    assert api.finished["ba-001-files-1"]["status"] == "passed"
    assert not (tmp_path / "work" / "jobs" / "ba-001-files-1").exists()


def test_input_file_that_does_not_match_fails_the_run(tmp_path: Path) -> None:
    api = FakeApi(
        jobs=[file_job("ba-001-files-2"), file_job("ba-001-files-3")],
        downloads={FILE_ID: ORDERS.replace(b"2", b"3")},
    )
    executor = FileExecutor()
    with serving(api) as url:
        source = make_source(url, tmp_path, [])
        # 下載不符時任務回報失敗、不交給執行器（這一輪沒有執行）
        assert Worker(source, executor=executor).run_once() is False
        api.downloads.clear()  # 第二個：伺服器上已經沒有這個檔案
        assert Worker(source, executor=executor).run_once() is False

    assert executor.seen == {}  # 沒有開始執行
    assert api.failed["ba-001-files-2"]["kind"] == "input_files"
    assert "sha256" in str(api.failed["ba-001-files-2"]["detail"])
    assert api.failed["ba-001-files-3"]["kind"] == "input_files"
    assert not list((tmp_path / "work" / "jobs").glob("*/inputs/*"))
