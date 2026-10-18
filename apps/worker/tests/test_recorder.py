"""錄製端執行互動子程序（rpa_worker.recorder，M10.2）：對一個假的 Client API 測試。

子程序用一個小腳本代替真的 rpa_runner 模組（不需要瀏覽器），檢查：參數與環境變數裡的工作資料夾、
送來的檔案、檔案先於那一行輸出傳回、標準輸入、結束碼、結束子程序、404 時停止、權杖被拒。
"""

import base64
import io
import json
import sys
import threading
import time
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rpa_worker.interactive import WORK
from rpa_worker.pairing import CLIENT_API_PREFIX
from rpa_worker.recorder import RecorderHost, translate
from rpa_worker.remote import WorkerClient

TOKEN = "recorder-token"

CHILD = r"""
import json, os, sys, time
mode = sys.argv[1]
if mode == "echo":
    scenario, out = sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "result.txt"), "w", encoding="utf-8") as handle:
        handle.write(open(scenario, encoding="utf-8").read() + "|" + os.environ["RPA_TEST_SECRET"]
                     + "|" + open(os.environ["RPA_TEST_STATE"], encoding="utf-8").read())
    print("ready", flush=True)
    for line in sys.stdin:
        print("got:" + line.strip(), flush=True)
    sys.exit(3)
if mode == "sleep":
    print("sleeping", flush=True)
    time.sleep(60)
if mode == "quiet":
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        handle.write("recorded")
    sys.exit(0)
"""


