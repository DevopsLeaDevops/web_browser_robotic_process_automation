"""RPA 錄製端 App（M10.2）：狀態與動作（rpa_desktop.recorder_controller）、App 自己的頁面
（rpa_desktop.recorder_pages）經由真的本機閘道。外部動作都換成替身。

真的 WKWebView 視窗是 CI 的桌面端建置（macOS，``rpa-recorder --smoke-test``）；錄製端程式
本身（RecorderHost）在 apps/worker 的測試，經由管理 Portal 的完整流程在 apps/server 的測試。
"""

import http.client
import json
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast, get_args

import pytest

from rpa_core.i18n import LOCALES
from rpa_desktop import recorder_headless
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import Closable
from rpa_desktop.credentials import Credentials, MemoryStore
from rpa_desktop.downloads import DownloadResult, Progress
from rpa_desktop.i18n import t
from rpa_desktop.recorder_controller import (
    Notify,
    Phase,
    RecorderController,
    RecorderServices,
    wait_for,
)
from rpa_desktop.recorder_gui import recorder_dir
from rpa_desktop.recorder_pages import DesktopPages, notice_page, offline_page
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.ui import PAGES, page_strings, render_page
from rpa_worker.environment import WorkerInfo
from rpa_worker.gateway import COOKIE, DESKTOP_COOKIE, DESKTOP_PREFIX, Gateway
from rpa_worker.pairing import CLIENT_API_PREFIX, App, Invite, PairResult
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient

SERVER = "http://192.168.1.10:8081"
CODE = "abcdefghijklmnopqrstuvwxyz012345"
LINE = Invite(SERVER, CODE, "recorder").line()
BUILD = BuildInfo(app="recorder", version="0.3.0", fingerprint="fp", protocol=1)
ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "apps" / "desktop" / "src" / "rpa_desktop" / "ui"


class Site:
    closed = False

    def shutdown(self) -> None:
        self.closed = True

    def server_close(self) -> None:
        pass


@dataclass
class FakeHost:
    """替身：RecorderHost.run 依序送出事件，之後等到停止（或回傳被拒的原因）。"""

    fakes: "Fakes"
    client: WorkerClient
    info: Mapping[str, object]
    work: Path
    notify: Notify

    def run(self, stop: threading.Event | None = None) -> str | None:
        assert stop is not None
        for event, details in self.fakes.events:
            self.notify(event, details)
        self.fakes.started.set()
        if self.fakes.fatal is not None:
            message, status = self.fakes.fatal
            self.notify("rejected", {"message": message, "status": status})
            return message
        stop.wait(10)
        return None

    def active(self) -> int:
        return self.fakes.active

    def stop_all(self) -> None:
        self.fakes.stopped_all += 1


@dataclass
class Fakes:
    pair_outcome: PairResult | Exception = field(
        default_factory=lambda: PairResult(
            SERVER, "mac-01", "Amy 的 Mac", "recorder", "tok", 1, "fp", "0.3.0"
        )
    )
    missing_engines: list[str] = field(default_factory=lambda: ["chromium"])
    download_codes: dict[str, int] = field(default_factory=lambda: {})
    events: list[tuple[str, dict[str, object]]] = field(
        default_factory=lambda: [("online", {"device": "mac-01", "sameVersion": True})]
    )
    fatal: tuple[str, int | None] | None = None
    active: int = 0
    stopped_all: int = 0
    paired: list[tuple[Invite, App]] = field(default_factory=lambda: [])
    downloaded: list[str] = field(default_factory=lambda: [])
    hosts: list[FakeHost] = field(default_factory=lambda: [])
    site: Site = field(default_factory=Site)
    started: threading.Event = field(default_factory=threading.Event)

    def services(self) -> RecorderServices:
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
            progress(None)
            progress(100)
            return DownloadResult(self.download_codes.get(engine, 0), "last line")

        def testsite(port: int) -> tuple[Closable | None, str, str]:
            return self.site, "started", ""

        def detect(name: str | None, fingerprint: str, version: str) -> WorkerInfo:
            return WorkerInfo(
                name=name or "mac", fingerprint=fingerprint, version=version, display=True
            )

        def host(
            client: WorkerClient, info: Mapping[str, object], work: Path, notify: Notify
        ) -> FakeHost:
            item = FakeHost(self, client, info, work, notify)
            self.hosts.append(item)
            return item

        return RecorderServices(
            pair=pair,
            missing=missing,
            download=download,
            testsite=testsite,
            detect=detect,
            host=host,
        )


