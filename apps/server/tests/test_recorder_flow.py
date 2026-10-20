"""M10.2 驗收：真的 HTTP、真的瀏覽器，逐步調試的子程序在錄製端執行。

管理 Portal 用 uvicorn 在背景執行緒啟動（管理頁面與對外埠兩個埠）。錄製端是同一個程序裡的
另一個執行緒：``rpa_worker.recorder.RecorderHost``（和 ``rpa recorder``、RPA 錄製端 App 同一套），
頁面經由 ``rpa_worker.gateway.Gateway``（本機閘道）打開。

流程：裝置頁新增錄製端 → 邀請 → 配對（Client API）→ 經由閘道看到「透過錄製端」→ 經由閘道開始
BA-001 的逐步調試（無頭：CI 沒有桌面）→ 子程序在錄製端的工作資料夾執行 → 執行第一步，
截圖傳回管理 Portal、經由閘道看得到 → 結束，錄製端的暫存資料夾刪掉。Chromium 與 Firefox 各跑一次。
"""

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import uvicorn
from httpx2 import Client, Response

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_worker.environment import WorkerInfo, code_fingerprint
from rpa_worker.gateway import Gateway
from rpa_worker.pairing import CLIENT_API_PREFIX, pair, parse_invite
from rpa_worker.recorder import RecorderHost
from rpa_worker.remote import WorkerClient
from testsite.browsers import ENGINES, require_engine
from testsite.server import running

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"
JsonObject = dict[str, object]


@dataclass(frozen=True)
class Portal:
    url: str
    external: str


def _socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


