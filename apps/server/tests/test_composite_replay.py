"""組合運行的合併回看（2026-10-27，任務 20261027-composite-report-replay，ADR 0019）：不需要瀏覽器。

假的執行器照 runner 的做法留下場景快照、步驟紀錄與一段最小的影片（testsite.webm），每次運行比上一次
晚 30 秒開始；可以指定哪個場景在第幾步失敗。驗證接起來的時間軸（片段、步驟、轉場與說明卡）、頁面、
全部錄影的下載，以及整組的錄影保留與釘選（D6）。真實錄影的連續播放在 test_composite_replay_flow.py。
Python 節點（ADR 0020）不錄影：假的執行器照 rpa_script 的格式留下步驟（含主控台的位置）與主控台。
"""

import io
import json
import shutil
import threading
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from httpx2 import Client, Response
from playwright.sync_api import Route, expect, sync_playwright
from sqlalchemy import select

from rpa_core.dsl import validate_file
from rpa_runner.browser import plan_records
from rpa_runner.contract import check_inputs
from rpa_runner.files import AUTOMATION_LOG, RESULT, SCENARIO_DIR, STEPS, VIDEO_TMP, write_json
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_runner.stepshots import shot_name
from rpa_runner.video import finalize, mark_page
from rpa_server.domain import now
from rpa_server.models import Revision, Run, Scene, WorkflowRun
from rpa_server.services import Services
from rpa_server.videos import VideoSettings
from rpa_worker import Worker
from testsite.browsers import require_engine
from testsite.webm import tiny_webm

JsonObject = dict[str, object]
STARTED = datetime(2026, 10, 27, 14, 0, 0, tzinfo=UTC)
VIDEO_MS = 6000

THREE: JsonObject = {
    "version": 2,
    "mode": "dag",
    "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "回看"}}},
        {
            "id": "n2",
            "sceneId": "ba-002",
            "revision": 1,
            "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
        },
        {"id": "n3", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "後續"}}},
    ],
    "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
}


PYTHON_NODE = """\
schemaVersion: 1
id: py-tidy
name: 整理資料
inputs:
  recordId: { type: string }
script:
  runtime: '1'
  automation: automation.py
"""
PYTHON_AUTOMATION = """\
from rpa_script import automation


@automation
def main(run):
    with run.step("read", "讀取"):
        print("讀到 3 列")
    with run.step("sum", "加總"):
        print("合計 60")
"""
PYTHON_LOG = "讀到 3 列\n合計 60\n".encode()
PYTHON_STEPS: list[tuple[str, str, int, int, int]] = [
    ("read", "讀取", 6, 20, len("讀到 3 列\n".encode())),
    ("sum", "加總", 8, 9000, len(PYTHON_LOG)),
]
"""Python 節點的步驟：id、名稱、行號、耗時（毫秒）、這一步結束時主控台寫到哪裡。"""