class FakeGateway:
    def __init__(self) -> None:
        self.servers: list[str | None] = []

    def set_server(self, server: str | None) -> None:
        self.servers.append(server)


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def controller(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> Iterator[RecorderController]:
    item = RecorderController(
        home=tmp_path / "home",
        build=BUILD,
        environ={},
        credentials=Credentials(tmp_path / "home", store),
        services=fakes.services(),
    )
    try:
        yield item
    finally:
        item.stop()
        item.wait(10)


def phase_is(controller: RecorderController, *phases: Phase) -> bool:
    return wait_for(lambda: controller.phase in phases, 10)


# ---------------------------------------------------------------- 狀態與動作


def test_pairing_downloads_and_connects(
    controller: RecorderController, fakes: Fakes, store: MemoryStore
) -> None:
    gateway = FakeGateway()
    controller.attach(gateway)
    assert gateway.servers == [None]
    assert controller.token() is None
    controller.start()
    assert phase_is(controller, "unpaired")
    assert controller.pair(LINE, None, firefox=True)
    assert phase_is(controller, "online")
    assert fakes.paired[0][1] == "recorder"
    assert fakes.downloaded == ["chromium"]  # Firefox 已經有了
    assert gateway.servers == [None, SERVER]
    assert controller.token() == "tok"
    host = fakes.hosts[0]
    assert host.client.base == SERVER + CLIENT_API_PREFIX
    assert host.client.token == "tok"
    assert host.work == controller.home / "sessions"
    assert host.info["fingerprint"] == "fp"
    state = controller.snapshot()
    assert state["paired"] is True
    assert state["device"] == "mac-01"
    assert state["storage"] == "keyring"
    assert store.items  # 權杖在鑰匙圈（測試用記憶體替身）
    assert cast("dict[str, object]", state["settings"])["firefox"] is True


def test_saved_pairing_connects_directly(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    Credentials(tmp_path / "home", store).save(
        PairResult(SERVER, "mac-01", "Mac", "recorder", "tok", 1, None, None)
    )
    controller = RecorderController(
        home=tmp_path / "home",
        build=BUILD,
        environ={},
        credentials=Credentials(tmp_path / "home", store),
        services=fakes.services(),
    )
    gateway = FakeGateway()
    controller.attach(gateway)
    controller.start()
    try:
        assert phase_is(controller, "online")
        assert gateway.servers[-1] == SERVER
        fakes.active = 2
        assert controller.active == 2
        assert controller.snapshot()["active"] == 2
    finally:
        controller.stop()
        controller.wait(10)
    assert controller.phase == "stopped"
    assert fakes.site.closed


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (WorkerApiError(409, "invite_wrong_app", "這是 worker 的邀請"), "這是 worker 的邀請"),
        (ConnectionLostError("refused"), "--worker-port"),
    ],
)
def test_pairing_problems_are_explained(
    controller: RecorderController, fakes: Fakes, outcome: Exception, expected: str
) -> None:
    fakes.pair_outcome = outcome
    controller.start(LINE)
    assert phase_is(controller, "unpaired")
    assert wait_for(lambda: controller.snapshot()["message"] is not None, 5)
    message = cast("dict[str, str]", controller.snapshot()["message"])
    assert expected in message["text"]
    assert message["level"] == "error"


