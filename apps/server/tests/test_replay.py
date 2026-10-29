"""運行回看（M12）：回看頁的資料與頁面、運行報告的錄影欄與「只看有錄影的」篩選。

假的執行器照 runner 的做法留下場景快照、步驟紀錄、頁面事實、每一步的截圖與一段最小的影片
（只有標頭，瀏覽器播不出畫面）。大部分不需要瀏覽器；時間軸的排法（依步驟的章節軸，2026-10-29）
用 Chromium 打開回看頁檢查（標了 browser）。真實錄影的播放、拖曳與點步驟跳轉在 test_replay_flow.py。
"""

import base64
import itertools
import json
import re
import shutil
import socket
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import uvicorn
from fastapi import FastAPI
from httpx2 import Client, Response
from playwright.sync_api import Page, expect, sync_playwright

from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_runner.browser import plan_records
from rpa_runner.files import FACTS, SCENARIO_DIR, STEPS, VIDEO_TMP, write_json
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_runner.stepshots import shot_name
from rpa_runner.video import finalize, mark_page
from rpa_server.app import create_app
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.models import Run
from rpa_server.replay import step_sources
from rpa_server.services import Services
from rpa_worker import Worker
from testsite.browsers import require_engine
from testsite.webm import tiny_webm

JsonObject = dict[str, object]
STARTED = datetime(2026, 10, 21, 3, 30, 12, tzinfo=UTC)
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERX"
    "RTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2Nj"
    "Y2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAAJABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAA"
    "AAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
    "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKT"
    "lJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QA"
    "HwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD0CiiigD//2Q=="
)
"""每一步的截圖（16×9 的白色 JPEG）。"""


class StepExecutor:
    """假的執行器：每一步 0.5 秒（從影片的第 1 秒開始），``fail_at`` 那一步失敗。"""

    def __init__(self) -> None:
        self.fail_at: int | None = None
        self.record = True
        self.multiple_pages = False
        self.child_video = True
        self.lost_video = False
        self.shots = False
        """照 Runner 錄影時的做法，每一步做完留一張截圖（2026-10-29）。"""

    def __call__(
        self,
        path: Path,
        inputs: Mapping[str, object],
        *,
        out_root: Path,
        base_url: str | None = None,
        engine: str | None = None,
        headed: bool = False,
        deadline_ms: int | None = None,
        run_id: str | None = None,
        cancel: threading.Event | None = None,
        on_stage: Callable[[StageName], None] | None = None,
        login: LoginSettings | None = None,
        secrets: Mapping[str, str] | None = None,
        record_video: bool = False,
        **_files: object,
    ) -> RunResult:
        scenario = validate_file(path).scenario
        assert scenario is not None
        assert run_id is not None
        folder = out_root / run_id
        (folder / SCENARIO_DIR).mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, folder / SCENARIO_DIR / "scenario.yaml")
        records = plan_records(scenario)
        status = "passed"
        for index, record in enumerate(records):
            if self.fail_at is not None and index > self.fail_at:
                break
            record.started_at = STARTED.timestamp() + 1 + index * 0.5
            record.ended_at = record.started_at + 0.4
            record.url = f"{base_url or 'http://site'}/page{index}"
            record.status = "passed"
            if self.multiple_pages:
                record.page_id = "page-2" if 1 <= index <= 2 else "page-1"
            if index == self.fail_at:
                record.status = "failed"
                record.error = "TimeoutError: 找不到元素"
                status = "failed"
            if self.shots and record_video:
                record.shot = shot_name(index + 1)
                record.shot_at = record.ended_at + 0.05
                (folder / record.shot).parent.mkdir(parents=True, exist_ok=True)
                (folder / record.shot).write_bytes(JPEG)
        write_json(folder / STEPS, [record.to_json() for record in records])
        write_json(folder / FACTS, {"record": {"recordId": "DEMO-1", "title": "回看"}})
        if record_video and self.record:
            mark_page(folder, "page.webm", STARTED.timestamp())
            if not self.lost_video:
                (folder / VIDEO_TMP / "page.webm").write_bytes(
                    tiny_webm(duration_ms=6000, started_at=STARTED, width=1280, height=800)
                )
            if self.multiple_pages and self.child_video:
                (folder / VIDEO_TMP / "popup.webm").write_bytes(
                    tiny_webm(duration_ms=2000, started_at=STARTED + timedelta(seconds=1))
                )
            finalize(folder, engine="chromium")
        return RunResult(
            run_id=run_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_hash=scenario_digest(path, scenario),
            kind="dsl",
            engine="chromium",
            directory=folder,
            started_at=now().isoformat(),
            status=status,  # pyright: ignore[reportArgumentType]
            error=None if status == "passed" else "自動化失敗",
        )


