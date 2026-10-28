"""端到端：真的錄影，在瀏覽器裡看組合運行的合併回看（2026-10-27，ADR 0019）。

Portal 用 uvicorn 在背景執行緒啟動（含背景 worker）；BA-001 → BA-002 的組合場景用 Chromium
無頭執行，兩段錄影接在一條時間軸上：N 跳到下一個節點、點轉場色帶顯示卡片、播放跨過轉場接到
下一段、點某個節點的某一步跳到那裡、釘選整次的錄影。播放位置讀時間軸的 aria-valuenow
（整條時間軸的秒數，不是影片元素的）。
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


def wait_for(client: httpx2.Client, path: str) -> JsonObject:
    deadline = time.monotonic() + 180
    while True:
        data = cast("JsonObject", client.get(path).json())
        if data["finished"]:
            return data
        assert time.monotonic() < deadline, f"{path} 沒有結束"
        time.sleep(0.2)


def validate_and_publish(client: httpx2.Client, scene: str, inputs: JsonObject) -> JsonObject:
    response = client.post(
        f"/api/scenes/{scene}/revisions/1/validate",
        json={"inputs": inputs, "engine": "chromium", "headless": True},
    )
    assert response.status_code == 202, response.text
    run = wait_for(client, f"/api/runs/{response.json()['id']}")
    assert run["status"] == "passed", run["error"]
    assert client.post(f"/api/scenes/{scene}/revisions/1/publish").status_code < 400
    return run


def position(page: Page) -> float:
    """整條合併時間軸上的位置（秒）。"""
    return float(page.locator("#replay-timeline").get_attribute("aria-valuenow") or 0)


def wait_near(page: Page, seconds: float, about: object) -> None:
    """等播放位置到 ``seconds`` 附近；等不到時列出位置與目前標示的步驟。"""
    deadline = time.monotonic() + 20
    while abs(position(page) - seconds) >= 0.15:
        shown = page.locator("#replay-chip-n").inner_text()
        where = f"停在 {position(page)}（{shown}），應該是 {seconds}"
        assert time.monotonic() < deadline, f"{where}：{about}"
        page.wait_for_timeout(100)


def test_composite_replay_plays_across_nodes(portal: str, page: Page) -> None:
    with running() as site, httpx2.Client(base_url=portal, timeout=30) as client:
        assert client.post("/api/scenes/import").status_code < 400
        for scene in ("ba-001", "ba-002"):
            client.patch(f"/api/scenes/{scene}", json={"baseUrl": site})
        created = validate_and_publish(client, "ba-001", {"title": "合併回看", "quantity": 2})
        record = cast("JsonObject", created["output"])
        validate_and_publish(client, "ba-002", {"recordId": record["recordId"]})
        definition: JsonObject = {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {}},
                {
                    "id": "n2",
                    "sceneId": "ba-002",
                    "revision": 1,
                    "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
                },
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        workflow = client.post(
            "/api/workflows", json={"name": "合併回看", "definition": definition}
        )
        assert workflow.status_code == 201, workflow.text
        started = client.post(
            f"/api/workflows/{workflow.json()['id']}/runs",
            json={"engine": "chromium", "headless": True},
        )
        assert started.status_code == 202, started.text
        run_id = str(started.json()["id"])
        finished = wait_for(client, f"/api/workflow-runs/{run_id}")
        assert finished["status"] == "passed", finished["error"]

        data = cast("JsonObject", client.get(f"/api/workflow-runs/{run_id}/replay").json())
        segments = cast("list[JsonObject]", cast("JsonObject", data["composite"])["segments"])
        assert [segment["kind"] for segment in segments] == ["video", "transition", "video"]
        second_start = cast("int", segments[2]["startMs"]) / 1000
        nodes = cast("list[JsonObject]", finished["nodes"])
        first_run, second_run = (cast("JsonObject", node["run"]) for node in nodes)
        output = cast("JsonObject", first_run["output"])
        # 轉場卡的實際間隔＝第一段錄影結束到第二段開始：中間至少有開新的子程序與瀏覽器
        clips = cast("list[JsonObject]", cast("JsonObject", data["video"])["clips"])
        detail = json.dumps(
            {
                "segments": segments,
                "clips": [
                    {k: c.get(k) for k in ("pageId", "startedAt", "durationMs", "startMs")}
                    for c in clips
                ],
                "runs": [
                    {k: run.get(k) for k in ("startedAt", "finishedAt", "durationSeconds")}
                    for run in (first_run, second_run)
                ],
            }
        )
        assert cast("int", segments[1]["gapMs"]) >= 300, detail

        page.goto(f"{portal}/playground/runs/{run_id}/replay")
        page.wait_for_function("document.querySelectorAll('.replay-tile.ready').length >= 2")
        expect(page.locator(".replay-band.video")).to_have_count(2)
        assert position(page) < 0.1

        # N：跳到下一個節點那一段的開頭；網址列標出節點
        page.locator("#replay-timeline").focus()
        page.keyboard.press("n")
        expect(page.locator("#replay-url")).to_contain_text("n2 ·")
        assert abs(position(page) - second_start) < 0.15

        # 點轉場色帶：卡片顯示上一個節點的出參、下一個節點的入參
        page.locator(".replay-band.transition").click()
        card = page.locator("#replay-card")
        expect(card).to_be_visible()
        expect(card).to_contain_text("n1 的結果")
        expect(card).to_contain_text(str(output["recordId"]))  # 這次 n1 建立的紀錄

        # 播放跨過轉場：卡片收起、影片接著播第二段
        page.locator("#replay-play").click()
        page.wait_for_function(
            f"Number(document.getElementById('replay-timeline').getAttribute('aria-valuenow'))"
            f" > {second_start + 0.3}",
            timeout=15_000,
        )
        page.locator("#replay-play").click()
        expect(card).to_be_hidden()
        assert (
            page.evaluate("getComputedStyle(document.getElementById('replay-video')).visibility")
            == "visible"
        )

        # 點 n2 的「查詢」那一步：跳到它開始前 0.4 秒，但不早於 n2 那一段的開頭（不跳回轉場卡）。
        # 本機的測試網站很快，n2 的錄影開始時（第一格）前幾步可能已經做完，「查詢」離開頭很近。
        steps = cast("list[JsonObject]", data["steps"])
        search = next(step for step in steps if step["node"] == "n2" and step["rawId"] == "search")
        page.locator(f'.replay-row[data-index="{search["index"]}"]').click()
        target = max(second_start, cast("int", search["startMs"]) / 1000 - 0.4)
        wait_near(page, target, search)
        expect(page.locator("#replay-chip-n")).to_have_text(str(search["label"]))

        # 釘選整次：兩個節點的錄影都釘選
        page.locator('[data-replay-tab][aria-controls="replay-tab-info"]').click()
        page.locator("#replay-pin").click()
        expect(page.locator("#replay-pin")).to_have_attribute("aria-pressed", "true")
        for node in nodes:
            video = cast(
                "JsonObject",
                client.get(f"/api/runs/{cast('JsonObject', node['run'])['id']}").json()["video"],
            )
            assert video["pinned"] is True

        # 從報告的「回看整次運行」與 ?step= 直接定位
        page.goto(f"{portal}/playground/runs/{run_id}")
        page.locator('[data-action="composite-replay"]').click()
        expect(page).to_have_url(f"{portal}/playground/runs/{run_id}/replay")
        page.goto(f"{portal}/playground/runs/{run_id}/replay?step={search['id']}")
        expect(page.locator("#replay-chip-n")).to_have_text(str(search["label"]))
