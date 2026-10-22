"""運行回看（M12）：回看頁的資料與頁面、運行回看清單、運行報告的回看欄。

不需要瀏覽器：假的執行器照 runner 的做法留下場景快照、步驟紀錄、頁面事實與一段最小的影片。
真實錄影的播放、拖曳與點步驟跳轉在 test_replay_flow.py。
"""

import shutil
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response

from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_runner.browser import plan_records
from rpa_runner.files import FACTS, SCENARIO_DIR, STEPS, VIDEO_TMP, write_json
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_runner.video import finalize, mark_page
from rpa_server.domain import now
from rpa_server.models import Run
from rpa_server.replay import step_sources
from rpa_server.services import Services
from rpa_worker import Worker
from testsite.webm import tiny_webm

JsonObject = dict[str, object]
STARTED = datetime(2026, 10, 21, 3, 30, 12, tzinfo=UTC)


class StepExecutor:
    """假的執行器：每一步 0.5 秒（從影片的第 1 秒開始），``fail_at`` 那一步失敗。"""

    def __init__(self) -> None:
        self.fail_at: int | None = None
        self.record = True
        self.multiple_pages = False
        self.child_video = True

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
        write_json(folder / STEPS, [record.to_json() for record in records])
        write_json(folder / FACTS, {"record": {"recordId": "DEMO-1", "title": "回看"}})
        if record_video and self.record:
            mark_page(folder, "page.webm", STARTED.timestamp())
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
    assert 'href="/replay"' in html  # 選單的「運行回看」
    listing = client.get("/replay").text
    assert f"/runs/{run_id}/replay" in listing
    assert "錄影開啟" in listing
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
        assert "Run replay" in page.text


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
    assert f"/runs/{recorded}/replay" not in client.get("/replay").text
    assert client.get("/api/runs/missing/replay").status_code == 404


def test_video_settings_form_is_on_the_replay_page(client: Client) -> None:
    html = client.get("/replay").text
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