@pytest.fixture
def executor() -> StepExecutor:
    return StepExecutor()


@pytest.fixture
def worker(app: FastAPI, executor: StepExecutor) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


@pytest.fixture(autouse=True)
def _examples(client: Client) -> None:
    assert client.post("/api/scenes/import").status_code < 400


def body(response: Response) -> JsonObject:
    assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def run_once(client: Client, worker: Worker, scene: str = "ba-001") -> str:
    run = body(client.post(f"/api/scenes/{scene}/revisions/1/validate", json={"inputs": {}}))
    assert worker.run_once() is True
    return str(run["id"])


def test_step_sources_follow_the_scenario_file() -> None:
    text = (
        "schemaVersion: 1\nid: a\nname: A\nsteps:\n"
        "  - id: open\n    action: goto\n    url: /\n\n"
        "  # 填寫\n  - id: fill\n    action: fill\n    target: { label: 標題 }\n    value: x\n"
        "verify: []\n"
    )

    assert step_sources(text) == [
        (5, "  - id: open\n    action: goto\n    url: /"),
        (10, "  - id: fill\n    action: fill\n    target: { label: 標題 }\n    value: x"),
    ]
    assert step_sources("steps: [") == []
    assert step_sources("id: a\n") == []


def test_replay_puts_steps_on_the_video_timeline(
    client: Client, worker: Worker, executor: StepExecutor
) -> None:
    executor.fail_at = 4
    run_id = run_once(client, worker)

    data = body(client.get(f"/api/runs/{run_id}/replay"))

    video = cast("JsonObject", data["video"])
    assert video["playable"] is True
    assert video["startedAt"] == "2026-10-21T03:30:12.000Z"
    assert (video["width"], video["height"]) == (1280, 800)
    assert video["keepUntil"] is not None  # 保留規則（失敗的 30 天）
    steps = cast("list[JsonObject]", data["steps"])
    assert [step["id"] for step in steps][:5] == [
        "open",
        "fill-title",
        "fill-quantity",
        "submit",
        "wait-receipt",
    ]
    assert [(step["startMs"], step["endMs"]) for step in steps[:2]] == [(1000, 1400), (1500, 1900)]
    assert data["failedStep"] == 5
    assert steps[4]["status"] == "failed"
    assert steps[5]["status"] == "skipped"
    assert steps[5]["startMs"] is None
    # 場景快照的原文與行號、定位器、場景檔裡的寫法（不是代入後的值）
    fill = steps[1]
    assert fill["line"] is not None
    assert str(fill["source"]).lstrip().startswith("- id: fill-title")
    assert fill["target"] == "{ label: 標題, exact: true }"
    assert fill["detail"] == 'value: "{{ inputs.title }}"'
    assert steps[0]["target"] == "/"
    read = next(step for step in steps if step["id"] == "read-record")
    assert read["hasFact"] is True
    assert read["fact"] == {"recordId": "DEMO-1", "title": "回看"}
    assert data["editUrl"] == "/scenes/ba-001/edit?revision=1&file=scenario.yaml"


def test_replay_links_to_neighbours(client: Client, worker: Worker, executor: StepExecutor) -> None:
    executor.fail_at = 1
    failed = run_once(client, worker)
    executor.fail_at = None
    middle = run_once(client, worker)
    last = run_once(client, worker)

    neighbors = cast("JsonObject", body(client.get(f"/api/runs/{middle}/replay"))["neighbors"])
    assert neighbors == {"previous": failed, "next": last, "previousFailed": failed}
    first = cast("JsonObject", body(client.get(f"/api/runs/{failed}/replay"))["neighbors"])
    assert first == {"previous": None, "next": middle, "previousFailed": None}


