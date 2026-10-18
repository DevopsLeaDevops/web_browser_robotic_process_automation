"""RPA Worker App 的狀態與動作（rpa_desktop.controller），外部動作都換成替身。

不連真的管理 Portal、不下載瀏覽器：真的配對並執行場景在 CI 的桌面端建置（tools/desktop_e2e.py
以 ``--no-window`` 啟動打包版，走的就是這個 controller）。
"""

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from rpa_desktop.autostart import AutoStart, command_line
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import QUICK_STOP_SECONDS, Closable, Services, WorkerController
from rpa_desktop.credentials import Credentials, MemoryStore, TokenStoreError
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_worker.environment import WorkerInfo
from rpa_worker.pairing import App, Invite, PairResult
from rpa_worker.remote import ConnectionLostError, Notify, WorkerApiError, WorkerClient

SERVER = "http://192.168.1.10:8081"
CODE = "abcdefghijklmnopqrstuvwxyz012345"
LINE = Invite(SERVER, CODE, "worker").line()
BUILD = BuildInfo(app="worker", version="0.2.0", fingerprint="fp", protocol=1)


class FakeRun:
    def __init__(self, value: str | None = None) -> None:
        self.value = value

    def get(self) -> str | None:
        return self.value

    def set(self, command: str) -> None:
        self.value = command

    def delete(self) -> None:
        self.value = None


class Site:
    closed = False

    def shutdown(self) -> None:
        self.closed = True

    def server_close(self) -> None:
        pass


Event = tuple[str, dict[str, object]]


@dataclass
class Fakes:
    """替身：每個外部動作的結果與呼叫紀錄。"""

    pair_outcome: PairResult | Exception = field(
        default_factory=lambda: PairResult(
            SERVER, "win-01", "Windows", "worker", "tok", 1, "fp", "0.2.0"
        )
    )
    missing_engines: list[str] = field(default_factory=lambda: ["chromium"])
    download_codes: dict[str, int] = field(default_factory=lambda: {})
    events: list[Event] = field(
        default_factory=lambda: [("online", {"worker": "win-01", "sameVersion": True})]
    )
    fatal: str | None = None
    paired: list[tuple[Invite, App]] = field(default_factory=lambda: [])
    downloaded: list[str] = field(default_factory=lambda: [])
    runs: list[dict[str, object]] = field(default_factory=lambda: [])
    site: Site = field(default_factory=Site)
    block_download: threading.Event | None = None
    """設定時下載一直不結束，直到被取消（測試結束、重新配對時的取消）。"""
    started: threading.Event = field(default_factory=threading.Event)

    def services(self) -> Services:
        def pair(invite: Invite, app: App) -> PairResult:
            self.paired.append((invite, app))
            if isinstance(self.pair_outcome, Exception):
                raise self.pair_outcome
            return self.pair_outcome

        def missing(engines: Sequence[str]) -> list[str]:
            return [engine for engine in engines if engine in self.missing_engines]

        def download(
            engine: str, progress: Progress, environ: Mapping[str, str], cancel: threading.Event
        ) -> DownloadResult:
            self.downloaded.append(engine)
            if self.block_download is not None:
                self.block_download.set()  # 告訴測試：下載開始了
                cancel.wait(10)  # 像真的下載一樣，直到被取消
                return DownloadResult(1, "cancelled")
            progress(None)
            progress(50)
            progress(100)
            return DownloadResult(self.download_codes.get(engine, 0), "last line")

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
            record: dict[str, object] = {
                "server": client.server,
                "token": client.token,
                "info": info,
                "paused": paused,
                "stop": stop,
                "stop_seconds": stop_seconds,
            }
            self.runs.append(record)
            for event, details in self.events:
                notify(event, details)
            self.started.set()
            if self.fatal is not None:
                return self.fatal
            stop.wait(10)
            record["stopped_after"] = stop_seconds()
            return None

        def testsite(port: int) -> tuple[Closable | None, str, str]:
            return self.site, "started", ""

        def detect(name: str | None, fingerprint: str, version: str) -> WorkerInfo:
            return WorkerInfo(
                name=name or "box", fingerprint=fingerprint, version=version, display=True
            )

        return Services(
            pair=pair, missing=missing, download=download, run=run, testsite=testsite, detect=detect
        )


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


def make(
    tmp_path: Path, fakes: Fakes, store: MemoryStore, entry: FakeRun | None = None
) -> WorkerController:
    environ: dict[str, str] = {}
    return WorkerController(
        home=tmp_path,
        build=BUILD,
        environ=environ,
        credentials=Credentials(tmp_path, store),
        autostart=AutoStart(entry, Path("C:/RPA/rpa-worker.exe")),
        services=fakes.services(),
    )