class ClockExecutor:
    """假的執行器：第 k 次運行的影片從 STARTED＋30k 秒開始、長 6 秒，
    每一步 0.5 秒（從第 1 秒起）。Python 節點照 rpa_script 留下步驟與主控台，不錄影。"""

    def __init__(self) -> None:
        self.fail: dict[str, int] = {}
        self.calls = 0
        self.python_steps = True

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
        resolved, problems = check_inputs(scenario, inputs)
        assert problems == []
        started = STARTED + timedelta(seconds=30 * self.calls)
        self.calls += 1
        folder = out_root / run_id
        (folder / SCENARIO_DIR).mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, folder / SCENARIO_DIR / "scenario.yaml")
        if scenario.script is not None:
            return self._python(scenario.id, scenario.name, run_id, folder, path, resolved, started)
        records = plan_records(scenario)
        fail_at = self.fail.get(scenario.id)
        status = "passed"
        for index, record in enumerate(records):
            if fail_at is not None and index > fail_at:
                break
            record.started_at = started.timestamp() + 1 + index * 0.5
            record.ended_at = record.started_at + 0.4
            record.url = f"http://site/{scenario.id}/{index}"
            record.status = "passed"
            if index == fail_at:
                record.status = "failed"
                record.error = "TimeoutError: 找不到元素"
                status = "failed"
            if record_video:  # 錄影時每一步做完的截圖（2026-10-29）
                record.shot, record.shot_at = shot_name(index + 1), record.ended_at + 0.05
                (folder / record.shot).parent.mkdir(parents=True, exist_ok=True)
                (folder / record.shot).write_bytes(b"\xff\xd8\xff\xe0")
        write_json(folder / STEPS, [record.to_json() for record in records])
        if record_video:
            mark_page(folder, "page.webm", started.timestamp())
            (folder / VIDEO_TMP / "page.webm").write_bytes(
                tiny_webm(duration_ms=VIDEO_MS, started_at=started, width=1280, height=800)
            )
            finalize(folder, engine="chromium")
        passed = status == "passed"
        fixed = "DEMO-" + scenario.id.upper().replace("-", "")
        return RunResult(
            run_id=run_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_hash="0" * 64,
            kind="dsl",
            engine="chromium",
            directory=folder,
            started_at=now().isoformat(),
            status=status,  # pyright: ignore[reportArgumentType]
            input=resolved,
            output=(
                {
                    name: resolved.get(name, fixed if spec.type == "string" else 1)
                    for name, spec in scenario.outputs.items()
                }
                if passed
                else None
            ),
            error=None if passed else "自動化失敗",
        )

    def _python(
        self,
        scene_id: str,
        name: str,
        run_id: str,
        folder: Path,
        path: Path,
        resolved: dict[str, object],
        started: datetime,
    ) -> RunResult:
        shutil.copy2(path.parent / "automation.py", folder / SCENARIO_DIR / "automation.py")
        (folder / AUTOMATION_LOG).write_bytes(PYTHON_LOG)
        moment = started.timestamp() + 1
        records: list[dict[str, object]] = []
        written = 0
        for step_id, title, line, duration, upto in PYTHON_STEPS if self.python_steps else []:
            records.append(
                {
                    "id": step_id,
                    "action": "python",
                    "name": title,
                    "status": "passed",
                    "durationMs": duration,
                    "error": None,
                    "artifacts": [],
                    "startedAt": iso(moment),
                    "endedAt": iso(moment + duration / 1000),
                    "occurrence": 1,
                    "parent": None,
                    "source": f"automation.py:{line}",
                    "previews": [],
                    "console": [written, upto],
                }
            )
            moment += duration / 1000
            written = upto
        write_json(folder / STEPS, records)
        write_json(folder / RESULT, {"kind": "script", "checks": [], "stages": []})
        return RunResult(
            run_id=run_id,
            scenario_id=scene_id,
            scenario_name=name,
            scenario_hash="0" * 64,
            kind="script",
            engine="chromium",
            directory=folder,
            started_at=now().isoformat(),
            status="passed",
            input=resolved,
            output={},
        )


def iso(seconds: float) -> str:
    return (
        datetime.fromtimestamp(seconds, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@pytest.fixture
def executor() -> ClockExecutor:
    return ClockExecutor()


@pytest.fixture
def worker(app: FastAPI, executor: ClockExecutor) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def publish(app: FastAPI, scene_id: str) -> None:
    with services(app).sessions() as session:
        scene = session.get(Scene, scene_id)
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == scene_id, Revision.number == 1)
        ).one()
        assert scene is not None
        revision.status = "passed"
        revision.published_at = now()
        scene.published_number = 1
        session.commit()


@pytest.fixture
def composite(app: FastAPI, client: Client) -> int:
    assert client.post("/api/scenes/import").status_code < 400
    publish(app, "ba-001")
    publish(app, "ba-002")
    created = body(
        client.post("/api/workflows", json={"name": "回看測試", "definition": THREE}), 201
    )
    return int(cast("int", created["id"]))


def run(client: Client, worker: Worker, composite: int) -> str:
    started = body(client.post(f"/api/workflows/{composite}/runs", json={}), 202)
    while worker.run_once():
        pass
    return str(started["id"])


def segments(data: JsonObject) -> list[JsonObject]:
    return cast("list[JsonObject]", cast("JsonObject", data["composite"])["segments"])


def node_runs(app: FastAPI, run_id: str) -> list[Run]:
    with services(app).sessions() as session:
        return list(
            session.scalars(
                select(Run).where(Run.workflow_run_id == run_id).order_by(Run.created_at)
            )
        )


