"""RPA Worker 的 worker 模式（M10.1）：資料夾與瀏覽器的位置、配對（邀請、存下的配對、詢問）、
下載瀏覽器、事件文字，以及打包後的入口分流。

不連真的管理 Portal：配對的 HTTP 在 apps/worker 的 test_pairing.py；打包版真的配對並執行場景
在 CI 的桌面端建置（tools/desktop_e2e.py）。
"""

import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_desktop import entry, worker_app
from rpa_desktop.build_info import App, BuildInfo
from rpa_desktop.worker_app import (
    BROWSERS_ENV,
    ENV_HOME,
    browsers_dir,
    data_dir,
    describe_event,
    ensure_browsers_path,
    obtain_credentials,
    prepare_browsers,
)
from rpa_worker.pairing import Invite, PairResult, load_pairing, save_pairing
from rpa_worker.remote import ConnectionLostError, WorkerApiError

CODE = "abcdefghijklmnopqrstuvwxyz012345"
LINE = Invite("http://192.168.1.10:8081", CODE, "worker").line()


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def result(server: str = "http://192.168.1.10:8081", token: str = "tok") -> PairResult:
    return PairResult(server, "win-01", "Windows", "worker", token, 1, "f", "0.1.0")


def test_folders_follow_the_platform() -> None:
    windows = {"LOCALAPPDATA": r"C:\Users\amy\AppData\Local", "USERPROFILE": r"C:\Users\amy"}
    assert data_dir(windows, "win32") == Path(windows["LOCALAPPDATA"]) / "rpa" / "worker"
    assert browsers_dir(windows, "win32") == Path(windows["LOCALAPPDATA"]) / "ms-playwright"
    mac = {"HOME": "/Users/amy"}
    assert data_dir(mac, "darwin") == Path("/Users/amy/Library/Application Support/rpa/worker")
    assert browsers_dir(mac, "darwin") == Path("/Users/amy/Library/Caches/ms-playwright")
    linux = {"HOME": "/home/amy"}
    assert data_dir(linux, "linux") == Path("/home/amy/.local/share/rpa/worker")
    assert browsers_dir(linux, "linux") == Path("/home/amy/.cache/ms-playwright")
    assert data_dir({ENV_HOME: "/tmp/w", **linux}, "linux") == Path("/tmp/w")


def test_browsers_path_is_set_only_when_frozen() -> None:
    env = {"HOME": "/home/amy"}
    ensure_browsers_path(env, frozen=False)
    assert BROWSERS_ENV not in env
    ensure_browsers_path(env, frozen=True)
    assert env[BROWSERS_ENV] == str(browsers_dir(env))
    zero = {"HOME": "/home/amy", BROWSERS_ENV: "0"}  # 打包工具可能設成放在 App 裡
    ensure_browsers_path(zero, frozen=True)
    assert zero[BROWSERS_ENV] == str(browsers_dir(zero))
    custom = {"HOME": "/home/amy", BROWSERS_ENV: "/opt/browsers"}
    ensure_browsers_path(custom, frozen=True)
    assert custom[BROWSERS_ENV] == "/opt/browsers"


def test_saved_pairing_is_used_without_asking(tmp_path: Path) -> None:
    pairing = tmp_path / "pairing.json"
    save_pairing(pairing, result())
    lines: list[str] = []

    found = obtain_credentials(pairing, invite=None, server=None, ask=None, say=lines.append)

    assert found == ("http://192.168.1.10:8081", "tok")
    assert "使用已配對的管理 Portal" in lines[0]


def test_no_pairing_and_nobody_to_ask(tmp_path: Path) -> None:
    lines: list[str] = []
    found = obtain_credentials(
        tmp_path / "pairing.json", invite=None, server=None, ask=None, say=lines.append
    )
    assert found is None
    assert "還沒有配對" in lines[0]


def test_invite_argument_pairs_and_saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Invite, str]] = []

    def fake_pair(invite: Invite, app: str) -> PairResult:
        calls.append((invite, app))
        return result(token="new")

    monkeypatch.setattr(worker_app, "pair", fake_pair)
    pairing = tmp_path / "work" / "pairing.json"
    save_pairing(pairing, result(token="old"))  # --invite 換掉存下的配對
    lines: list[str] = []

    found = obtain_credentials(pairing, invite=LINE, server=None, ask=None, say=lines.append)

    assert found == ("http://192.168.1.10:8081", "new")
    assert calls == [(Invite("http://192.168.1.10:8081", CODE, "worker"), "worker")]
    assert load_pairing(pairing) == ("http://192.168.1.10:8081", "new")
    assert "已配對：Windows（win-01）" in lines[-1]


def test_asking_retries_and_asks_for_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: list[Exception | PairResult] = [
        WorkerApiError(401, "invite_invalid", "邀請代碼不對"),
        ConnectionLostError("refused"),
        result(server="http://10.0.0.5:8081"),
    ]

    def fake_pair(invite: Invite, app: str) -> PairResult:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(worker_app, "pair", fake_pair)
    answers = ["這不是邀請", CODE, "10.0.0.5:8081", LINE, LINE]
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return answers.pop(0)

    lines: list[str] = []
    found = obtain_credentials(
        tmp_path / "pairing.json", invite=None, server=None, ask=ask, say=lines.append
    )

    assert found == ("http://10.0.0.5:8081", "tok")
    assert "這不是邀請" in lines[0]
    assert any("網址" in question for question in asked)  # 只貼代碼時問伺服器網址
    assert "配對失敗：邀請代碼不對" in lines[1]
    assert "連不上管理 Portal" in lines[2]
    assert answers == []


