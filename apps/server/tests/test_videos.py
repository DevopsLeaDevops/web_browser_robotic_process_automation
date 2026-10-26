"""運行的錄影（M12）：設定、運行結束時記下錄影、釘選、保留規則、影片檔的下載。

不需要瀏覽器：假的執行器照 runner 的做法在 .video/ 放一段最小的 WebM，再由 runner 的
``finalize`` 整理成 video.webm 與 video.json。真實錄影在 rpa_runner 的 test_video_browser.py
與本目錄的 test_production_flow.py。
"""

import json
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
from rpa_runner.files import VIDEO, VIDEO_INFO, VIDEO_TMP
from rpa_runner.login import LoginSettings
from rpa_runner.run import RunResult, StageName
from rpa_runner.video import finalize, mark_page
from rpa_server.domain import now
from rpa_server.models import Run
from rpa_server.services import Services
from rpa_server.videos import VideoSettings
from rpa_worker import Worker
from testsite.webm import tiny_webm

JsonObject = dict[str, object]


class VideoExecutor:
    """假的執行器：要錄影時留下一段影片；結果依 ``status``。"""

    def __init__(self) -> None:
        self.recorded: list[bool] = []
        self.status = "passed"
        self.multiple_pages = False

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
        folder.mkdir(parents=True, exist_ok=True)
        self.recorded.append(record_video)
        if record_video:
            started = datetime.now(UTC)
            mark_page(folder, "page.webm", started.timestamp())
            (folder / VIDEO_TMP / "page.webm").write_bytes(
                tiny_webm(duration_ms=2500, started_at=started)
            )
            if self.multiple_pages:
                (folder / VIDEO_TMP / "popup.webm").write_bytes(
                    tiny_webm(duration_ms=4000, started_at=started + timedelta(seconds=1))
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
            status=self.status,  # pyright: ignore[reportArgumentType]
            error=None if self.status == "passed" else "假的失敗",
        )


@pytest.fixture
def executor() -> VideoExecutor:
    return VideoExecutor()


@pytest.fixture
def worker(app: FastAPI, executor: VideoExecutor) -> Worker:
    return Worker(cast("Worker", app.state.worker).source, executor=executor)


def body(response: Response) -> JsonObject:
    assert response.status_code < 400, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def run_once(
    client: Client, worker: Worker, executor: VideoExecutor, status: str = "passed"
) -> str:
    """驗證一次 ba-001（假的執行器），回傳運行編號。"""
    executor.status = status
    run = body(client.post("/api/scenes/ba-001/revisions/1/validate", json={"inputs": {}}))
    assert worker.run_once() is True
    return str(run["id"])


def video_of(client: Client, run_id: str) -> JsonObject | None:
    return cast("JsonObject | None", body(client.get(f"/api/runs/{run_id}"))["video"])


def age(app: FastAPI, run_id: str, days: float) -> None:
    with services(app).sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.finished_at = now() - timedelta(days=days)
        session.commit()


@pytest.fixture(autouse=True)
def _examples(client: Client) -> None:
    body(client.post("/api/scenes/import"))


def test_settings_default_to_recording_everything(client: Client) -> None:
    assert body(client.get("/api/settings/video")) == {
        "enabled": True,
        "keepPassedDays": 7,
        "keepOtherDays": 30,
        "maxTotalGb": 20.0,
        "usage": {"count": 0, "bytes": 0, "pinned": 0},
    }


def test_settings_are_checked_and_saved(client: Client) -> None:
    changed = {"enabled": False, "keepPassedDays": 0, "keepOtherDays": 90, "maxTotalGb": 5}
    saved = body(client.put("/api/settings/video", json=changed))
    assert saved == {**changed, "maxTotalGb": 5.0, "usage": {"count": 0, "bytes": 0, "pinned": 0}}
    assert body(client.get("/api/settings/video"))["enabled"] is False
    for bad in ({**changed, "keepPassedDays": -1}, {**changed, "maxTotalGb": 0}, {"enabled": 1}):
        assert client.put("/api/settings/video", json=bad).status_code == 422