def test_videos_are_joined_on_one_timeline(client: Client, worker: Worker, composite: int) -> None:
    run_id = run(client, worker, composite)
    data = body(client.get(f"/api/workflow-runs/{run_id}/replay"))

    kinds = [(s["kind"], s.get("node"), s["startMs"], s["durationMs"]) for s in segments(data)]
    assert kinds == [
        ("video", "n1", 0, VIDEO_MS),
        ("transition", "n2", VIDEO_MS, 2000),
        ("video", "n2", VIDEO_MS + 2000, VIDEO_MS),
        ("transition", "n3", 2 * VIDEO_MS + 2000, 2000),
        ("video", "n3", 2 * VIDEO_MS + 4000, VIDEO_MS),
    ]
    # 實際隔了多久：n1 最後一步結束（第 4.4 秒）到 n2 第一步開始（第 31 秒）
    assert segments(data)[1]["gapMs"] == 26600
    video = cast("JsonObject", data["video"])
    assert video["playable"] is True
    assert video["durationMs"] == 3 * VIDEO_MS + 4000
    clips = cast("list[JsonObject]", video["clips"])
    assert [(c["pageId"], c["startMs"]) for c in clips] == [
        ("n1/page-1", 0),
        ("n2/page-1", VIDEO_MS + 2000),
        ("n3/page-1", 2 * VIDEO_MS + 4000),
    ]
    assert [card["kind"] for card in cast("list[JsonObject]", video["cards"])] == [
        "transition",
        "transition",
    ]
    steps = cast("list[JsonObject]", data["steps"])
    second = next(step for step in steps if step["node"] == "n2")
    assert (second["label"], second["id"], second["rawId"]) == ("n2·1", "n2:open", "open")
    assert second["startMs"] == VIDEO_MS + 2000 + 1000  # 那一段的開始＋在自己影片裡的位置
    assert second["shotMs"] == cast("int", second["endMs"]) + 50  # 截圖的時間也接到這一段
    assert str(second["shot"]).endswith("/files/steps/001.jpg")
    assert second["pageId"] == "n2/page-1"
    assert [step["index"] for step in steps] == list(range(1, len(steps) + 1))
    assert data["failedStep"] is None
    state = cast("JsonObject", data["videoState"])
    assert (state["count"], state["pinned"]) == (3, False)

    page = client.get(f"/playground/runs/{run_id}/replay").text
    assert 'id="replay-card"' in page
    assert 'id="replay-bands"' in page
    assert '<template id="replay-card-1">' in page
    assert "n1 的結果" in page
    assert "n2 的入參" in page
    assert "<code>recordId</code>" in page
    assert "實際隔了 26.6 s" in page
    assert f'data-url="/api/workflow-runs/{run_id}/video"' in page
    # 資訊頁：每個節點的入參與出參，可以單獨下載這個節點的錄影
    assert page.count('class="creplay-node-values"') == 3
    assert f'href="{clips[1]["url"]}" download="{run_id}-n2-video.webm"' in page
    assert "下載這個節點的錄影" in page
    report = client.get(f"/playground/runs/{run_id}").text
    assert f'href="/playground/runs/{run_id}/replay"' in report
    assert f'href="/playground/runs/{run_id}/replay?node=n2"' in report

    client.cookies.set("rpa_lang", "en")
    english = client.get(f"/playground/runs/{run_id}/replay").text
    client.cookies.delete("rpa_lang")
    assert "Replay of composite run" in english
    assert "Result of n1" in english
    assert "The real gap was 26.6 s" in english

    archive = client.get(f"/playground/runs/{run_id}/videos.zip")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as opened:
        names = opened.namelist()
        playlist = json.loads(opened.read("playlist.json"))
    assert names == ["01-n1-video.webm", "02-n2-video.webm", "03-n3-video.webm", "playlist.json"]
    assert playlist["compositeRun"] == run_id