def message_of(controller: WorkerController) -> dict[str, object]:
    message = controller.snapshot()["message"]
    assert isinstance(message, dict)
    return cast("dict[str, object]", message)


def text_of(controller: WorkerController) -> str:
    return str(message_of(controller)["text"])


def runs_of(state: dict[str, object], key: str = "recent") -> list[dict[str, object]]:
    value = state[key]
    assert isinstance(value, list)
    return cast("list[dict[str, object]]", value)


def wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    ticker = threading.Event()
    for _ in range(int(seconds / 0.01)):
        if condition():
            return
        ticker.wait(0.01)
    assert condition()


def test_without_pairing_waits_for_an_invite(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    controller = make(tmp_path, fakes, store)
    controller.start()
    assert controller.wait(5)
    assert controller.phase == "unpaired"
    assert controller.exit_code == 2
    state = controller.snapshot()
    assert state["paired"] is False
    assert fakes.runs == []


def test_pair_download_connect_run_and_stop(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.events = [
        ("online", {"worker": "win-01", "sameVersion": False, "serverFingerprint": "other"}),
        ("claimed", {"run": "r1", "headless": False, "engine": "chromium"}),
        ("reported", {"run": "r1", "status": "passed"}),
        ("claimed", {"run": "r2", "headless": True, "engine": "firefox"}),
    ]
    entry = FakeRun()
    controller = make(tmp_path, fakes, store, entry)
    changes: list[str] = []
    controller.subscribe(lambda: changes.append(controller.phase))
    assert controller.pair(LINE, None, firefox=False)
    wait_for(fakes.started.is_set)

    assert fakes.paired == [(Invite(SERVER, CODE, "worker"), "worker")]
    assert store.items == {f"win-01@{SERVER}": "tok"}  # 權杖在認證管理員
    assert entry.value is not None
    assert "--background" in entry.value  # 第一次配對預設開啟
    assert fakes.downloaded == ["chromium"]
    assert "downloading" in changes
    run = fakes.runs[0]
    assert (run["server"], run["token"]) == (SERVER, "tok")
    info = run["info"]
    assert isinstance(info, WorkerInfo)
    assert (info.fingerprint, info.version) == ("fp", "0.2.0")  # 建置資訊的指紋，不是原始碼的

    state = controller.snapshot()
    assert state["phase"] == "online"
    assert state["sameVersion"] is False
    assert state["serverFingerprint"] == "other"
    assert controller.busy
    current = state["current"]
    assert isinstance(current, dict)
    assert cast("dict[str, object]", current)["run"] == "r2"
    recent = runs_of(state)
    assert [(item["run"], item["status"]) for item in recent] == [("r2", None), ("r1", "passed")]

    controller.stop()
    assert controller.wait(5)
    assert controller.phase == "stopped"
    assert controller.exit_code == 0
    assert fakes.site.closed
    assert run["stopped_after"] == 120.0
    assert runs_of(controller.snapshot())[0]["status"] == "cancelled"


def test_saved_pairing_connects_and_fast_stop(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    Credentials(tmp_path, store).save(
        PairResult(SERVER, "win-01", "Windows", "worker", "saved", 1, None, None)
    )
    fakes.missing_engines = []
    controller = make(tmp_path, fakes, store)
    controller.start()
    wait_for(fakes.started.is_set)
    assert fakes.runs[0]["token"] == "saved"
    assert fakes.downloaded == []
    controller.stop(fast=True)  # Windows 關機
    assert controller.wait(5)
    assert fakes.runs[0]["stopped_after"] == QUICK_STOP_SECONDS


@pytest.mark.parametrize(
    ("outcome", "text"),
    [
        (WorkerApiError(409, "invite_wrong_app", "這是錄製端的邀請"), "配對失敗：這是錄製端的邀請"),
        (ConnectionLostError("refused"), "連不上管理 Portal"),
    ],
)
def test_pairing_errors_are_shown(
    tmp_path: Path, fakes: Fakes, store: MemoryStore, outcome: Exception, text: str
) -> None:
    fakes.pair_outcome = outcome
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert controller.wait(5)
    assert controller.phase == "unpaired"
    message = message_of(controller)
    assert text in str(message["text"])
    assert message["level"] == "error"
    assert controller.pair(LINE)  # 可以再試一次


def test_bad_invite_text_and_language(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    controller = make(tmp_path, fakes, store)
    controller.set_language("en")
    controller.pair("not an invite")
    assert controller.wait(5)
    # 訊息在背景執行緒產生，仍然是使用者選的語言（語言存在 ContextVar）
    assert "This is not an invitation" in text_of(controller)
    assert fakes.paired == []
    controller.set_language("zh-Hant")
    assert "這不是邀請" in text_of(controller)


def test_only_code_needs_the_server(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    controller = make(tmp_path, fakes, store)
    controller.pair(CODE)
    assert controller.wait(5)
    assert controller.phase == "unpaired"
    controller.pair(CODE, "192.168.1.10:8081")
    wait_for(fakes.started.is_set)
    assert fakes.paired[-1][0] == Invite(SERVER, CODE)
    controller.stop()
    controller.wait(5)


def test_rejected_token_clears_the_pairing(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.events = [
        ("rejected", {"status": 401, "code": "worker_unauthorized", "message": "權杖不對"})
    ]
    fakes.fatal = "權杖不對"
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert controller.wait(5)
    assert controller.phase == "unpaired"
    assert controller.exit_code == 1
    assert store.items == {}
    assert not (tmp_path / "pairing.json").exists()
    assert "權杖不對" in text_of(controller)


def test_protocol_mismatch_keeps_the_pairing(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.events = [
        ("rejected", {"status": 409, "code": "protocol_mismatch", "message": "協定不同"})
    ]
    fakes.fatal = "協定不同"
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert controller.wait(5)
    assert controller.phase == "error"
    assert store.items != {}  # 更新程式後就能再用，不必重新配對


def test_required_browser_failure_stops_and_retry(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.download_codes = {"chromium": 7}
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert controller.wait(5)
    assert controller.phase == "error"
    assert controller.exit_code == 3
    assert "結束碼 7" in text_of(controller)
    assert fakes.runs == []

    fakes.download_codes = {}
    assert controller.retry()
    wait_for(fakes.started.is_set)
    controller.stop()
    controller.wait(5)


def test_optional_firefox_failure_only_warns(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.missing_engines = ["chromium", "firefox"]
    fakes.download_codes = {"firefox": 1}
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE, firefox=True)
    wait_for(fakes.started.is_set)
    assert fakes.downloaded == ["chromium", "firefox"]
    assert controller.settings.firefox  # 記住選擇
    controller.stop()
    controller.wait(5)


def test_pause_is_passed_to_the_worker_loop(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    wait_for(fakes.started.is_set)
    paused = fakes.runs[0]["paused"]
    assert isinstance(paused, threading.Event)

    controller.set_paused(True)
    assert paused.is_set()
    assert controller.phase == "paused"
    assert controller.snapshot()["paused"] is True
    controller.set_paused(False)
    assert not paused.is_set()
    assert controller.phase == "connecting"  # 等迴圈重新上線（online 事件）
    controller.stop()
    controller.wait(5)


def test_autostart_is_offered_only_once(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    entry = FakeRun()
    controller = make(tmp_path, fakes, store, entry)
    controller.pair(LINE)
    wait_for(fakes.started.is_set)
    controller.set_autostart(False)  # 使用者關掉
    assert entry.value is None
    controller.stop()
    controller.wait(5)

    again = make(tmp_path, Fakes(), store, entry)
    again.reset_pairing()
    again.pair(LINE)  # 重新配對不會再自動開啟
    again.wait(0.5)
    assert entry.value is None
    again.stop()
    again.wait(5)


def test_moved_folder_updates_the_autostart_path(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    entry = FakeRun('"D:\\old\\rpa-worker.exe" --background')
    Credentials(tmp_path, store).save(
        PairResult(SERVER, "win-01", "Windows", "worker", "saved", 1, None, None)
    )
    controller = make(tmp_path, fakes, store, entry)
    controller.start()
    wait_for(fakes.started.is_set)
    assert entry.value == command_line(Path("C:/RPA/rpa-worker.exe"))
    controller.stop()
    controller.wait(5)


def test_settings_and_reset(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    controller = make(tmp_path, fakes, store)
    controller.set_download_host(" http://mirror.local ")
    assert controller.environ["PLAYWRIGHT_DOWNLOAD_HOST"] == "http://mirror.local"
    controller.set_download_host("")
    assert "PLAYWRIGHT_DOWNLOAD_HOST" not in controller.environ

    controller.pair(LINE)
    wait_for(fakes.started.is_set)
    controller.set_firefox(True)
    assert "Firefox" in text_of(controller)

    controller.reset_pairing()
    assert controller.phase == "unpaired"
    assert store.items == {}
    assert controller.snapshot()["paired"] is False

    reopened = make(tmp_path, Fakes(), store)
    assert reopened.settings.firefox  # 設定存在資料夾裡
    assert reopened.settings.download_host == ""


def test_saved_download_host_is_applied_at_start(tmp_path: Path, store: MemoryStore) -> None:
    first = make(tmp_path, Fakes(), store)
    first.set_download_host("http://mirror")
    environ: dict[str, str] = {}
    WorkerController(
        home=tmp_path,
        build=BUILD,
        environ=environ,
        credentials=Credentials(tmp_path, store),
        autostart=AutoStart(None, Path("x")),
        services=Fakes().services(),
    )
    assert environ["PLAYWRIGHT_DOWNLOAD_HOST"] == "http://mirror"


def test_tray_hint_only_once(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    controller = make(tmp_path, fakes, store)
    assert controller.mark_tray_hint_shown()
    assert not controller.mark_tray_hint_shown()
    assert not make(tmp_path, fakes, store).mark_tray_hint_shown()


# ---------------------------------------------------------------- 審閱後補上的情況


def test_reset_during_download_cancels_it_and_never_runs_the_old_token(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.block_download = threading.Event()
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert fakes.block_download.wait(5)  # 正在下載 Chromium
    assert controller.reset_pairing(timeout=5)
    assert controller.phase == "unpaired"
    assert store.items == {}
    assert fakes.runs == []  # 下載被取消後沒有拿舊的權杖連線
    assert controller.pair(LINE)  # 可以馬上重新配對


def test_quit_during_download_stops_without_connecting(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.block_download = threading.Event()
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    assert fakes.block_download.wait(5)
    controller.stop()
    assert controller.wait(5)
    assert controller.phase == "stopped"
    assert controller.exit_code == 0
    assert fakes.runs == []


def test_reset_keeps_the_pairing_when_the_worker_does_not_stop(
    tmp_path: Path, fakes: Fakes, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    wait_for(fakes.started.is_set)

    def never_stops(self: WorkerController, timeout: float | None = None) -> bool:
        return False

    monkeypatch.setattr(WorkerController, "wait", never_stops)
    assert not controller.reset_pairing(timeout=0.1)
    assert store.items != {}  # 還沒停下來就不清除
    assert "還沒停下來" in text_of(controller)
    monkeypatch.undo()
    controller.wait(5)


def test_undelivered_result_does_not_stay_running(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.events = [
        ("online", {"worker": "win-01", "sameVersion": True}),
        ("claimed", {"run": "r1", "headless": True, "engine": "chromium"}),
        ("report_failed", {"reason": "refused"}),
        ("done", {"run": "r1"}),
        ("claimed", {"run": "r2", "headless": True, "engine": "chromium"}),
        ("reported", {"run": "r2", "status": "passed"}),
        ("done", {"run": "r2"}),
    ]
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE)
    wait_for(fakes.started.is_set)
    assert not controller.busy  # 結束時不必確認「有任務在執行」
    recent = runs_of(controller.snapshot())
    assert [(item["run"], item["status"]) for item in recent] == [
        ("r2", "passed"),  # done 不會改掉已經有的結果
        ("r1", "unreported"),
    ]
    controller.stop()
    controller.wait(5)


def test_going_online_keeps_warnings_but_clears_connection_problems(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.missing_engines = ["chromium", "firefox"]
    fakes.download_codes = {"firefox": 1}
    controller = make(tmp_path, fakes, store)
    controller.pair(LINE, firefox=True)
    wait_for(fakes.started.is_set)
    message = message_of(controller)
    assert message["level"] == "warn"
    assert "Firefox" in str(message["text"])  # 上線後仍看得到選用的瀏覽器沒下載成功
    controller.stop()
    controller.wait(5)

    again = Fakes(
        events=[
            ("offline", {"server": SERVER, "reason": "refused"}),
            ("online", {"worker": "win-01", "sameVersion": True}),
        ]
    )
    reopened = make(tmp_path, again, store)
    reopened.start()
    wait_for(again.started.is_set)
    assert reopened.snapshot()["message"] is None  # 連不上的提醒在重新上線後清掉
    reopened.stop()
    reopened.wait(5)


class _FlakyStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.broken = False

    def get(self, key: str) -> str | None:
        if self.broken:
            raise TokenStoreError("locked")
        return super().get(key)


def test_unreadable_credential_manager_is_an_error_with_retry(tmp_path: Path, fakes: Fakes) -> None:
    flaky = _FlakyStore()
    Credentials(tmp_path, flaky).save(
        PairResult(SERVER, "win-01", "Windows", "worker", "saved", 1, None, None)
    )
    flaky.broken = True
    controller = make(tmp_path, fakes, flaky)
    controller.start()
    assert controller.wait(5)
    assert controller.phase == "error"  # 不是「尚未配對」：不必重新配對
    assert "認證管理員" in text_of(controller)
    assert flaky.items != {}
    flaky.broken = False
    assert controller.retry()
    wait_for(fakes.started.is_set)
    assert fakes.runs[0]["token"] == "saved"
    controller.stop()
    controller.wait(5)


def test_concurrent_pair_calls_start_one_worker(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.block_download = threading.Event()
    controller = make(tmp_path, fakes, store)
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(controller.pair(LINE))) for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert results.count(True) == 1
    controller.stop()
    controller.wait(5)
