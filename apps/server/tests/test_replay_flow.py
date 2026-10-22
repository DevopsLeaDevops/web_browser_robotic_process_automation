"""端到端：真的錄影，在瀏覽器裡回看（M12）。

Portal 用 uvicorn 在背景執行緒啟動（含背景 worker）；場景與操作 Portal 的瀏覽器都是 Chromium
（CI 的網站測試只跑 Chromium；錄影本身在兩種瀏覽器的測試在 rpa_runner 的 test_video_browser.py）。
"""

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import httpx2
import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from testsite.browsers import require_engine
from testsite.server import running
from testsite.video import PAGES_SCENARIO, recording_site

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
JsonObject = dict[str, object]


@pytest.fixture
def portal(tmp_path: Path) -> Iterator[str]:
    data = tmp_path / "data"
    settings = Settings(
        data_dir=data,
        database_url=sqlite_url(data / "rpa.db"),
        examples_dir=ROOT / "scenarios/demo",
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "Portal 沒有啟動"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=60)
        sock.close()


@pytest.fixture
def page() -> Iterator[Page]:
    require_engine("chromium")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-TW")
        context.set_default_timeout(20_000)
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()


def finished(client: httpx2.Client, run: JsonObject) -> JsonObject:
    deadline = time.monotonic() + 120
    while True:
        data = cast("JsonObject", client.get(f"/api/runs/{run['id']}").json())
        if data["finished"]:
            return data
        assert time.monotonic() < deadline, "運行沒有結束"
        time.sleep(0.2)


def validate(client: httpx2.Client, scene: str, inputs: JsonObject) -> JsonObject:
    response = client.post(
        f"/api/scenes/{scene}/revisions/1/validate",
        json={"inputs": inputs, "engine": "chromium", "headless": True},
    )
    assert response.status_code == 202, response.text
    return finished(client, cast("JsonObject", response.json()))


def current_time(page: Page) -> float:
    return float(page.evaluate("document.getElementById('replay-video').currentTime"))


def test_replay_follows_steps_and_seeks(portal: str, page: Page) -> None:
    with running() as site, httpx2.Client(base_url=portal, timeout=30) as client:
        assert client.post("/api/scenes/import").status_code < 400
        for scene in ("ba-001", "ba-002"):
            client.patch(f"/api/scenes/{scene}", json={"baseUrl": site})
        passed = validate(client, "ba-001", {"title": "回看", "quantity": 2})
        assert passed["status"] == "passed", passed["error"]
        failed = validate(client, "ba-002", {"recordId": "DEMO-NOTEXIST"})
        assert failed["status"] == "failed"
        replay = cast("JsonObject", client.get(f"/api/runs/{passed['id']}/replay").json())
        steps = cast("list[JsonObject]", replay["steps"])

        # 通過的運行：停在開頭；縮圖產生；點一步跳到那一步開始前 0.4 秒
        page.goto(f"{portal}/runs/{passed['id']}/replay")
        page.wait_for_function("document.querySelectorAll('.replay-tile.ready').length >= 2")
        expect(page.locator("#replay-duration")).not_to_have_text("00:00.00")
        assert current_time(page) < 0.1
        submit = next(step for step in steps if step["id"] == "submit")
        page.locator('.replay-row[data-index="4"]').click()
        expect(page.locator(".replay-detail")).to_contain_text("從這一步播放")
        start = cast("int", submit["startMs"]) / 1000
        assert abs(current_time(page) - max(0.0, start - 0.4)) < 0.15
        expect(page.locator('.replay-row[data-index="4"]')).to_have_class("replay-row current")
        # 下一步：依步驟的順序（BA-001 的前幾步很快，常常比 0.4 秒還短）
        page.keyboard.press("l")
        expect(page.locator('.replay-row[data-index="5"]')).to_have_class("replay-row current")
        following = next(step for step in steps if step["index"] == 5)
        assert (
            abs(current_time(page) - max(0.0, cast("int", following["startMs"]) / 1000 - 0.4))
            < 0.15
        )
        # 滑過時間軸：預覽
        box = page.locator("#replay-film").bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        expect(page.locator("#replay-preview")).to_be_visible()
        # 釘選
        page.locator('[data-replay-tab][aria-controls="replay-tab-info"]').click()
        page.locator("#replay-pin").click()
        expect(page.locator("#replay-pin")).to_have_attribute("aria-pressed", "true")
        video = cast("JsonObject", client.get(f"/api/runs/{passed['id']}").json()["video"])
        assert video["pinned"] is True

        # 失敗的運行：停在失敗步驟開始前 1 秒，展開那一步
        failed_replay = cast("JsonObject", client.get(f"/api/runs/{failed['id']}/replay").json())
        index = cast("int", failed_replay["failedStep"])
        failed_step = cast("list[JsonObject]", failed_replay["steps"])[index - 1]
        page.goto(f"{portal}/runs/{failed['id']}/replay")
        expect(page.locator("#replay-located")).to_be_visible()
        expect(page.locator(".replay-detail .replay-error")).to_be_visible()
        expected = max(0.0, cast("int", failed_step["startMs"]) / 1000 - 1)
        assert abs(current_time(page) - expected) < 0.15

        # 運行報告與運行回看的清單都連到回看
        page.goto(f"{portal}/replay")
        expect(page.locator(f'a[href="/runs/{failed["id"]}/replay"]')).to_be_visible()