def test_replay_page_and_lists(client: Client, worker: Worker, executor: StepExecutor) -> None:
    executor.fail_at = 3
    run_id = run_once(client, worker)

    page = client.get(f"/runs/{run_id}/replay")
    assert page.status_code == 200
    html = page.text
    assert 'id="replay-video"' in html
    assert f'src="/runs/{run_id}/files/video.webm"' in html
    assert 'id="replay-data"' in html
    assert "/static/replay.js" in html
    assert "自動化在第 4 步" in html  # 結束卡
    # 運行回看的清單併進運行報告（2026-10-25）：回看頁的位置是 運行報告 › 這次運行 › 錄影回看
    assert 'href="/replay"' not in html
    assert (
        f'<a href="/runs">運行報告</a> › <a href="/runs/{run_id}">{run_id}</a> › 錄影回看' in html
    )
    moved = client.get("/replay?status=failed", follow_redirects=False)
    assert moved.status_code == 303
    assert moved.headers["location"] == "/runs?status=failed&video=1"
    listing = client.get("/runs?video=1").text
    assert f"/runs/{run_id}/replay" in listing
    assert "錄影開啟" in listing
    assert 'name="video" value="1" checked' in listing
    assert f"/runs/{run_id}/replay" in client.get("/runs").text
    assert f"/runs/{run_id}/replay" in client.get(f"/runs/{run_id}").text


@pytest.mark.parametrize("locale", ["en", "zh-Hans"])
def test_replay_page_in_other_languages(
    client: Client, worker: Worker, executor: StepExecutor, locale: str
) -> None:
    executor.fail_at = 0
    run_id = run_once(client, worker)
    client.cookies.set("rpa_lang", locale)

    page = client.get(f"/runs/{run_id}/replay")

    assert page.status_code == 200
    if locale == "en":
        assert "The automation failed at step 1" in page.text
        assert "› Replay" in page.text


def test_replay_without_video_explains_why(
    app: FastAPI, client: Client, worker: Worker, executor: StepExecutor
) -> None:
    executor.record = False
    plain = run_once(client, worker)
    executor.record = True
    recorded = run_once(client, worker)
    with services(app).sessions() as session:
        run = session.get(Run, recorded)
        assert run is not None
        run.finished_at = now() - timedelta(days=60)
        session.commit()
    services(app).videos.sweep()

    data = body(client.get(f"/api/runs/{plain}/replay"))
    assert data["video"] is None
    assert len(cast("list[object]", data["steps"])) > 0  # 步驟照樣顯示
    page = client.get(f"/runs/{plain}/replay").text
    assert 'id="replay-video"' not in page
    assert "錄影設定是關閉的" in page
    deleted = client.get(f"/runs/{recorded}/replay").text
    assert "錄影已依保留規則刪除（超過保留天數）" in deleted
    assert "已刪除" in client.get("/runs").text
    assert f"/runs/{recorded}/replay" not in client.get("/runs?video=1").text
    assert client.get("/api/runs/missing/replay").status_code == 404


def test_replay_explains_a_recording_that_was_not_saved(
    client: Client, worker: Worker, executor: StepExecutor
) -> None:
    # 開了錄影但影片沒存下來（video.json 只有 error）：回看頁說明原因，不是伺服器錯誤
    executor.lost_video = True
    run_id = run_once(client, worker)
    data = body(client.get(f"/api/runs/{run_id}/replay"))
    assert data["video"] == {"playable": False, "url": None, "error": "no_video"}
    response = client.get(f"/runs/{run_id}/replay")
    assert response.status_code == 200
    assert "這次運行的錄影沒有存下來（no_video）" in response.text
    assert 'id="replay-video"' not in response.text


def test_replay_gives_each_step_its_screenshot(
    app: FastAPI, client: Client, worker: Worker, executor: StepExecutor
) -> None:
    """錄影時每一步做完的截圖（2026-10-29）：回看資料有網址與時間，錄影刪了還在。"""
    executor.shots = True
    executor.fail_at = 2
    run_id = run_once(client, worker)
    folder = services(app).storage.run_dir(run_id)
    steps_file = folder / STEPS
    records = cast("list[JsonObject]", json.loads(steps_file.read_text(encoding="utf-8")))
    records[1]["shot"] = "../video.json"  # 只接受 Runner 產生的檔名
    write_json(steps_file, records)

    data = body(client.get(f"/api/runs/{run_id}/replay"))

    steps = cast("list[JsonObject]", data["steps"])
    assert steps[0]["shot"] == f"/runs/{run_id}/files/steps/001.jpg"
    assert steps[0]["shotMs"] == cast("int", steps[0]["endMs"]) + 50
    assert steps[1]["shot"] is None
    assert steps[2]["shot"] == f"/runs/{run_id}/files/steps/003.jpg"  # 失敗的那一步也有
    assert steps[3]["shot"] is None  # 略過的沒有
    image = client.get(f"/runs/{run_id}/files/steps/001.jpg")
    assert image.content == JPEG
    assert image.headers["cache-control"] == "private, max-age=86400"
    # 運行詳情的檔案清單只列一項，連到回看
    page = client.get(f"/runs/{run_id}").text
    assert 'data-file="steps/"' in page
    assert "每一步做完的截圖（3 張）" in page
    assert 'data-file="steps/001.jpg"' not in page

    with services(app).sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.finished_at = now() - timedelta(days=60)
        session.commit()
    services(app).videos.sweep()

    kept = body(client.get(f"/api/runs/{run_id}/replay"))
    assert cast("JsonObject", kept["video"])["playable"] is False
    assert cast("list[JsonObject]", kept["steps"])[0]["shot"] == steps[0]["shot"]
    assert client.get(f"/runs/{run_id}/files/steps/001.jpg").status_code == 200


