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
from rpa_desktop.recorder_pages import DesktopPages, offline_page
from rpa_desktop.ui import PAGES, page_strings, render_page
from rpa_worker.environment import WorkerInfo
from rpa_worker.gateway import COOKIE, DESKTOP_PREFIX, Gateway
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
    """經由閘道送請求的小工具（帶著閘道的 Cookie）。"""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def request(
        self,
        method: str,
        path: str,
        body: object = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.gateway.port, timeout=10)
        values = {"Cookie": f"{COOKIE}={self.gateway.secret}", **(headers or {})}
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
    pages = DesktopPages(
        controller,
        on_quit=lambda: calls.append("quit"),
        on_logs=lambda: calls.append("logs"),
        on_download=lambda: calls.append("download"),
        on_ready=lambda agent: calls.append("ready:" + agent),
    )
    gateway = Gateway(None, controller.token, local=pages)
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
    # 還沒配對：管理 Portal 的網址轉到 App 自己的頁面
    status, headers, _ = browser.request("GET", "/scenes")
    assert (status, headers["location"]) == (303, DESKTOP_PREFIX)
    assert browser.request("POST", "/api/scenes", {})[0] == 409
    controller.start()
    assert phase_is(controller, "unpaired")
    status, _, data = browser.request("GET", DESKTOP_PREFIX + "state")
    assert json.loads(data)["phase"] == "unpaired"
    status, _, data = browser.request("POST", DESKTOP_PREFIX + "pair", {"invite": LINE})
    assert json.loads(data) == {"ok": True}
    assert phase_is(controller, "online")
    assert browser.gateway.server == SERVER
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
    assert browser.request("GET", DESKTOP_PREFIX + "nope")[0] == 404
    # 別的網站不能叫 App 做事
    foreign = browser.request(
        "POST", DESKTOP_PREFIX + "quit", {}, headers={"Origin": "http://evil.example"}
    )
    assert foreign[0] == 403
    assert calls.count("quit") == 1


def test_offline_page() -> None:
    render = offline_page(lambda: "en", lambda: SERVER)
    html = render("connection refused <x>")
    assert t.messages("en")["recorder.offline_title"] in html
    assert "connection refused &lt;x&gt;" in html
    assert f'href="{DESKTOP_PREFIX}"' in html