def test_cards_explain_what_has_no_video(
    app: FastAPI, client: Client, worker: Worker, composite: int, executor: ClockExecutor
) -> None:
    executor.fail["ba-002"] = 2
    failed = run(client, worker, composite)
    data = body(client.get(f"/api/workflow-runs/{failed}/replay"))
    assert [s["kind"] for s in segments(data)] == ["video", "transition", "video", "not_run"]
    assert segments(data)[-1]["nodes"] == ["n3"]
    steps = cast("list[JsonObject]", data["steps"])
    failing = steps[cast("int", data["failedStep"]) - 1]
    assert (failing["node"], failing["rawId"], failing["label"]) == ("n2", "search", "n2·3")
    report = client.get(f"/playground/runs/{failed}").text
    assert f'href="/playground/runs/{failed}/replay?step=n2:search"' in report  # 從失敗處回看

    # 從 n2 繼續：n1 是沿用的卡片，連到原本那次的回看
    executor.fail.clear()
    resumed = body(client.post(f"/api/workflow-runs/{failed}/rerun", json={"resume": True}), 202)
    while worker.run_once():
        pass
    again = body(client.get(f"/api/workflow-runs/{resumed['id']}/replay"))
    assert [s["kind"] for s in segments(again)] == ["reused", "video", "transition", "video"]
    page = client.get(f"/playground/runs/{resumed['id']}/replay").text
    assert f'href="/playground/runs/{failed}/replay?node=n1"' in page

    # 節點的錄影被刪掉：那一段換成說明卡
    first = node_runs(app, failed)[0]
    with services(app).sessions() as session:
        row = session.get(Run, first.id)
        assert row is not None
        services(app).videos._delete(row, "expired", now())  # pyright: ignore[reportPrivateUsage]
        session.commit()
    trimmed = body(client.get(f"/api/workflow-runs/{failed}/replay"))
    assert [s["kind"] for s in segments(trimmed)] == ["no_video", "video", "not_run"]
    assert "已依保留規則刪除" in str(segments(trimmed)[0]["reason"])


def test_composite_videos_are_kept_and_pinned_together(
    app: FastAPI, client: Client, worker: Worker, composite: int, executor: ClockExecutor
) -> None:
    executor.fail["ba-002"] = 1
    failed = run(client, worker, composite)  # n1 通過、n2 失敗：整次沒通過，全部留 30 天
    members = [run.id for run in node_runs(app, failed)]
    assert len(members) == 2

    def age(days: float) -> None:
        with services(app).sessions() as session:
            moment = now() - timedelta(days=days)
            for run_id in members:
                row = session.get(Run, run_id)
                assert row is not None
                row.finished_at = moment
            group = session.get(WorkflowRun, failed)
            assert group is not None
            group.finished_at = moment
            session.commit()

    age(8)
    assert services(app).videos.sweep() == []  # 通過的 n1 沒有在 7 天後被刪
    state = body(client.put(f"/api/workflow-runs/{failed}/video", json={"pinned": True}))
    assert state["pinned"] is True
    with services(app).sessions() as session:
        assert all(
            row.video_pinned for row in session.scalars(select(Run).where(Run.id.in_(members)))
        )
    age(31)
    assert services(app).videos.sweep() == []
    # 在單一節點的回看取消釘選，也是整次一起
    body(client.put(f"/api/runs/{members[0]}/video", json={"pinned": False}))
    with services(app).sessions() as session:
        assert not any(
            row.video_pinned for row in session.scalars(select(Run).where(Run.id.in_(members)))
        )
        deleted = [
            row.video_deleted_reason
            for row in session.scalars(select(Run).where(Run.id.in_(members)))
        ]
    assert deleted == ["expired", "expired"]


def test_quota_deletes_a_whole_composite_run(
    app: FastAPI, client: Client, worker: Worker, composite: int
) -> None:
    older = run(client, worker, composite)
    newer = run(client, worker, composite)
    with services(app).sessions() as session:
        for run_id, days in ((older, 3), (newer, 1)):
            group = session.get(WorkflowRun, run_id)
            assert group is not None
            group.finished_at = now() - timedelta(days=days)
        session.commit()
    sizes = [run.video_bytes or 0 for run in node_runs(app, older)]
    services(app).save_video_settings(VideoSettings(max_total_gb=sum(sizes) * 1.5 / 1024**3))
    assert {run.video_deleted_reason for run in node_runs(app, older)} == {"quota"}
    assert {run.video_deleted_reason for run in node_runs(app, newer)} == {None}
    assert client.get(f"/playground/runs/{older}/videos.zip").status_code == 404


