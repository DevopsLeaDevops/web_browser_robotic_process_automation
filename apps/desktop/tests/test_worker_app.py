"""RPA Worker 的 worker 模式（M10.1）：資料夾與瀏覽器的位置、配對（邀請、存下的配對、詢問）、
下載瀏覽器、事件文字，以及打包後的入口分流。

不連真的管理 Portal：配對的 HTTP 在 apps/worker 的 test_pairing.py；打包版真的配對並執行場景
在 CI 的桌面端建置（tools/desktop_e2e.py）。
"""

import json
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_desktop import entry, gui, headless, recorder_gui, recorder_headless, worker_app
from rpa_desktop.build_info import App, BuildInfo
from rpa_desktop.credentials import Credentials, MemoryStore
from rpa_desktop.single_instance import InstanceLock
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
from rpa_worker.pairing import Invite, PairResult
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


def test_saved_pairing_is_used_without_asking(tmp_path: Path, store: MemoryStore) -> None:
    pairing = Credentials(tmp_path, store)
    pairing.save(result())
    lines: list[str] = []

    found = obtain_credentials(pairing, invite=None, server=None, ask=None, say=lines.append)

    assert found == ("http://192.168.1.10:8081", "tok")
    assert "使用已配對的管理 Portal" in lines[0]


def test_no_pairing_and_nobody_to_ask(tmp_path: Path, store: MemoryStore) -> None:
    lines: list[str] = []
    found = obtain_credentials(
        Credentials(tmp_path, store), invite=None, server=None, ask=None, say=lines.append
    )
    assert found is None
    assert "還沒有配對" in lines[0]


def test_invite_argument_pairs_and_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store: MemoryStore
) -> None:
    calls: list[tuple[Invite, str]] = []

    def fake_pair(invite: Invite, app: str) -> PairResult:
        calls.append((invite, app))
        return result(token="new")

    monkeypatch.setattr(worker_app, "pair", fake_pair)
    pairing = Credentials(tmp_path / "work", store)
    pairing.save(result(token="old"))  # --invite 換掉存下的配對
    lines: list[str] = []

    found = obtain_credentials(pairing, invite=LINE, server=None, ask=None, say=lines.append)

    assert found == ("http://192.168.1.10:8081", "new")
    assert calls == [(Invite("http://192.168.1.10:8081", CODE, "worker"), "worker")]
    saved = pairing.load()
    assert saved is not None
    assert (saved.server, saved.token) == ("http://192.168.1.10:8081", "new")
    assert "token" not in json.loads(pairing.path.read_text(encoding="utf-8"))  # 權杖在認證管理員
    assert "已配對：Windows（win-01）" in lines[-1]


def test_asking_retries_and_asks_for_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store: MemoryStore
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
        Credentials(tmp_path, store), invite=None, server=None, ask=ask, say=lines.append
    )

    assert found == ("http://10.0.0.5:8081", "tok")
    assert "這不是邀請" in lines[0]
    assert any("網址" in question for question in asked)  # 只貼代碼時問伺服器網址
    assert "配對失敗：邀請代碼不對" in lines[1]
    assert "連不上管理 Portal" in lines[2]
    assert answers == []