def test_finished_run_records_its_video(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    run_id = run_once(client, worker, executor)

    assert executor.recorded == [True]
    video = video_of(client, run_id)
    assert video is not None
    folder = services(app).storage.run_dir(run_id)
    assert video == {
        "seconds": 2.5,
        "bytes": (folder / VIDEO).stat().st_size,
        "pinned": False,
        "deletedAt": None,
        "deletedReason": None,
        "url": f"/runs/{run_id}/files/{VIDEO}",
    }
    manifest = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert {VIDEO, VIDEO_INFO} <= {item["path"] for item in manifest["files"]}
    usage = cast("JsonObject", body(client.get("/api/settings/video"))["usage"])
    assert usage["count"] == 1


def test_video_file_supports_seeking_and_caching(
    client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    run_id = run_once(client, worker, executor)

    whole = client.get(f"/runs/{run_id}/files/{VIDEO}")
    part = client.get(f"/runs/{run_id}/files/{VIDEO}", headers={"Range": "bytes=0-9"})

    assert whole.status_code == 200
    assert whole.headers["content-type"] == "video/webm"
    assert whole.headers["cache-control"] == "private, max-age=86400"
    # 直接打開 video.webm 時瀏覽器自己的播放頁也受 CSP 限制：要允許同來源的媒體
    assert "media-src 'self'" in whole.headers["content-security-policy"]
    assert part.status_code == 206
    assert part.content == whole.content[:10]


def test_report_and_run_page_link_to_the_replay(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    """有錄影時：Portal 送出的報告最上面有錄影回看；運行詳情的檔案清單裡，影片連到回看、可下載。"""
    run_id = run_once(client, worker, executor)
    folder = services(app).storage.run_dir(run_id)
    (folder / "report.html").write_text(
        "<!doctype html><html><head></head><body><main>報告</main></body></html>",
        encoding="utf-8",
    )

    report = client.get(f"/runs/{run_id}/files/report.html")
    page = client.get(f"/runs/{run_id}").text

    assert report.text.index(f'href="/runs/{run_id}/replay"') < report.text.index("<main>")
    assert (folder / "report.html").read_text(encoding="utf-8").count("replay") == 0
    assert f'<a href="/runs/{run_id}/replay" title=' in page
    assert f'href="/runs/{run_id}/files/{VIDEO}?download=1" download="{run_id}-{VIDEO}"' in page


def test_recording_can_be_turned_off(
    client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    settings = {"enabled": False, "keepPassedDays": 7, "keepOtherDays": 30, "maxTotalGb": 20}
    body(client.put("/api/settings/video", json=settings))

    run_id = run_once(client, worker, executor)

    assert executor.recorded == [False]
    assert video_of(client, run_id) is None


def test_expired_videos_are_deleted_but_runs_stay(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    old_passed = run_once(client, worker, executor)
    old_failed = run_once(client, worker, executor, status="failed")
    pinned = run_once(client, worker, executor)
    fresh = run_once(client, worker, executor)
    for run_id in (old_passed, old_failed, pinned):
        age(app, run_id, 8)
    body(client.put(f"/api/runs/{pinned}/video", json={"pinned": True}))

    deleted = services(app).videos.sweep()

    assert deleted == [old_passed]  # 失敗的留 30 天、釘選的不刪
    gone = video_of(client, old_passed)
    assert gone is not None
    assert gone["deletedReason"] == "expired"
    assert gone["url"] is None
    folder = services(app).storage.run_dir(old_passed)
    assert not (folder / VIDEO).exists()
    assert (folder / VIDEO_INFO).exists()  # 其他檔案都留著
    assert body(client.get(f"/api/runs/{old_passed}"))["status"] == "passed"
    assert client.get(f"/runs/{old_passed}/files/{VIDEO}").status_code == 404
    manifest = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert VIDEO not in {item["path"] for item in manifest["files"]}
    assert manifest["removed"][0]["path"] == VIDEO
    assert manifest["removed"][0]["reason"] == "expired"
    for run_id in (old_failed, pinned, fresh):
        video = video_of(client, run_id)
        assert video is not None
        assert video["deletedAt"] is None
    assert cast("JsonObject", video_of(client, pinned))["pinned"] is True


def test_quota_deletes_the_oldest_unpinned_videos(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    runs = [run_once(client, worker, executor) for _ in range(4)]
    for index, run_id in enumerate(runs):
        age(app, run_id, 4 - index)  # runs[0] 最舊
    body(client.put(f"/api/runs/{runs[0]}/video", json={"pinned": True}))
    size = cast("int", cast("JsonObject", video_of(client, runs[1]))["bytes"])

    services(app).save_video_settings(VideoSettings(max_total_gb=size * 2.5 / 1024**3))

    assert [cast("JsonObject", video_of(client, run_id))["deletedReason"] for run_id in runs] == [
        None,
        "quota",
        None,
        None,
    ]


def test_unpinning_applies_the_rules_again(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    run_id = run_once(client, worker, executor)
    body(client.put(f"/api/runs/{run_id}/video", json={"pinned": True}))
    age(app, run_id, 30)
    assert services(app).videos.sweep() == []

    unpinned = body(client.put(f"/api/runs/{run_id}/video", json={"pinned": False}))

    video = cast("JsonObject", unpinned["video"])
    assert video["pinned"] is False
    assert video["deletedReason"] == "expired"
    assert client.put("/api/runs/missing/video", json={"pinned": True}).status_code == 404


def test_all_page_videos_count_toward_quota_and_are_deleted_together(
    app: FastAPI, client: Client, worker: Worker, executor: VideoExecutor
) -> None:
    executor.multiple_pages = True
    run_id = run_once(client, worker, executor)
    folder = services(app).storage.run_dir(run_id)
    files = list(folder.glob("*.webm"))
    assert len(files) == 2
    info = video_of(client, run_id)
    assert info is not None
    assert info["bytes"] == sum(path.stat().st_size for path in files)
    assert info["seconds"] == 5
    for path in files:
        response = client.get(f"/runs/{run_id}/files/{path.name}", headers={"Range": "bytes=0-9"})
        assert response.status_code == 206
        assert len(response.content) == 10
    age(app, run_id, 8)
    assert services(app).videos.sweep() == [run_id]
    assert not list(folder.glob("*.webm"))
    manifest = json.loads((folder / "run.json").read_text())
    assert {item["path"] for item in manifest["removed"]} == {path.name for path in files}
    assert (folder / VIDEO_INFO).exists()