def test_giving_up_returns_nothing(tmp_path: Path) -> None:
    answers = [CODE, ""]  # 只有代碼、問網址時直接按 Enter
    found = obtain_credentials(
        tmp_path / "pairing.json",
        invite=None,
        server=None,
        ask=lambda question: answers.pop(0),
        say=lambda line: None,
    )
    assert found is None
    nobody = obtain_credentials(
        tmp_path / "pairing.json",
        invite=None,
        server=None,
        ask=lambda question: "",
        say=lambda line: None,
    )
    assert nobody is None


def test_required_browser_must_download(tmp_path: Path) -> None:
    installed: list[str] = []
    lines: list[str] = []

    def missing(engines: Sequence[str]) -> list[str]:
        return list(engines)

    def install(engine: str) -> int:
        installed.append(engine)
        return 0 if engine == "chromium" else 1

    engines = ["chromium", "firefox"]
    assert prepare_browsers(engines, missing=missing, say=lines.append, install=install)
    assert installed == ["chromium", "firefox"]
    assert "Chromium 已下載" in lines[1]
    assert "下載 Firefox 失敗（結束碼 1）" in lines[3]  # 選用的失敗只提醒

    assert not prepare_browsers(
        ["chromium"], missing=missing, say=lines.append, install=lambda engine: 7
    )
    assert prepare_browsers(["chromium"], missing=lambda engines: [], say=lines.append)


def test_events_are_described() -> None:
    details: dict[str, object] = {
        "worker": "win-01",
        "sameVersion": False,
        "fingerprint": "a",
        "serverFingerprint": "b",
    }
    online = describe_event("online", details)
    assert online is not None
    assert "win-01" in online
    assert "（a）" in online
    claimed = describe_event("claimed", {"run": "r1", "headless": False})
    assert claimed == "開始執行 r1（有頭模式）"
    rejected = describe_event("rejected", {"status": 401, "code": "x", "message": "權杖不對"})
    assert rejected == "管理 Portal 拒絕這台 worker：權杖不對"
    assert describe_event("unknown", {}) is None


def test_main_without_pairing_and_nobody_to_ask(tmp_path: Path) -> None:
    lines: list[str] = []
    code = worker_app.main(
        [], environ={ENV_HOME: str(tmp_path), "RPA_LANG": "en"}, say=lines.append, console=False
    )
    assert code == 2
    assert lines[0].startswith("RPA Worker ")
    assert "Not paired yet" in lines[1]


def test_reset_clears_the_saved_pairing(tmp_path: Path) -> None:
    save_pairing(tmp_path / "pairing.json", result())
    lines: list[str] = []
    code = worker_app.main(
        ["--reset-pairing"], environ={ENV_HOME: str(tmp_path)}, say=lines.append, console=False
    )
    assert code == 2
    assert not (tmp_path / "pairing.json").exists()
    assert "已清除配對" in lines[1]


# ---------------------------------------------------------------- 打包後的入口


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """把 worker 模式換成記錄參數；回傳每次進入 worker 模式時的參數。"""
    calls: list[list[str]] = []

    def fake(argv: Sequence[str] = ()) -> int:
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(worker_app, "main", fake)
    return calls


def _frozen(monkeypatch: pytest.MonkeyPatch, executable: str, app: App) -> None:
    monkeypatch.setattr(entry, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", executable)
    info = BuildInfo(app=app, version="0.1.0", fingerprint="f", protocol=1)
    monkeypatch.setattr("rpa_desktop.build_info.load", lambda: info)


def test_packaged_worker_starts_worker_mode(
    monkeypatch: pytest.MonkeyPatch, routed: list[list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    _frozen(monkeypatch, str(Path("RPA Worker") / "rpa-worker.exe"), "worker")
    assert entry.main([]) == 0
    assert entry.main(["--invite", LINE]) == 0
    assert routed == [[], ["--invite", LINE]]
    assert entry.main(["--version"]) == 0  # 自己的旗標照舊
    assert json.loads(capsys.readouterr().out)["app"] == "worker"
    assert len(routed) == 2


def test_child_and_recorder_do_not_start_a_worker(
    monkeypatch: pytest.MonkeyPatch, routed: list[list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    _frozen(monkeypatch, str(Path("RPA Worker") / "rpa-child.exe"), "worker")
    assert entry.main([]) == 0
    _frozen(monkeypatch, "/Applications/RPA Recorder.app/Contents/MacOS/rpa-recorder", "recorder")
    assert entry.main([]) == 0
    assert routed == []
    capsys.readouterr()


def test_worker_flag_works_in_development(routed: list[list[str]]) -> None:
    assert entry.main(["--worker", "--reset-pairing"]) == 0
    assert routed == [["--reset-pairing"]]


def test_console_detection_and_end_of_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """沒有輸入（CI 的 stdin 是 NUL、/dev/null）時不問問題；輸入結束視為沒有回答。"""

    class _NotATerminal:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", _NotATerminal())
    assert worker_app._console_ask() is None  # pyright: ignore[reportPrivateUsage]

    def end_of_input(question: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", end_of_input)
    assert worker_app._answer("？") == ""  # pyright: ignore[reportPrivateUsage]