def test_video_settings_form_is_on_the_runs_page(client: Client) -> None:
    html = client.get("/runs").text
    assert "data-video-settings" in html
    assert 'name="keepPassedDays"' in html
    assert 'value="7"' in html


def test_edit_page_can_jump_to_a_line(client: Client) -> None:
    html = client.get("/scenes/ba-001/edit?revision=1&file=scenario.yaml&line=42").text
    assert 'data-line="42"' in html


@pytest.mark.parametrize("child_video", [False, True])
def test_replay_resolves_steps_to_their_page_recordings(
    client: Client, worker: Worker, executor: StepExecutor, child_video: bool
) -> None:
    executor.multiple_pages = True
    executor.child_video = child_video
    run_id = run_once(client, worker)
    data = body(client.get(f"/api/runs/{run_id}/replay"))
    video = cast("JsonObject", data["video"])
    recordings = cast("list[JsonObject]", video["clips"])
    steps = cast("list[JsonObject]", data["steps"])
    assert [step["pageId"] for step in steps[:4]] == ["page-1", "page-2", "page-2", "page-1"]
    assert video["missingPages"] is (not child_video)
    assert recordings[0]["startMs"] == 0
    if child_video:
        assert recordings[1]["startMs"] == 1000
        assert str(recordings[1]["url"]).endswith("video-page-2.webm")
        assert recordings[1]["pageId"] == steps[1]["pageId"]


# ---------------------------------------------------------------- 時間軸的排法（需要 Chromium）


@pytest.fixture
def live(settings: Settings) -> Iterator[str]:
    """同一份資料的另一個伺服器（uvicorn，背景執行緒），給瀏覽器打開回看頁。"""
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "伺服器沒有啟動"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        sock.close()


@pytest.fixture
def page() -> Iterator[Page]:
    require_engine("chromium")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-TW")
        context.set_default_timeout(10_000)
        try:
            yield context.new_page()
        finally:
            context.close()
            browser.close()


def position(page: Page) -> float:
    return float(page.locator("#replay-timeline").get_attribute("aria-valuenow") or 0)