@dataclass
class FakeClientApi:
    """假的 Client API：依序交出指令，記下收到的事件（檔案、輸出）。"""

    commands: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    events: list[tuple[str, str, object]] = field(default_factory=list[tuple[str, str, object]])
    files: dict[str, dict[str, bytes]] = field(default_factory=dict[str, dict[str, bytes]])
    hellos: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    gone: set[str] = field(default_factory=set[str])
    hello_status: int = 200
    condition: threading.Condition = field(default_factory=threading.Condition)

    def add(self, command: dict[str, object]) -> None:
        with self.condition:
            command["seq"] = len(self.commands) + 1
            self.commands.append(command)
            self.condition.notify_all()

    def wait_for(self, check: Callable[[], bool], timeout: float = 20) -> None:
        deadline = time.monotonic() + timeout
        with self.condition:
            while not check():
                assert time.monotonic() < deadline, f"逾時；事件：{self.events}"
                self.condition.wait(0.05)  # 有些變化（例如資料夾刪掉）不會通知：常常再看一次

    def outputs(self, process: str) -> list[object]:
        return [value for kind, item, value in self.events if kind == "output" and item == process]

    def serve(self) -> ThreadingHTTPServer:
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return None

            def reply(self, status: int, payload: object = None) -> None:
                data = json.dumps(payload or {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                assert self.headers["Authorization"] == f"Bearer {TOKEN}"
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                path = self.path.removeprefix(CLIENT_API_PREFIX)
                if path == "/hello":
                    api.hellos.append(body)
                    if api.hello_status != 200:
                        error = {"code": "recorder_unauthorized", "message": "權杖不對"}
                        return self.reply(api.hello_status, {"error": error})
                    return self.reply(200, {"device": "mac-01", "sameVersion": True})
                if path == "/control":
                    after = int(body.get("after", 0))
                    deadline = time.monotonic() + 0.3
                    with api.condition:
                        while len(api.commands) <= after and time.monotonic() < deadline:
                            api.condition.wait(0.05)
                        pending = api.commands[after:]
                    return self.reply(200, {"commands": pending})
                process = path.split("/")[2]
                if process in api.gone:
                    with api.condition:
                        api.events.append(("gone", process, body))
                        api.condition.notify_all()
                    error = {"code": "process_not_found", "message": "gone"}
                    return self.reply(404, {"error": error})
                with api.condition:
                    api.events.append(("output", process, body))
                    api.condition.notify_all()
                return self.reply(204)

            def do_PUT(self) -> None:
                process = self.path.removeprefix(CLIENT_API_PREFIX).split("/")[2]
                data = self.rfile.read(int(self.headers["Content-Length"]))
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    names = archive.namelist()
                    stored = api.files.setdefault(process, {})
                    for name in names:
                        stored[name] = archive.read(name)
                with api.condition:
                    api.events.append(("files", process, sorted(names)))
                    api.condition.notify_all()
                return self.reply(204)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


@dataclass
class Running:
    api: FakeClientApi
    host: RecorderHost
    stop: threading.Event
    thread: threading.Thread
    result: list[str | None]


@pytest.fixture
def running(tmp_path: Path) -> Iterator[Running]:
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    api = FakeClientApi()
    server = api.serve()
    client = WorkerClient(
        f"http://127.0.0.1:{server.server_address[1]}", TOKEN, prefix=CLIENT_API_PREFIX
    )

    def command(module: str, args: Sequence[str]) -> list[str]:
        assert module == "rpa_runner.fake"
        return [sys.executable, str(script), *args]

    host = RecorderHost(
        client,
        {"protocol": 1, "fingerprint": "f", "browsers": ["chromium"], "display": True},
        tmp_path / "work",
        command=command,
        wait_seconds=0.3,
    )
    stop = threading.Event()
    result: list[str | None] = []
    thread = threading.Thread(target=lambda: result.append(host.run(stop)), daemon=True)
    thread.start()
    try:
        yield Running(api, host, stop, thread, result)
    finally:
        stop.set()
        thread.join(20)
        server.shutdown()
        server.server_close()


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_translate() -> None:
    folder = Path("/tmp/rpa-x")
    assert translate(WORK, folder) == str(folder)
    assert translate(f"{WORK}/out/a.png", folder) == str(folder / "out" / "a.png")
    assert translate(f"{WORK}/../etc", folder) == f"{WORK}/../etc"
    assert translate("chromium", folder) == "chromium"


def test_runs_a_child_and_syncs_files_first(running: Running) -> None:
    api = running.api
    api.wait_for(lambda: bool(api.hellos))
    assert api.hellos[0]["boot"] == running.host.boot
    api.add(
        {
            "type": "start",
            "process": "p1",
            "module": "rpa_runner.fake",
            "args": ["echo", f"{WORK}/scenario.yaml", f"{WORK}/out"],
            "env": {"RPA_TEST_SECRET": "s3cret", "RPA_TEST_STATE": f"{WORK}/.inputs/0-state.json"},
            "files": {"scenario.yaml": b64("steps"), ".inputs/0-state.json": b64("{}")},
            "pipes": True,
            "log": "debug.log",
        }
    )
    api.wait_for(lambda: len(api.outputs("p1")) >= 1)
    # 那一行之前，子程序寫的檔案已經傳回（送來的檔案沒改，不傳回）
    first_files = next(index for index, event in enumerate(api.events) if event[0] == "files")
    first_output = next(index for index, event in enumerate(api.events) if event[0] == "output")
    assert first_files < first_output
    assert api.files["p1"]["out/result.txt"] == b"steps|s3cret|{}"
    assert "scenario.yaml" not in api.files["p1"]
    assert not any(name.startswith(".inputs") for name in api.files["p1"])
    assert api.outputs("p1")[0] == {"lines": ["ready"]}
    folder = next((running.host.work_dir).glob("rpa-p1-*"))
    api.add({"type": "input", "process": "p1", "line": "hello"})
    api.wait_for(lambda: {"lines": ["got:hello"]} in api.outputs("p1"))
    api.add({"type": "close", "process": "p1"})
    api.wait_for(lambda: any("exit" in item for item in api.outputs("p1")))  # type: ignore[operator]
    assert api.outputs("p1")[-1] == {"lines": [], "exit": 3}
    assert "debug.log" in api.files["p1"]
    api.wait_for(lambda: not folder.exists())  # 暫存資料夾（Secrets、登入狀態）刪掉了
    assert running.host.active() == 0


def test_child_without_pipes_reports_files_at_exit(running: Running) -> None:
    api = running.api
    api.add(
        {
            "type": "start",
            "process": "p2",
            "module": "rpa_runner.fake",
            "args": ["quiet", f"{WORK}/.recording.py"],
            "pipes": False,
            "log": "codegen.log",
        }
    )
    api.wait_for(lambda: bool(api.outputs("p2")))
    assert api.outputs("p2") == [{"lines": [], "exit": 0}]
    assert api.files["p2"][".recording.py"] == b"recorded"


def test_kill_ends_the_child(running: Running) -> None:
    api = running.api
    api.add(
        {
            "type": "start",
            "process": "p3",
            "module": "rpa_runner.fake",
            "args": ["sleep"],
            "pipes": True,
            "log": "debug.log",
        }
    )
    api.wait_for(lambda: bool(api.outputs("p3")))
    started = time.monotonic()
    api.add({"type": "kill", "process": "p3"})
    api.wait_for(lambda: any("exit" in item for item in api.outputs("p3")))  # type: ignore[operator]
    assert time.monotonic() - started < 15
    assert api.outputs("p3")[-1]["exit"] != 0  # type: ignore[index]


def test_gone_on_the_server_kills_the_child(running: Running) -> None:
    api = running.api
    api.gone.add("p4")
    api.add(
        {
            "type": "start",
            "process": "p4",
            "module": "rpa_runner.fake",
            "args": ["sleep"],
            "pipes": True,
            "log": "debug.log",
        }
    )
    api.wait_for(lambda: any(kind == "gone" for kind, _, _ in api.events))
    api.wait_for(lambda: running.host.active() == 0)  # 回報時得到 404：結束子程序
    assert api.outputs("p4") == []


def test_bad_start_is_reported(running: Running) -> None:
    api = running.api
    api.add(
        {"type": "start", "process": "p5", "module": "rpa_runner.fake", "files": {"../x": b64("")}}
    )
    api.wait_for(lambda: bool(api.outputs("p5")))
    reply = api.outputs("p5")[0]
    assert reply["exit"] == 1  # type: ignore[index]
    assert "unsafe file name" in reply["error"]  # type: ignore[index]


def test_rejected_token_stops(tmp_path: Path) -> None:
    api = FakeClientApi(hello_status=401)
    server = api.serve()
    client = WorkerClient(
        f"http://127.0.0.1:{server.server_address[1]}", TOKEN, prefix=CLIENT_API_PREFIX
    )
    events: list[str] = []
    host = RecorderHost(
        client,
        {"protocol": 1},
        tmp_path / "work",
        notify=lambda event, details: events.append(event),
    )
    try:
        assert host.run() == "權杖不對"
    finally:
        server.shutdown()
        server.server_close()
    assert events == ["rejected"]


def test_needs_the_client_api(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Client API"):
        RecorderHost(WorkerClient("http://127.0.0.1:1", TOKEN), {}, tmp_path)