def test_giving_up_returns_nothing(tmp_path: Path, store: MemoryStore) -> None:
    answers = [CODE, ""]  # 只有代碼、問網址時直接按 Enter
    found = obtain_credentials(
        Credentials(tmp_path, store),
        invite=None,
        server=None,
        ask=lambda question: answers.pop(0),
        say=lambda line: None,
    )
    assert found is None
    nobody = obtain_credentials(
        Credentials(tmp_path, store),
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


def test_main_without_pairing_and_nobody_to_ask(tmp_path: Path, store: MemoryStore) -> None:
    lines: list[str] = []
    code = worker_app.main(
        [],
        environ={ENV_HOME: str(tmp_path), "RPA_LANG": "en"},
        say=lines.append,
        console=False,
        store=store,
    )
    assert code == 2
    assert lines[0].startswith("RPA Worker ")
    assert "Not paired yet" in lines[1]


def test_reset_clears_the_saved_pairing(tmp_path: Path, store: MemoryStore) -> None:
    Credentials(tmp_path, store).save(result())
    lines: list[str] = []
    code = worker_app.main(
        ["--reset-pairing"],
        environ={ENV_HOME: str(tmp_path)},
        say=lines.append,
        console=False,
        store=store,
    )
    assert code == 2
    assert not (tmp_path / "pairing.json").exists()
    assert store.items == {}  # 認證管理員裡的權杖也刪了
    assert "已清除配對" in lines[1]


def test_only_one_copy_runs_per_folder(tmp_path: Path, store: MemoryStore) -> None:
    held = InstanceLock(tmp_path)
    assert held.acquire()  # 例如視窗版正在執行
    try:
        lines: list[str] = []
        code = worker_app.main(
            [], environ={ENV_HOME: str(tmp_path)}, say=lines.append, console=False, store=store
        )
    finally:
        held.release()
    assert code == 4
    assert "已經有一份 RPA Worker" in lines[1]


# ---------------------------------------------------------------- 打包後的入口


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """把三種 worker 與錄製端視窗的入口換成記錄；回傳 (哪一種, 參數)。"""
    calls: list[tuple[str, list[str]]] = []

    def recorder(kind: str) -> Callable[..., int]:
        def fake(argv: Sequence[str] = ()) -> int:
            calls.append((kind, list(argv)))
            return 0

        return fake

    monkeypatch.setattr(worker_app, "main", recorder("console"))
    monkeypatch.setattr(gui, "main", recorder("window"))
    monkeypatch.setattr(headless, "main", recorder("no-window"))
    monkeypatch.setattr(recorder_gui, "main", recorder("recorder"))
    monkeypatch.setattr(recorder_headless, "main", recorder("recorder-no-window"))
    return calls


def _frozen(monkeypatch: pytest.MonkeyPatch, executable: str, app: App) -> None:
    monkeypatch.setattr(entry, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", executable)
    info = BuildInfo(app=app, version="0.1.0", fingerprint="f", protocol=1)
    monkeypatch.setattr("rpa_desktop.build_info.load", lambda: info)


def test_packaged_worker_opens_the_window(
    monkeypatch: pytest.MonkeyPatch,
    routed: list[tuple[str, list[str]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _frozen(monkeypatch, str(Path("RPA Worker") / "rpa-worker.exe"), "worker")
    assert entry.main([]) == 0
    assert entry.main(["--background"]) == 0
    assert entry.main(["--invite", LINE]) == 0
    assert routed == [("window", []), ("window", ["--background"]), ("window", ["--invite", LINE])]
    assert entry.main(["--version"]) == 0  # 自己的旗標照舊
    assert json.loads(capsys.readouterr().out)["app"] == "worker"
    assert len(routed) == 3


def test_no_window_flag_anywhere(
    monkeypatch: pytest.MonkeyPatch, routed: list[tuple[str, list[str]]]
) -> None:
    _frozen(monkeypatch, str(Path("RPA Worker") / "rpa-worker.exe"), "worker")
    assert entry.main(["--no-window", "--invite", LINE]) == 0
    assert entry.main(["--invite", LINE, "--no-window"]) == 0
    assert routed == [("no-window", ["--invite", LINE]), ("no-window", ["--invite", LINE])]


def test_child_and_recorder_do_not_start_a_worker(
    monkeypatch: pytest.MonkeyPatch,
    routed: list[tuple[str, list[str]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _frozen(monkeypatch, str(Path("RPA Worker") / "rpa-child.exe"), "worker")
    assert entry.main([]) == 0
    assert routed == []
    capsys.readouterr()
    # 打包的錄製端開錄製端的視窗（M10.2），同資料夾的 rpa-child 不會
    recorder = "/Applications/RPA Recorder.app/Contents/MacOS/"
    _frozen(monkeypatch, recorder + "rpa-recorder", "recorder")
    assert entry.main(["-psn_0_123"]) == 0
    _frozen(monkeypatch, recorder + "rpa-child", "recorder")
    assert entry.main([]) == 0
    assert routed == [("recorder", ["-psn_0_123"])]
    assert entry.main(["--recorder", "--smoke-test"]) == 0  # 開發環境試視窗
    assert routed[-1] == ("recorder", ["--smoke-test"])
    capsys.readouterr()


def test_recorder_without_the_window(
    monkeypatch: pytest.MonkeyPatch, routed: list[tuple[str, list[str]]]
) -> None:
    """錄製端的 --no-window 是不開 App 視窗的錄製端，不是 worker（打包版的兩個執行檔都一樣）。"""
    assert entry.main(["--recorder", "--no-window", "--invite", LINE]) == 0  # 開發環境
    recorder = "/Applications/RPA Recorder.app/Contents/MacOS/"
    _frozen(monkeypatch, recorder + "rpa-recorder", "recorder")
    assert entry.main(["--no-window", "--url-file", "portal.txt"]) == 0
    _frozen(monkeypatch, recorder + "rpa-child", "recorder")
    assert entry.main(["--log", "r.log", "--no-window"]) == 0
    assert routed == [
        ("recorder-no-window", ["--invite", LINE]),
        ("recorder-no-window", ["--url-file", "portal.txt"]),
        ("recorder-no-window", ["--log", "r.log"]),
    ]


def test_worker_flags_work_in_development(routed: list[tuple[str, list[str]]]) -> None:
    assert entry.main(["--worker", "--reset-pairing"]) == 0  # 主控台版（rpa-child.exe --worker）
    assert entry.main(["--window", "--background"]) == 0
    assert entry.main(["--no-window"]) == 0
    assert routed == [
        ("console", ["--reset-pairing"]),
        ("window", ["--background"]),
        ("no-window", []),
    ]


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


def test_console_worker_stops_on_request_before_connecting(
    tmp_path: Path, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """安裝檔在下載瀏覽器時就寫 stop.request：那一步做完就結束，不再連線（結束碼 0）。"""
    Credentials(tmp_path, store).save(result())
    handled = threading.Event()
    watch = InstanceLock.watch

    def watching(
        lock: InstanceLock,
        on_show: Callable[[], object] | None,
        stop: threading.Event,
        interval: float = 0.5,
        *,
        on_stop: Callable[[], object] | None = None,
    ) -> threading.Thread:
        # 背景的監看先刪掉請求檔、再呼叫 on_stop：只等檔案不見會有空檔（偶發失敗），
        # 要等 on_stop 真的做完
        def stopped() -> None:
            if on_stop is not None:
                on_stop()
            handled.set()

        return watch(lock, on_show, stop, interval, on_stop=stopped)

    def downloading(*args: object, **kwargs: object) -> bool:
        InstanceLock(tmp_path).request_stop()
        assert handled.wait(10), "背景的監看沒有處理結束的請求"
        return True

    monkeypatch.setattr(InstanceLock, "watch", watching)

    def never(*args: object, **kwargs: object) -> object:
        raise AssertionError("收到結束的請求後不應該連線")

    monkeypatch.setattr(worker_app, "prepare_browsers", downloading)
    monkeypatch.setattr("rpa_worker.service.run_remote_worker", never)
    code = worker_app.main(
        ["--no-testsite"],
        environ={ENV_HOME: str(tmp_path)},
        say=lambda line: None,
        console=False,
        store=store,
    )
    assert code == 0
    assert not (tmp_path / "stop.request").exists()
