"""調試工作階段的子程序：一行一個 JSON 命令，一次執行一個步驟（M4）。"""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

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
    replies = [debug.send("step", index=index) for index in range(4)]
    for reply in replies:
        assert cast("dict[str, object]", reply["record"])["status"] == "passed", reply
    last = replies[-1]
    assert str(last["url"]).endswith("/")
    shot = last["screenshot"]
    assert isinstance(shot, str)
    assert (out / shot).is_file()

    debug.send("step", index=4)  # 等收據出現
    facts = cast("dict[str, object]", debug.send("step", index=5)["facts"])  # 讀取紀錄
    assert cast("dict[str, object]", facts["record"])["title"] == "調試範例"


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


def test_load_takes_the_scenario_text_and_keeps_the_browser(
    session: tuple[Session, Path],
) -> None:
    """換版本（v0.6.3）：命令直接帶場景內容與入參，子程序不讀伺服器的檔案（它可能在另一台電腦）；
    瀏覽器與已開的頁面保留，接著執行下一步。"""
    debug, _ = session
    assert cast("dict[str, object]", debug.send("step", index=0)["record"])["status"] == "passed"
    text = BA_001.read_text(encoding="utf-8").replace("name: 建立範例紀錄", "name: 建立範例紀錄 v2")
    loaded = debug.send(
        "load", revision=2, scenarioText=text, inputs={"title": "換版本之後", "quantity": 4}
    )
    assert loaded["ok"] is True, loaded
    assert loaded["steps"] == 7
    assert loaded["inputs"] == {"title": "換版本之後", "quantity": 4}
    # 頁面還開著：不必重跑第 1 步，直接填寫標題
    assert cast("dict[str, object]", debug.send("step", index=1)["record"])["status"] == "passed"

    # 校驗失敗：說出哪一行、哪個步驟，不只是「場景校驗失敗」；工作階段照常可用
    broken = text.replace("action: goto", "action: teleport", 1)
    rejected = debug.send("load", revision=3, scenarioText=broken, inputs={})
    assert rejected["ok"] is False
    assert str(rejected["error"]).startswith("場景校驗失敗：第 52 行"), rejected
    issues = cast("list[dict[str, object]]", rejected["issues"])
    assert issues[0]["line"] == 52
    assert issues[0]["stepId"] == "open"
    not_object = debug.send("load", revision=3, scenarioText=text, inputs=["x"])
    assert not_object["ok"] is False
    assert "issues" not in not_object
    assert cast("dict[str, object]", debug.send("step", index=2)["record"])["status"] == "passed"


def test_reset_and_unknown_command(session: tuple[Session, Path]) -> None:
    debug, _ = session
    debug.send("step", index=0)
    reset = debug.send("reset")
    assert reset["ok"] is True
    assert reset["facts"] == {}
    assert debug.send("dance")["ok"] is False
    assert debug.send("step", index=99)["ok"] is False


POPUP_FORM = ROOT / "scenarios" / "examples" / "popup-form.yaml"