@pytest.fixture
def portal(tmp_path: Path) -> Iterator[Portal]:
    pages, external = _socket(), _socket()
    port = int(external.getsockname()[1])
    data = tmp_path / "data"
    settings = Settings(
        data_dir=data,
        database_url=sqlite_url(data / "rpa.db"),
        examples_dir=DEMO,
        seed_examples=False,
        worker_port=port,
        worker_host="127.0.0.1",
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [pages, external]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "Portal 沒有啟動"
        time.sleep(0.05)
    try:
        yield Portal(f"http://127.0.0.1:{pages.getsockname()[1]}", f"http://127.0.0.1:{port}")
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        pages.close()
        external.close()


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


@dataclass
class Recorder:
    host: RecorderHost
    gateway: Gateway


@pytest.fixture
def recorder(portal: Portal, engine: str, tmp_path: Path) -> Iterator[Recorder]:
    """登記錄製端、用邀請配對，在背景執行緒執行 RecorderHost，並開一個本機閘道。"""
    with Client(base_url=portal.url, timeout=30) as client:
        body(client.post("/api/recorders", json={"id": "mac-01", "name": "測試 Mac"}), 201)
        invited = cast("JsonObject", body(client.post("/api/recorders/mac-01/invite"))["invite"])
    paired = pair(parse_invite(str(invited["line"])), "recorder")
    assert (paired.server, paired.device, paired.app) == (portal.external, "mac-01", "recorder")
    info = WorkerInfo(
        name="mac-01", fingerprint=code_fingerprint(), browsers=(engine,), display=False
    )
    host = RecorderHost(
        WorkerClient(portal.external, paired.token, prefix=CLIENT_API_PREFIX),
        info.to_json(),
        tmp_path / "recorder",
        wait_seconds=2,
    )
    stop = threading.Event()
    thread = threading.Thread(target=host.run, args=(stop,), daemon=True)
    thread.start()
    gateway = Gateway(portal.external, lambda: paired.token)
    gateway.start()
    try:
        yield Recorder(host, gateway)
    finally:
        gateway.close()
        stop.set()
        thread.join(timeout=60)


def wait_debug(
    client: Client, session: object, statuses: set[str], timeout: float = 120
) -> JsonObject:
    deadline = time.monotonic() + timeout
    while True:
        state = body(client.get(f"/api/debug/{session}"))
        if state["status"] in statuses:
            return state
        assert time.monotonic() < deadline, f"調試沒有變成 {statuses}：{state}"
        time.sleep(0.2)


def test_debug_session_runs_on_the_recorder(
    portal: Portal, site: str, engine: str, recorder: Recorder
) -> None:
    with Client(base_url=portal.url, timeout=30) as local:
        body(local.post("/api/scenes/import"))
        body(local.patch("/api/scenes/ba-001", json={"baseUrl": site}))
        deadline = time.monotonic() + 30
        while body(local.get("/api/recorders/mac-01"))["status"] != "online":
            assert time.monotonic() < deadline, "錄製端沒有上線"
            time.sleep(0.2)

    gateway = recorder.gateway
    with Client(base_url=gateway.origin, timeout=120, follow_redirects=True) as browser:
        # 沒有閘道的 Cookie：拒絕
        assert browser.get("/devices").status_code == 403
        page = browser.get(gateway.login_url("/devices"))
        assert page.status_code == 200
        assert 'id="via-recorder"' in page.text
        assert "透過錄製端「測試 Mac」" in page.text

        session = body(
            browser.post(
                "/api/scenes/ba-001/debug",
                json={"engine": engine, "headless": True},
                headers={"Origin": gateway.origin},
            ),
            202,
        )
        assert session["deviceId"] == "mac-01"
        state = wait_debug(browser, session["id"], {"ready", "failed"})
        assert state["status"] == "ready", state["message"]
        assert recorder.host.active() == 1  # 子程序在錄製端
        folders = list(recorder.host.work_dir.glob("rpa-*"))
        assert len(folders) == 1

        step = body(
            browser.post(f"/api/debug/{session['id']}/steps/0", headers={"Origin": gateway.origin})
        )
        steps = cast("list[JsonObject]", step["steps"])
        assert steps[0]["status"] == "passed", steps[0]
        shot = str(step["screenshotUrl"])
        image = browser.get(shot)
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG")  # 錄製端截的圖傳回管理 Portal

        closed = browser.delete(f"/api/debug/{session['id']}", headers={"Origin": gateway.origin})
        assert closed.status_code == 200
    deadline = time.monotonic() + 30
    while recorder.host.active() or any(folder.exists() for folder in folders):
        assert time.monotonic() < deadline, "錄製端的子程序或暫存資料夾還在"
        time.sleep(0.2)


@pytest.fixture
def no_server_browsers(monkeypatch: pytest.MonkeyPatch) -> None:
    """伺服器沒有下載瀏覽器（例如 Linux 安裝腳本裝的伺服器）；要在建立 Portal 之前換掉。"""
    from rpa_server import roles

    monkeypatch.setattr(roles, "_LOCAL_BROWSERS", lambda: frozenset[str]())


def test_role_check_runs_on_the_recorder(
    no_server_browsers: None, portal: Portal, site: str, engine: str, recorder: Recorder
) -> None:
    """伺服器沒有瀏覽器：透過錄製端按「檢查」，在錄製端（無頭）自動登入，登入狀態傳回伺服器。"""
    steps = "\n".join(
        [
            f"- {{ id: open, action: goto, url: '{site}/login' }}",
            "- { id: user, action: fill, target: { label: 帳號 }, value: manager }",
            "- { id: pw, action: fill, target: { label: 密碼 },"
            " value: '{{ secrets.TESTSITE_MANAGER_PASSWORD }}' }",
            "- { id: go, action: click, target: { role: button, name: 登入 } }",
            "- { id: wait, action: waitFor, url: /account }",
        ]
    )
    role = {
        "id": "auto-manager",
        "name": "自動登入的主管",
        "loginUrl": f"{site}/login",
        "checkUrl": f"{site}/account",
        "check": "{ testId: current-user }",
        "engine": engine,
        "autoLogin": steps,
    }
    with Client(base_url=portal.url, timeout=30) as local:
        body(local.post("/api/roles", json=role), 201)
        secret = {"value": "manager-pass"}
        body(local.put("/api/secrets/TESTSITE_MANAGER_PASSWORD", json=secret))
        deadline = time.monotonic() + 30
        while body(local.get("/api/recorders/mac-01"))["status"] != "online":
            assert time.monotonic() < deadline, "錄製端沒有上線"
            time.sleep(0.2)
        # 直接打開管理頁面（不是透過錄製端）：伺服器沒有瀏覽器，不能檢查
        refused = local.post("/api/roles/auto-manager/check")
        assert refused.status_code == 422, refused.text
        assert "role_check_unavailable" in refused.text

    gateway = recorder.gateway
    with Client(base_url=gateway.origin, timeout=120, follow_redirects=True) as browser:
        assert browser.get(gateway.login_url("/roles")).status_code == 200
        started = browser.post("/api/roles/auto-manager/check", headers={"Origin": gateway.origin})
        assert body(started, 202)["activity"] == "checking"
        deadline = time.monotonic() + 120
        while (checked := body(browser.get("/api/roles/auto-manager")))["activity"]:
            assert time.monotonic() < deadline, f"檢查沒有結束：{checked}"
            time.sleep(0.2)
    assert checked["status"] == "logged_in", checked["message"]
    assert checked["message"]  # 在錄製端自動登入過
    assert checked["stateSavedAt"] is not None  # 登入狀態傳回伺服器