def python_composite(app: FastAPI, client: Client, *, browser: bool = True) -> int:
    """ba-001（瀏覽器）→ py-tidy（Python 節點）→ ba-002（瀏覽器）。

    browser 為 False 時只有 Python 節點。
    """
    services(app).queue.runtimes = lambda: ("1.0.0",)  # 這台伺服器有運行環境 1
    assert client.post("/api/scenes/import").status_code < 400
    publish(app, "ba-001")
    publish(app, "ba-002")
    assert client.post("/api/scenes", json={"id": "py-tidy", "name": "暫名"}).status_code == 201
    files = {"scenario.yaml": PYTHON_NODE, "automation.py": PYTHON_AUTOMATION}
    saved = client.post("/api/scenes/py-tidy/revisions", json={"baseRevision": 1, "files": files})
    assert saved.status_code == 201, saved.text
    with services(app).sessions() as session:
        scene = session.get(Scene, "py-tidy")
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == "py-tidy", Revision.number == 2)
        ).one()
        assert scene is not None
        revision.status = "passed"
        revision.published_at = now()
        scene.published_number = 2
        session.commit()
    python: JsonObject = {
        "id": "n2",
        "sceneId": "py-tidy",
        "revision": 2,
        "inputs": {
            "recordId": {"node": "n1", "output": "recordId"} if browser else {"value": "R1"}
        },
    }
    nodes = cast("list[JsonObject]", THREE["nodes"])
    definition: JsonObject = (
        {**THREE, "nodes": [nodes[0], python, nodes[1] | {"id": "n3"}]}
        if browser
        else {"version": 2, "mode": "dag", "nodes": [python], "edges": []}
    )
    if browser:
        definition["edges"] = [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]
        third = cast("list[JsonObject]", definition["nodes"])[2]
        third["inputs"] = {"recordId": {"node": "n1", "output": "recordId"}}
    created = body(
        client.post("/api/workflows", json={"name": "瀏覽器與 Python", "definition": definition}),
        201,
    )
    return int(cast("int", created["id"]))


def test_python_nodes_play_a_step_timeline(app: FastAPI, client: Client, worker: Worker) -> None:
    """合併回看裡的 Python 節點（ADR 0020）：一步一格的步驟時間軸，前後有轉場卡。"""
    run_id = run(client, worker, python_composite(app, client))
    data = body(client.get(f"/api/workflow-runs/{run_id}/replay"))
    low, high = 1500, 6000  # 20 ms 的一步佔 1.5 秒，9 秒的一步佔 6 秒
    kinds = [(s["kind"], s.get("node"), s["startMs"], s["durationMs"]) for s in segments(data)]
    assert kinds == [
        ("video", "n1", 0, VIDEO_MS),
        ("transition", "n2", VIDEO_MS, 2000),
        ("python", "n2", VIDEO_MS + 2000, low + high),
        ("transition", "n3", VIDEO_MS + 2000 + low + high, 2000),
        ("video", "n3", VIDEO_MS + 4000 + low + high, VIDEO_MS),
    ]
    # 轉場卡的實際間隔照樣用步驟的時間：n1 最後一步結束（第 4.4 秒）到 n2 第一步開始（第 31 秒）
    assert segments(data)[1]["gapMs"] == 26600
    video = cast("JsonObject", data["video"])
    assert [card["kind"] for card in cast("list[JsonObject]", video["cards"])] == [
        "transition",
        "python",
        "transition",
    ]
    steps = [s for s in cast("list[JsonObject]", data["steps"]) if s["node"] == "n2"]
    start = VIDEO_MS + 2000
    assert [(s["label"], s["startMs"], s["endMs"]) for s in steps] == [
        ("n2·1", start, start + low),
        ("n2·2", start + low, start + low + high),
    ]
    assert steps[1]["durationMs"] == 9000  # 實際耗時照舊
    assert steps[1]["focusLine"] == 8
    assert steps[0]["console"] == {"line": 1, "text": "讀到 3 列", "own": [1, 1]}
    assert steps[1]["console"] == {"line": 1, "text": "讀到 3 列\n合計 60", "own": [2, 2]}

    page = client.get(f"/playground/runs/{run_id}/replay").text
    assert '<template id="replay-card-2">' in page
    assert "data-python-card" in page
    assert "Python 節點" in page


def test_composite_of_only_python_nodes_still_plays(
    app: FastAPI, client: Client, worker: Worker, executor: ClockExecutor
) -> None:
    """沒有任何錄影、只有 Python 節點：照樣有播放器（時鐘走過步驟時間軸），沒有錄影可以下載。"""
    run_id = run(client, worker, python_composite(app, client, browser=False))
    data = body(client.get(f"/api/workflow-runs/{run_id}/replay"))
    assert [s["kind"] for s in segments(data)] == ["python"]
    video = cast("JsonObject", data["video"])
    assert (video["playable"], video["url"], video["clips"]) == (True, None, [])
    page = client.get(f"/playground/runs/{run_id}/replay").text
    assert '<video id="replay-video" playsinline' in page
    assert "videos.zip" not in page

    # 腳本沒有用 run.step()：說明卡說明為什麼沒有步驟時間軸
    executor.python_steps = False
    plain = run(client, worker, python_composite_again(client))
    trimmed = body(client.get(f"/api/workflow-runs/{plain}/replay"))
    assert [s["kind"] for s in segments(trimmed)] == ["no_video"]
    assert "run.step()" in str(segments(trimmed)[0]["reason"])
    assert trimmed["video"] is None