def test_tabs_stay_open_between_steps(engine: str, tmp_path: Path) -> None:
    """新分頁（M7b）：開出的新分頁在步驟之間都在；截圖、網址與定位器測試在目前的分頁。"""
    inputs = tmp_path / "input.json"
    inputs.write_text(json.dumps({"item": "A-1"}), encoding="utf-8")
    with running() as site:
        command = [
            sys.executable, "-m", "rpa_runner.debug",
            "--scenario", str(POPUP_FORM), "--input", str(inputs),
            "--out", str(tmp_path / "debug"), "--engine", engine, "--base-url", site,
        ]  # fmt: skip
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8"
        )
        try:
            debug = Session(process)
            assert debug.read()["event"] == "ready"
            first = debug.send("step", index=0)
            assert str(first["url"]).endswith("/popup")
            opened = debug.send("step", index=1)  # 點連結：開出新分頁，目前分頁換成它
            assert cast("dict[str, object]", opened["record"])["status"] == "passed", opened
            assert str(opened["url"]).endswith("/popup/items")
            found = debug.send("locate", locator={"role": "button", "name": "新增商品行"})
            assert found["count"] == 1
            replies = [debug.send("step", index=index) for index in range(2, 6)]
            for reply in replies:
                record = cast("dict[str, object]", reply["record"])
                assert record["status"] == "passed", reply
            facts = cast("dict[str, object]", replies[-1]["facts"])
            assert facts["status"] == "已儲存：A-1"
            last = debug.send("step", index=6)  # 回到一開始的分頁
            assert cast("dict[str, object]", last["record"])["status"] == "passed", last
            assert str(last["url"]).endswith("/popup")
            # 從頭開始：新分頁不在了，在新分頁上的步驟說明要先開它
            debug.send("reset")
            missing = debug.send("step", index=2)
            record = cast("dict[str, object]", missing["record"])
            assert record["status"] == "failed"
            assert "items" in str(record["error"])
        finally:
            if process.poll() is None:
                assert process.stdin is not None
                process.stdin.write(json.dumps({"cmd": "close"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=30)


def test_snapshot_lists_fields_and_the_accessibility_tree(session: tuple[Session, Path]) -> None:
    """讀頁面結構（M14）：給 Agent 寫定位器用的欄位、無障礙樹，within 只看一部分。"""
    debug, _ = session
    debug.send("step", index=0)
    debug.send("step", index=1)  # 填標題
    shot = debug.send("snapshot")
    assert shot["ok"] is True
    assert str(shot["url"]).endswith("/")
    assert shot["title"] == "本機範例頁"
    fields = cast("list[dict[str, object]]", shot["fields"])
    visible = {str(field["label"]): field for field in fields if field["visible"]}
    assert visible["標題"]["role"] == "textbox"
    assert visible["標題"]["value"] == "調試範例"
    assert visible["標題"]["required"] is True
    assert visible["數量"]["role"] == "spinbutton"
    aria = str(shot["aria"])
    assert 'button "建立紀錄"' in aria
    assert shot["truncated"] is False
    tabs = cast("list[dict[str, object]]", shot["tabs"])
    assert tabs == [{"page": None, "url": shot["url"], "title": "本機範例頁", "active": True}]
    assert shot["frames"] == []

    part = debug.send("snapshot", within={"css": "#create-form"})
    assert "建立範例紀錄" in str(part["aria"])
    assert "範例紀錄" not in str(part["aria"]).replace("建立範例紀錄", "")
    missing = debug.send("snapshot", within={"css": "#does-not-exist"})
    assert missing["ok"] is False
    assert debug.send("snapshot", within={"role": "button", "css": "x"})["ok"] is False


def test_snapshot_masks_passwords_and_secrets(engine: str, tmp_path: Path) -> None:
    """密碼欄位與 Secrets 的值不離開調試子程序。"""
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text(
        "schemaVersion: 1\nid: snapshot-login\nname: 讀頁面結構\n"
        "secrets: [DEMO_SECRET]\n"
        "browser: { baseUrl: http://127.0.0.1:8765 }\n"
        "steps:\n"
        "  - { id: open, action: goto, url: /login }\n"
        "  - { id: user, action: fill, target: { label: 帳號 },"
        " value: '{{ secrets.DEMO_SECRET }}' }\n"
        "  - { id: password, action: fill, target: { label: 密碼 }, value: user-pass }\n",
        encoding="utf-8",
    )
    inputs = tmp_path / "input.json"
    inputs.write_text("{}", encoding="utf-8")
    with running() as site:
        command = [
            sys.executable, "-m", "rpa_runner.debug",
            "--scenario", str(scenario), "--input", str(inputs),
            "--out", str(tmp_path / "debug"), "--engine", engine, "--base-url", site,
        ]  # fmt: skip
        env = {**os.environ, "DEMO_SECRET": "manager-secret"}
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        try:
            debug = Session(process)
            assert debug.read()["event"] == "ready"
            for index in range(3):
                reply = debug.send("step", index=index)
                assert cast("dict[str, object]", reply["record"])["status"] == "passed", reply
            shot = debug.send("snapshot")
            text = json.dumps(shot, ensure_ascii=False)
            assert "manager-secret" not in text
            assert "user-pass" not in text
            fields = {
                str(field["label"]): field
                for field in cast("list[dict[str, object]]", shot["fields"])
            }
            assert fields["密碼"]["value"] == "***"
            assert fields["帳號"]["value"] == "***"
            assert fields["記住我"]["role"] == "checkbox"
            assert fields["記住我"]["checked"] is False
        finally:
            if process.poll() is None:
                assert process.stdin is not None
                process.stdin.write(json.dumps({"cmd": "close"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=30)


def test_file_inputs_given_by_the_portal(engine: str, tmp_path: Path) -> None:
    """M7c：管理 Portal 以原始檔名準備好的檔案用 --file 給；path 值在這台找、只能在允許的資料夾。"""
    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "scenario.yaml").write_text(
        "schemaVersion: 1\nid: debug-upload\nname: 調試上傳\n"
        "browser: { baseUrl: http://127.0.0.1:8765 }\n"
        "inputs:\n"
        "  orders: { type: file }\n"
        "  photos: { type: file, multiple: true }\n"
        "steps:\n"
        "  - { id: open, action: goto, url: /upload }\n"
        "  - { id: pick, action: upload, target: { label: 匯入檔案 },"
        ' files: "{{ inputs.orders }}" }\n'
        "  - { id: send, action: click, target: { role: button, name: 匯入, exact: true } }\n"
        "  - id: read\n"
        "    action: extract\n"
        "    target: { css: '#import-result .name' }\n"
        "    as: imported\n"
        "  - id: photos\n"
        "    action: upload\n"
        "    target: { css: 'input[type=file]', within: { role: button, name: 點擊上傳圖片 } }\n"
        '    files: "{{ inputs.photos }}"\n',
        encoding="utf-8",
    )
    given = tmp_path / "debug" / "input-files" / "orders" / "0" / "十月訂單.csv"
    given.parent.mkdir(parents=True)
    given.write_bytes("編號\nA-1\n".encode())
    share = tmp_path / "share"
    share.mkdir()
    (share / "a.png").write_bytes(b"\x89PNG fake")
    inputs = tmp_path / "input.json"
    inputs.write_text(
        json.dumps(
            {
                "orders": {"file": "0123456789abcdef0123456789abcdef", "name": "十月訂單.csv"},
                "photos": [{"path": str(share / "a.png")}],
            }
        ),
        encoding="utf-8",
    )
    with running() as site:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "rpa_runner.debug",
                "--scenario",
                str(scene / "scenario.yaml"),
                "--input",
                str(inputs),
                "--out",
                str(tmp_path / "debug"),
                "--engine",
                engine,
                "--base-url",
                site,
                "--file",
                "orders",
                str(given),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "RPA_INPUT_FOLDERS": str(share)},
        )
        try:
            debug = Session(process)
            ready = debug.read()
            assert ready["event"] == "ready", ready
            resolved = cast("dict[str, object]", ready["inputs"])
            assert cast("dict[str, object]", resolved["orders"])["name"] == "十月訂單.csv"
            assert "path" not in json.dumps(resolved)
            replies = [debug.send("step", index=index) for index in range(5)]
            for reply in replies:
                assert cast("dict[str, object]", reply["record"])["status"] == "passed", reply
            assert cast("dict[str, object]", replies[3]["facts"])["imported"] == "十月訂單.csv"
            assert cast("dict[str, object]", replies[4]["record"])["files"] == ["a.png"]
        finally:
            if process.poll() is None:
                assert process.stdin is not None
                process.stdin.write(json.dumps({"cmd": "close"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=30)


def test_path_outside_the_allowed_folders_is_refused(tmp_path: Path) -> None:
    scene = tmp_path / "scenario.yaml"
    scene.write_text(
        "schemaVersion: 1\nid: debug-upload\nname: 調試上傳\n"
        "inputs:\n  f: { type: file }\n"
        "steps:\n  - { id: open, action: goto, url: about:blank }\n",
        encoding="utf-8",
    )
    inputs = tmp_path / "input.json"
    inputs.write_text(json.dumps({"f": {"path": str(scene)}}), encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "rpa_runner.debug",
            "--scenario",
            str(scene),
            "--input",
            str(inputs),
            "--out",
            str(tmp_path / "out"),
        ],
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "RPA_INPUT_FOLDERS": "", "RPA_LANG": "zh-Hant"},
        timeout=120,
        check=False,
    )
    first = json.loads(process.stdout.splitlines()[0])
    assert first["event"] == "error"
    assert "不在允許讀取的資料夾裡" in first["error"]