def test_replay_switches_pages_and_returns_to_main(portal: str, page: Page, tmp_path: Path) -> None:
    with recording_site(tmp_path) as site, httpx2.Client(base_url=portal, timeout=30) as client:
        assert (
            client.post("/api/scenes", json={"id": "video-pages", "name": "純色分頁"}).status_code
            == 201
        )
        response = client.post(
            "/api/scenes/video-pages/revisions",
            json={
                "baseRevision": 1,
                "files": {"scenario.yaml": PAGES_SCENARIO.replace("http://localhost", site)},
            },
        )
        assert response.status_code == 201, response.text
        response = client.post(
            "/api/scenes/video-pages/revisions/2/validate",
            json={"inputs": {}, "engine": "chromium", "headless": True},
        )
        assert response.status_code == 202, response.text
        run = finished(client, cast("JsonObject", response.json()))
        assert run["status"] == "passed", run["error"]
        run_id = str(run["id"])
        replay = client.get(f"/api/runs/{run_id}/replay").json()
        assert len(replay["video"]["clips"]) == 2
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{portal}/runs/{run_id}/replay")
        media = page.locator("#replay-video")
        page.wait_for_function("document.querySelectorAll('.replay-tile.ready').length >= 2")
        for index, page_id in ((5, "page-2"), (8, "page-1"), (5, "page-2")):
            page.locator(f'.replay-row[data-index="{index}"]').click()
            expect(media).to_have_attribute("data-page-id", page_id)
            expect(page.locator("#replay-gap")).to_be_hidden()
            # 真的解碼到目標分頁的畫面，不能只驗證 src 或分頁標籤。
            page.wait_for_function(
                """id => {
                const v = document.getElementById('replay-video');
                if (v.readyState < 2 || v.seeking) return false;
                const c = document.createElement('canvas'); c.width = 64; c.height = 36;
                const x = c.getContext('2d'); x.drawImage(v, 0, 0, 64, 36);
                const [r,g,b] = x.getImageData(56,30,1,1).data;
                return id === 'page-2' ? b > 200 && r < 80 && g < 80 : Math.min(r,g,b) > 200;
            }""",
                arg=page_id,
            )
        # 連續播放必須在共用時間軸上自動切回起始頁，最後停在全程末尾。
        page.keyboard.press("Home")
        page.locator("#replay-play").click()
        expect(media).to_have_attribute("data-page-id", "page-2", timeout=20_000)
        expect(media).to_have_attribute("data-page-id", "page-1", timeout=20_000)
        expect(page.locator("#replay-play")).to_have_attribute(
            "aria-label", "播放（空白鍵）", timeout=20_000
        )
        expect(page.locator("#replay-now")).to_have_text(
            page.locator("#replay-duration").inner_text()
        )
        assert not errors, errors
        # 每一頁可獨立下載；片段分開保存，不把同時錄下的背景頁重複串接。
        assert page.locator(".replay-downloads a").all_text_contents() == ["分頁 1", "分頁 2"]

        # 片段缺少長度時由媒體中繼資料補足，仍可播放；不能直接當成零長度缺片。
        manifest = next((tmp_path / "data").rglob("video.json"))
        info = json.loads(manifest.read_text())
        info["clips"][1]["durationMs"] = None
        manifest.write_text(json.dumps(info))
        page.reload()
        page.locator('.replay-row[data-index="5"]').click()
        expect(media).to_have_attribute("data-page-id", "page-2")
        expect(page.locator("#replay-gap")).to_be_hidden()
        # 舊錄影遺失新分頁：保留步驟與正確結果，不播放上一頁假裝有畫面。
        next((tmp_path / "data").rglob("video-page-2.webm")).unlink()
        page.reload()
        page.locator('.replay-row[data-index="5"]').click()
        expect(page.locator("#replay-gap")).to_be_visible()
        expect(page.locator("#replay-beyond")).to_contain_text("部分分頁影片缺失")
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "passed"

        # 瀏覽器播不了影片（例如 Safari、錄製端 App）：顯示「播不了、請下載」，不當成缺片。
        next((tmp_path / "data").rglob("video.webm")).write_bytes(b"not a webm")
        browser = page.context.browser
        assert browser is not None
        fresh = browser.new_context(locale="zh-TW")  # 新的 context，不用快取裡的影片
        try:
            other = fresh.new_page()
            other.goto(f"{portal}/runs/{run_id}/replay")
            expect(other.locator("#replay-cannot-play")).to_be_visible()
            expect(other.locator("#replay-gap")).to_be_hidden()
        finally:
            fresh.close()