def python_composite_again(client: Client) -> int:
    """再建一個只有 Python 節點的組合場景（場景已經發布）。"""
    python: JsonObject = {
        "id": "n1",
        "sceneId": "py-tidy",
        "revision": 2,
        "inputs": {"recordId": {"value": "R2"}},
    }
    definition: JsonObject = {"version": 2, "mode": "dag", "nodes": [python], "edges": []}
    created = body(
        client.post("/api/workflows", json={"name": "只有腳本", "definition": definition}), 201
    )
    return int(cast("int", created["id"]))


@pytest.mark.browser
def test_python_step_timeline_in_the_browser(
    app: FastAPI, client: Client, worker: Worker, executor: ClockExecutor
) -> None:
    """在瀏覽器裡播 Python 節點的步驟時間軸：卡片換成目前那一步的腳本與到那一步為止的主控台。

    頁面與靜態檔由 TestClient 供應（Playwright 攔下 http://portal/ 的請求），不必啟動伺服器。
    """
    require_engine("chromium")
    only = run(client, worker, python_composite(app, client, browser=False))
    mixed = run(client, worker, python_composite_mixed(client))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(15_000)

        def handle(route: Route) -> None:
            url = urlsplit(route.request.url)
            response = client.get(url.path + (f"?{url.query}" if url.query else ""))
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={"content-type": response.headers.get("content-type", "text/html")},
            )

        page.route("http://portal/**", handle)
        try:
            page.goto(f"http://portal/playground/runs/{only}/replay")
            card = page.locator("#replay-card [data-python-card]")
            expect(card).to_contain_text("讀取")
            expect(card.locator(".replay-console .focus")).to_have_text("1讀到 3 列")
            expect(page.locator(".replay-tile.step")).to_have_count(2)
            # 每一步的縮圖畫的是自己（一步的最後一刻不算成下一步）
            expect(page.locator(".replay-tile.step.ready")).to_have_count(2)
            first = page.locator(".replay-tile.step").first.locator("canvas")
            pixels = first.evaluate(
                "canvas => canvas.toDataURL() === (() => {"
                " const other = document.querySelectorAll('.replay-tile.step canvas')[1];"
                " return other.toDataURL(); })()"
            )
            assert pixels is False
            expect(page.locator("#replay-url")).to_contain_text("automation.py:6")
            page.keyboard.press("l")  # 下一步
            expect(card).to_contain_text("加總")
            expect(card.locator(".replay-source:not(.replay-console) .focus")).to_contain_text(
                'with run.step("sum"'
            )
            expect(card.locator(".replay-console .focus")).to_have_text("2合計 60")
            page.keyboard.press("Home")
            page.locator("#replay-play").click()  # 播放：時鐘走過第一步（1.5 秒）就換成第二步
            expect(card).to_contain_text("加總", timeout=5_000)

            # 瀏覽器節點與 Python 節點接在一起：跳到 Python 節點那一段，畫面是它的第一步
            page.goto(f"http://portal/playground/runs/{mixed}/replay?node=n2")
            expect(page.locator("#replay-card [data-python-card]")).to_contain_text("讀取")
            expect(page.locator(".replay-band.python")).to_have_count(1)
        finally:
            browser.close()


def python_composite_mixed(client: Client) -> int:
    """瀏覽器節點接 Python 節點（場景都已經發布）。"""
    nodes = cast("list[JsonObject]", THREE["nodes"])
    python: JsonObject = {
        "id": "n2",
        "sceneId": "py-tidy",
        "revision": 2,
        "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
    }
    definition: JsonObject = {
        "version": 2,
        "mode": "dag",
        "nodes": [nodes[0], python],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    created = body(
        client.post("/api/workflows", json={"name": "瀏覽器接腳本", "definition": definition}), 201
    )
    return int(cast("int", created["id"]))