@pytest.mark.browser
def test_step_axis_gives_each_step_one_slot(
    client: Client, worker: Worker, executor: StepExecutor, live: str, page: Page
) -> None:
    """依步驟的時間軸（2026-10-29）：一格一步、縮圖是那一步的截圖、空檔折疊、可以切回依時間。

    假的執行器：影片 6 秒，第 1～5 步各 0.4 秒、相隔 0.5 秒（第 1 秒起），第 5 步失敗：
    開頭 1 秒與第 5 步之後（3.45～6 秒）沒有動作，折疊成兩個空檔。
    """
    executor.shots = True
    executor.fail_at = 4
    run_id = run_once(client, worker)
    steps = cast("list[JsonObject]", body(client.get(f"/api/runs/{run_id}/replay"))["steps"])
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    page.goto(f"{live}/runs/{run_id}/replay")

    tiles = page.locator(".replay-tile.step")
    expect(tiles).to_have_count(5)
    indexes = tiles.evaluate_all("all => all.map(tile => Number(tile.dataset.index))")
    assert indexes == [1, 2, 3, 4, 5]
    boxes = [tiles.nth(index).bounding_box() for index in range(5)]
    assert all(box is not None and box["width"] >= 43 for box in boxes), boxes
    lefts = [cast("dict[str, float]", box)["x"] for box in boxes]
    assert lefts == sorted(lefts)
    expect(tiles.nth(0).locator("img")).to_have_attribute("src", cast("str", steps[0]["shot"]))
    expect(page.locator('.replay-tile.step.failed[data-index="5"]')).to_have_count(1)
    gaps = page.locator(".replay-tile.gap")
    expect(gaps).to_have_count(2)
    assert all((gap.bounding_box() or {"width": 99})["width"] <= 21 for gap in gaps.all())
    expect(page.locator('.replay-seg[data-index="3"]')).to_have_count(1)

    # 點第 3 格：跳到第 3 步那一段（2.0～2.5 秒），畫面上標出第 3 步
    third = cast("dict[str, float]", boxes[2])
    page.mouse.click(third["x"] + third["width"] / 2, third["y"] + third["height"] / 2)
    assert 2.0 <= position(page) < 2.5, position(page)
    expect(page.locator("#replay-chip-n")).to_have_text("03")
    expect(tiles.nth(2)).to_contain_class("current")
    # 滑過第 2 格：預覽是那一步做完的截圖
    second = cast("dict[str, float]", boxes[1])
    page.mouse.move(second["x"] + 5, second["y"] + 10)
    expect(page.locator("#replay-preview-step")).to_contain_text("02 · ")
    expect(page.locator("#replay-preview-step")).to_contain_text("做完的畫面")

    # 播放經過最後的空檔：4× 快轉，畫面上有提示；暫停就收起
    page.keyboard.press("End")
    page.evaluate("document.getElementById('replay-timeline').focus()")
    page.mouse.click(lefts[4] + 10, third["y"] + third["height"] / 2)
    page.keyboard.press("ArrowRight")  # 第 5 步之後，空檔裡
    assert 3.7 < position(page) < 5.5, position(page)
    page.locator("#replay-play").click()
    expect(page.locator("#replay-skim")).to_be_visible()
    page.locator("#replay-play").click()
    expect(page.locator("#replay-skim")).to_be_hidden()

    # 依時間：照實際時間平均切格；記住選擇，重新整理後還是依時間
    page.locator('[data-axis="time"]').click()
    expect(page.locator(".replay-tile.step")).to_have_count(0)
    expect(page.locator(".replay-tile.frame").first).to_be_attached()
    page.reload()
    expect(page.locator('[data-axis="time"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".replay-tile.step")).to_have_count(0)
    page.locator('[data-axis="steps"]').click()
    expect(page.locator(".replay-tile.step")).to_have_count(5)
    assert not errors, errors


@pytest.mark.browser
def test_crowded_step_axis_zooms_into_a_group(
    client: Client, worker: Worker, executor: StepExecutor, live: str, page: Page
) -> None:
    """一百二十步放不下一步一格（2026-10-29）：每幾步一組、縮圖合併；點一組放大，「整次」回來。"""
    many = "".join(
        f"  - id: fill-{number}\n    action: fill\n    target: {{ css: '#title' }}\n"
        f"    value: '{number}'\n"
        for number in range(1, 121)
    )
    scenario = "schemaVersion: 1\nid: crowded\nname: 很多步\nsteps:\n" + many
    assert client.post("/api/scenes", json={"id": "crowded", "name": "很多步"}).status_code == 201
    created = client.post(
        "/api/scenes/crowded/revisions",
        json={"baseRevision": 1, "files": {"scenario.yaml": scenario}},
    )
    assert created.status_code == 201, created.text
    executor.shots = True
    run = body(client.post("/api/scenes/crowded/revisions/2/validate", json={"inputs": {}}))
    assert worker.run_once() is True

    page.goto(f"{live}/runs/{run['id']}/replay")

    groups = page.locator(".replay-band.group")
    expect(groups.first).to_be_visible()
    count = groups.count()
    assert 5 <= count <= 20, count
    expect(groups.first).to_have_text(re.compile(r"^1–\d+$"))
    # 縮圖不會一步一張：每幾步合成一格，不重疊
    bunched = page.locator(".replay-tile.step")
    assert bunched.count() < 120
    boxes = [box for box in (tile.bounding_box() for tile in bunched.all()) if box]
    pairs = itertools.pairwise(boxes)
    assert all(left["x"] + left["width"] <= right["x"] + 0.5 for left, right in pairs), boxes

    groups.nth(1).click()
    expect(page.locator("#replay-zoom")).to_be_visible()
    expect(page.locator("#replay-zoom-label")).to_contain_text("第 ")
    zoomed = page.locator(".replay-tile.step")
    expect(zoomed.first).to_be_attached()
    indexes = zoomed.evaluate_all("all => all.map(tile => Number(tile.dataset.index))")
    assert indexes == list(range(indexes[0], indexes[0] + len(indexes))), indexes
    assert all((tile.bounding_box() or {"width": 0})["width"] >= 43 for tile in zoomed.all())

    page.locator("#replay-unzoom").click()
    expect(page.locator("#replay-zoom")).to_be_hidden()
    expect(page.locator(".replay-band.group")).to_have_count(count)
