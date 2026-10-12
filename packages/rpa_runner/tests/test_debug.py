"""調試工作階段的子程序：一行一個 JSON 命令，一次執行一個步驟（M4）。"""

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


class Session:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.number = 0

    def read(self) -> dict[str, object]:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        assert line, "子程序沒有回覆"
        return json.loads(line)

    def send(self, cmd: str, **fields: object) -> dict[str, object]:
        assert self.process.stdin is not None
        self.number += 1
        self.process.stdin.write(json.dumps({"id": self.number, "cmd": cmd, **fields}) + "\n")
        self.process.stdin.flush()
        reply = self.read()
        assert reply["id"] == self.number
        return reply


@pytest.fixture
def session(engine: str, tmp_path: Path) -> Iterator[tuple[Session, Path]]:
    inputs = tmp_path / "input.json"
    inputs.write_text(json.dumps({"title": "調試範例", "quantity": 3}), encoding="utf-8")
    out = tmp_path / "debug"
    with running() as site:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "rpa_runner.debug",
                "--scenario",
                str(BA_001),
                "--input",
                str(inputs),
                "--out",
                str(out),
                "--engine",
                engine,
                "--base-url",
                site,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            debug = Session(process)
            ready = debug.read()
            assert ready["event"] == "ready"
            assert ready["steps"] == 7
            yield debug, out
        finally:
            if process.poll() is None:
                assert process.stdin is not None
                process.stdin.write(json.dumps({"cmd": "close"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=30)


def test_steps_one_at_a_time(session: tuple[Session, Path]) -> None:
    debug, out = session
    for index in range(4):
        reply = debug.send("step", index=index)
        record = reply["record"]
        assert isinstance(record, dict)
        assert record["status"] == "passed", record
    assert str(reply["url"]).endswith("/")
    shot = reply["screenshot"]
    assert isinstance(shot, str)
    assert (out / shot).is_file()

    reply = debug.send("step", index=4)  # 等收據出現
    reply = debug.send("step", index=5)  # 讀取紀錄
    facts = reply["facts"]
    assert isinstance(facts, dict)
    record = facts["record"]
    assert isinstance(record, dict)
    assert record["title"] == "調試範例"


def test_failed_step_does_not_end_the_session(session: tuple[Session, Path]) -> None:
    debug, _ = session
    reply = debug.send("step", index=4)  # 還沒開頁面就等收據：逾時失敗
    record = reply["record"]
    assert isinstance(record, dict)
    assert record["status"] == "failed"
    assert record["error"]
    assert debug.send("step", index=0)["ok"] is True


def test_locator_tester_counts_and_highlights(session: tuple[Session, Path]) -> None:
    debug, out = session
    debug.send("step", index=0)
    found = debug.send("locate", locator={"role": "button", "name": "建立紀錄"})
    assert found["count"] == 1
    matches = found["matches"]
    assert isinstance(matches, list)
    assert matches[0] == {"tag": "button", "text": "建立紀錄"}
    assert (out / str(found["screenshot"])).is_file()

    none = debug.send("locate", locator={"css": "#does-not-exist"})
    assert none["count"] == 0
    invalid = debug.send("locate", locator={"role": "button", "css": "x"})
    assert invalid["ok"] is False


def test_reset_and_unknown_command(session: tuple[Session, Path]) -> None:
    debug, _ = session
    debug.send("step", index=0)
    reset = debug.send("reset")
    assert reset["ok"] is True
    assert reset["facts"] == {}
    assert debug.send("dance")["ok"] is False
    assert debug.send("step", index=99)["ok"] is False