def test_rejected_token_clears_the_pairing(
    controller: RecorderController, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.fatal = ("錄製端的權杖不對", 401)
    gateway = FakeGateway()
    controller.attach(gateway)
    controller.start(LINE)
    assert phase_is(controller, "unpaired")
    assert wait_for(lambda: not controller.running, 5)
    assert store.items == {}
    assert gateway.servers[-1] is None
    message = cast("dict[str, str]", controller.snapshot()["message"])
    assert "錄製端的權杖不對" in message["text"]


def test_protocol_mismatch_keeps_the_pairing(
    controller: RecorderController, fakes: Fakes, store: MemoryStore
) -> None:
    fakes.fatal = ("協定版本不同", None)
    controller.start(LINE)
    assert phase_is(controller, "error")
    assert store.items  # 不是權杖的問題：配對留著，更新 App 後再試


def test_download_failure_can_be_retried(controller: RecorderController, fakes: Fakes) -> None:
    fakes.download_codes = {"chromium": 1}
    controller.start(LINE)
    assert phase_is(controller, "error")
    assert wait_for(lambda: not controller.running, 5)
    fakes.download_codes = {}
    assert controller.retry()
    assert phase_is(controller, "online")


def test_reset_pairing(controller: RecorderController, fakes: Fakes, store: MemoryStore) -> None:
    controller.start(LINE)
    assert phase_is(controller, "online")
    assert controller.reset_pairing()
    assert controller.phase == "unpaired"
    assert store.items == {}
    assert controller.token() is None


def test_settings(controller: RecorderController) -> None:
    controller.set_download_host(" https://mirror.example ")
    assert controller.environ["PLAYWRIGHT_DOWNLOAD_HOST"] == "https://mirror.example"
    controller.set_download_host("")
    assert "PLAYWRIGHT_DOWNLOAD_HOST" not in controller.environ
    controller.set_language("en")
    assert controller.locale == "en"
    controller.set_firefox(True)
    assert controller.settings.firefox is True


def test_recorder_dir() -> None:
    home = {"HOME": "/Users/amy"}
    assert recorder_dir(home, "darwin") == Path(
        "/Users/amy/Library/Application Support/rpa/recorder"
    )
    assert recorder_dir({**home, "RPA_RECORDER_HOME": "/tmp/r"}, "darwin") == Path("/tmp/r")
    assert recorder_dir({"LOCALAPPDATA": "C:/L"}, "win32") == Path("C:/L/rpa/recorder")


# ---------------------------------------------------------------- 頁面


@pytest.mark.parametrize("locale", LOCALES)
def test_page_is_complete_in_every_language(locale: str) -> None:
    html = render_page(locale, "recorder")  # type: ignore[arg-type]
    strings = page_strings(locale, PAGES["recorder"])  # type: ignore[arg-type]
    keys = set(re.findall(r'data-(?:text|placeholder)="([^"]+)"', html))
    script = (UI / "recorder.js").read_text(encoding="utf-8")
    keys |= set(re.findall(r'text\("(recorder\.[a-z_.]+)"', script))
    missing = sorted(key for key in keys if key not in strings and not key.endswith("."))
    assert missing == []
    for phase in get_args(Phase):
        assert f"recorder.phase.{phase}" in strings


class Browser:
    """經由閘道送請求的小工具：App 自己的頁面那個埠（帶著那一邊的 Cookie 與 Origin），
    或（``portal``）轉送到管理 Portal 的埠。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def request(
        self,
        method: str,
        path: str,
        body: object = None,
        headers: Mapping[str, str] | None = None,
        *,
        portal: bool = False,
    ) -> tuple[int, dict[str, str], bytes]:
        gateway = self.gateway
        if portal:
            port, cookie = gateway.port, f"{COOKIE}={gateway.secret}"
            values = {"Cookie": cookie}
        else:
            assert gateway.desktop_port is not None
            port, cookie = gateway.desktop_port, f"{DESKTOP_COOKIE}={gateway.desktop_secret}"
            values = {"Cookie": cookie, "Origin": str(gateway.desktop_origin)}
        values.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            values["Content-Type"] = "application/json"
        connection.request(method, path, body=data, headers=values)
        response = connection.getresponse()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            response.read(),
        )
        connection.close()
        return result


@pytest.fixture
def served(controller: RecorderController) -> Iterator[tuple[Browser, list[str]]]:
    calls: list[str] = []
    gateway: Gateway | None = None

    def portal_url() -> str:
        assert gateway is not None
        return gateway.login_url("/")

    pages = DesktopPages(
        controller,
        on_quit=lambda: calls.append("quit"),
        on_logs=lambda: calls.append("logs"),
        on_download=lambda: calls.append("download"),
        on_ready=lambda agent: calls.append("ready:" + agent),
        portal_url=portal_url,
    )
    gateway = Gateway(
        None, controller.token, local=pages, notice_page=notice_page(lambda: controller.locale)
    )
    controller.attach(gateway)
    gateway.start()
    try:
        yield Browser(gateway), calls
    finally:
        gateway.close()


def test_pages_through_the_gateway(
    served: tuple[Browser, list[str]], controller: RecorderController
) -> None:
    browser, calls = served
    status, _, page = browser.request("GET", DESKTOP_PREFIX)
    assert status == 200
    assert b'<html lang="zh-Hant">' in page
    assert "RPA 錄製端".encode() in page
    # 還沒配對：Portal 那個埠只有說明頁（沒有 App 頁面的網址）
    status, _, page = browser.request(
        "GET", "/scenes", headers={"Accept": "text/html"}, portal=True
    )
    assert status == 409
    assert t.messages("zh-Hant")["recorder.notice_unpaired"].encode() in page
    assert browser.gateway.desktop_secret.encode() not in page
    assert browser.request("POST", "/api/scenes", {}, portal=True)[0] == 409
    controller.start()
    assert phase_is(controller, "unpaired")
    status, _, data = browser.request("GET", DESKTOP_PREFIX + "state")
    state = json.loads(data)
    assert (state["phase"], state["portalUrl"]) == ("unpaired", None)
    status, _, data = browser.request("POST", DESKTOP_PREFIX + "pair", {"invite": LINE})
    assert json.loads(data) == {"ok": True}
    assert phase_is(controller, "online")
    assert browser.gateway.server == SERVER
    state = json.loads(browser.request("GET", DESKTOP_PREFIX + "state")[2])
    assert state["portalUrl"] == browser.gateway.login_url("/")
    for name in ("logs", "download", "quit"):
        assert browser.request("POST", DESKTOP_PREFIX + name, {})[0] == 200
    browser.request("POST", DESKTOP_PREFIX + "ready", {"userAgent": "AppleWebKit"})
    assert calls == ["logs", "download", "quit", "ready:AppleWebKit"]
    status, _, data = browser.request(
        "POST", DESKTOP_PREFIX + "settings", {"name": "language", "value": "en"}
    )
    assert json.loads(data) == {"ok": True}
    assert controller.locale == "en"
    assert browser.request("POST", DESKTOP_PREFIX + "settings", {"name": "x", "value": 1})[0] == 200
    mirror = {"name": "download_host", "value": "file:///tmp/evil"}
    assert json.loads(browser.request("POST", DESKTOP_PREFIX + "settings", mirror)[2]) == {
        "ok": False
    }
    assert browser.request("GET", DESKTOP_PREFIX + "nope")[0] == 404


def test_portal_pages_cannot_drive_the_app(
    served: tuple[Browser, list[str]], controller: RecorderController
) -> None:
    """Portal 的頁面（或塞進去的腳本）和 App 的頁面不同來源：叫不動 App。"""
    browser, calls = served
    # Portal 那個埠沒有 App 的頁面
    assert browser.request("POST", DESKTOP_PREFIX + "quit", {}, portal=True)[0] == 403
    # 從 Portal 的來源送到 App 的埠（瀏覽器會帶上 Cookie）：Origin 不對，拒絕
    portal = {"Origin": browser.gateway.origin}
    assert browser.request("POST", DESKTOP_PREFIX + "quit", {}, headers=portal)[0] == 403
    assert browser.request("POST", DESKTOP_PREFIX + "reset", {}, headers=portal)[0] == 403
    foreign = {"Origin": "http://evil.example"}
    assert browser.request("POST", DESKTOP_PREFIX + "quit", {}, headers=foreign)[0] == 403
    assert calls == []


def test_stop_now_ends_the_children_without_waiting(
    controller: RecorderController, fakes: Fakes
) -> None:
    controller.start(LINE)
    assert phase_is(controller, "online")
    controller.stop_now()
    assert fakes.stopped_all == 1


def test_new_windows_and_external_links(monkeypatch: pytest.MonkeyPatch) -> None:
    from rpa_desktop import recorder_gui

    launched: list[str] = []

    def launch(target: str) -> bool:
        launched.append(target)
        return True

    monkeypatch.setattr(recorder_gui, "_launch", launch)
    gateway = Gateway(SERVER, lambda: "tok")
    opened: list[tuple[str, str]] = []
    done = threading.Event()

    def open_window(url: str) -> None:
        opened.append((url, threading.current_thread().name))
        done.set()

    browser = recorder_gui._WindowBrowser(gateway, open_window)  # pyright: ignore[reportPrivateUsage]
    try:
        assert browser.open(gateway.origin + "/runs/x/files/report.html")
        assert done.wait(5)
        # pywebview 在主執行緒呼叫：新視窗要在另一個執行緒開，才建得出來
        assert opened[0][1] != threading.current_thread().name
        assert browser.open("https://login.example.com/")
        assert not browser.open("smb://server/share")
        assert not browser.open("file:///etc/passwd")
        assert launched == ["https://login.example.com/"]
    finally:
        gateway.close()


def test_offline_page() -> None:
    render = offline_page(lambda: "en", lambda: SERVER)
    html = render("connection refused <x>")
    assert t.messages("en")["recorder.offline_title"] in html
    assert "connection refused &lt;x&gt;" in html
    assert "location.reload()" in html
    assert "__gateway" not in html  # 不放帶著密語的網址


# ---------------------------------------------------------------- 不開 App 視窗（--no-window）


class NoWindow:
    """在背景執行緒跑 ``recorder_headless.main``，回傳結束碼。"""

    def __init__(self, home: Path, fakes: Fakes, store: MemoryStore, argv: Sequence[str]) -> None:
        self.home = home
        self.opened: list[str] = []
        self.code: list[int] = []
        self.thread = threading.Thread(
            target=lambda: self.code.append(
                recorder_headless.main(
                    argv,
                    environ={"RPA_RECORDER_HOME": str(home)},
                    store=store,
                    services=fakes.services(),
                    open_browser=self.opened.append,
                )
            ),
            daemon=True,
        )
        self.thread.start()

    def finished(self, timeout: float = 30) -> int:
        self.thread.join(timeout)
        assert self.code, "--no-window 沒有結束"
        return self.code[0]


def test_no_window_pairs_and_stops_on_request(
    tmp_path: Path, fakes: Fakes, store: MemoryStore
) -> None:
    home, url_file = tmp_path / "home", tmp_path / "portal.txt"
    argv = ["--invite", LINE, "--url-file", str(url_file), "--open", "--firefox"]
    run = NoWindow(home, fakes, store, argv)
    assert fakes.started.wait(10)
    assert wait_for(lambda: bool(run.opened), 5)
    url = url_file.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"http://127\.0\.0\.1:\d+/__gateway/login\?key=[^&]+&next=/", url)
    assert url_file.stat().st_mode & 0o077 == 0  # 網址帶著閘道的密語：只有本人能讀
    assert run.opened == [url]  # --open：連上後用預設瀏覽器打開一次
    assert fakes.downloaded == ["chromium"]
    assert fakes.paired[0][1] == "recorder"
    # 有頭模式照樣可以用：上線時回報能顯示視窗（沒有的只是 App 自己的視窗）
    assert fakes.hosts[0].info["display"] is True
    assert json.loads((home / "settings.json").read_text(encoding="utf-8"))["firefox"] is True
    InstanceLock(home).request_stop()
    assert run.finished() == 0
    assert fakes.stopped_all >= 1  # 不等長輪詢：直接結束子程序
    assert not url_file.exists()
    assert fakes.site.closed


@pytest.mark.parametrize(
    ("setup", "argv", "code"),
    [
        ("none", [], 2),  # 沒有配對也沒有邀請
        ("rejected", ["--invite", LINE], 1),
        ("download", ["--invite", LINE], 3),
    ],
)
def test_no_window_exit_codes(
    tmp_path: Path, fakes: Fakes, store: MemoryStore, setup: str, argv: list[str], code: int
) -> None:
    if setup == "rejected":
        fakes.fatal = ("權杖已失效", 401)
    if setup == "download":
        fakes.download_codes = {"chromium": 1}
    assert NoWindow(tmp_path / "home", fakes, store, argv).finished() == code
    if setup == "rejected":
        assert not store.items  # 被拒時清除配對


def test_no_window_refuses_a_second_copy(tmp_path: Path, fakes: Fakes, store: MemoryStore) -> None:
    home = tmp_path / "home"
    held = InstanceLock(home)
    assert held.acquire()
    try:
        assert NoWindow(home, fakes, store, ["--invite", LINE]).finished() == 4
    finally:
        held.release()
    assert not fakes.paired
