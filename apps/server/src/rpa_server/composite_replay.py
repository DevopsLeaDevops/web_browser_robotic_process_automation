"""組合運行的合併回看（2026-10-27，任務 20261027-composite-report-replay，ADR 0019）。

一次組合運行的各節點錄影接在同一條時間軸上，一個播放器從頭看到尾（D1：不產生新的影片檔）：

- 有錄影的節點是一段，長度是它自己的回看長度（rpa_server.replay.build_replay）；它的片段、步驟
  都往後移到這一段的開始。分頁代號加上節點（``n2/page-1``），各節點的分頁不會混在一起。
- 兩段錄影之間（排隊、開瀏覽器、登入檢查、斷言，都沒有畫面）壓成 2 秒的轉場卡（D2）：上一個節點的
  出參、下一個節點的入參與來源、實際隔了多久。
- 沒有錄影的節點（已依保留規則刪除、需要登入、沒有開始、錄影關閉）是一張 3 秒的說明卡；沿用的節點
  （從停下的節點繼續）也是一張卡片，連到原本那次的回看（D3）；最後沒有執行或還沒輪到的節點合成
  一張卡片。
- 步驟依整次運行重新編號（``index``），另外記下節點與節點裡的編號（``n2·3``）；步驟代號加上節點
  （``n2:search``），網址的 ``?step=`` 才能指定到某個節點的某一步。

節點的入參、出參與狀態來自匯總報告（composite_report），卡片的文字在樣板裡產生。
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final, cast

from sqlalchemy.orm import Session

from rpa_core.workflow import Workflow
from rpa_server.composite_report import build_composite_report
from rpa_server.domain import WorkflowNodeState, WorkflowRunRecord
from rpa_server.i18n import t
from rpa_server.models import Run
from rpa_server.replay import build_replay
from rpa_server.storage import Storage
from rpa_server.videos import VideoSettings

__all__ = ["NOTE_MS", "TRANSITION_MS", "build_composite_replay", "node_page"]

TRANSITION_MS: Final = 2000
"""兩段錄影之間的轉場卡多長（D2）。"""
NOTE_MS: Final = 3000
"""說明卡（沒有錄影、沿用、沒有執行）多長。"""
_WAITING: Final = frozenset({"pending", "queued", "running"})


def node_page(node: str, page: object) -> str:
    """節點裡的分頁代號加上節點：``n2/page-1``。"""
    return f"{node}/{page or 'page-1'}"


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _no_video(
    state: WorkflowNodeState, video: Mapping[str, object] | None, stages: Sequence[object]
) -> str:
    """節點沒有錄影的原因（說明卡）。"""
    if state.run is None:
        return t("creplay.no_video_not_started")
    if video is not None and video.get("deletedAt"):
        reason = str(video.get("deletedReason") or "expired")
        return t("replay.no_video_deleted", reason=t(f"replay.deleted_{reason}"))
    if state.status == "needs_login":
        return t("creplay.no_video_login")
    if video is not None and video.get("error"):
        return t("replay.no_video_failed", error=str(video["error"]))
    automation = next(
        (
            cast("Mapping[str, object]", stage)
            for stage in stages
            if isinstance(stage, Mapping)
            and cast("Mapping[str, object]", stage).get("name") == "automation"
        ),
        None,
    )
    if automation is not None and automation.get("status") == "skipped":
        return t("creplay.no_video_no_automation")
    return t("replay.no_video_off")


class _Timeline:
    """一段一段接起來的時間軸。"""

    def __init__(self) -> None:
        self.position = 0
        self.segments: list[dict[str, object]] = []
        self.clips: list[dict[str, object]] = []
        self.steps: list[dict[str, object]] = []
        self.checks: list[dict[str, object]] = []

    def add(self, kind: str, duration: int, **fields: object) -> dict[str, object]:
        segment: dict[str, object] = {
            "index": len(self.segments),
            "kind": kind,
            "startMs": self.position,
            "durationMs": duration,
            **fields,
        }
        self.segments.append(segment)
        self.position += duration
        return segment


def build_composite_replay(
    session: Session,
    storage: Storage,
    record: WorkflowRunRecord,
    workflow: Workflow | None,
    settings: VideoSettings,
) -> tuple[dict[str, object], dict[str, object]]:
    """合併回看頁的資料（見模組說明）與匯總報告。

    回看的資料格式和單一運行的回看相同（JSON 嵌進頁面、API 回傳），另外多 ``composite``；
    匯總報告給樣板產生卡片的文字（含 datetime，不直接轉 JSON）。
    """
    report = build_composite_report(record, workflow, storage)
    details = {str(node["id"]): node for node in cast("list[dict[str, object]]", report["nodes"])}
    line = _Timeline()
    nodes: list[dict[str, object]] = []
    previous: dict[str, object] | None = None
    """上一段錄影：節點代號與它實際結束的時間（轉場卡用）。"""
    waiting: list[str] = []
    skipped: list[str] = []
    width = height = None
    missing_pages = False
    for state in record.nodes:
        detail = details.get(state.id, {})
        entry: dict[str, object] = {
            "id": state.id,
            "sceneId": state.scene_id,
            "sceneName": state.scene_name,
            "status": state.status,
            "segment": None,
            "startMs": None,
            "runUrl": detail.get("runUrl"),
            "reportUrl": detail.get("reportUrl"),
            "replayUrl": detail.get("replayUrl"),
            "reusedFrom": detail.get("reusedFrom"),
            "reusedUrl": detail.get("reusedUrl"),
            "durationSeconds": detail.get("durationSeconds"),
        }
        nodes.append(entry)
        if state.status == "skipped":
            skipped.append(state.id)
            continue
        if state.status in _WAITING and state.run is None:
            waiting.append(state.id)
            continue
        if state.status == "reused":
            segment = line.add("reused", NOTE_MS, node=state.id, status=state.status)
            entry.update(segment=segment["index"], startMs=segment["startMs"])
            previous = None
            continue
        row = session.get(Run, state.run.id) if state.run is not None else None
        data = build_replay(session, storage, row, settings) if row is not None else None
        video = cast("dict[str, object] | None", (data or {}).get("video"))
        if data is None or video is None or not video.get("playable"):
            if state.status in _WAITING:
                waiting.append(state.id)
                continue
            stages = cast("Sequence[object]", (data or {}).get("stages") or [])
            segment = line.add(
                "no_video",
                NOTE_MS,
                node=state.id,
                status=state.status,
                reason=_no_video(state, video, stages),
            )
            entry.update(segment=segment["index"], startMs=segment["startMs"])
            _add_steps(line, state, data, offset=None)
            previous = None
            continue
        started = _moment(video.get("startedAt"))
        if previous is not None:
            ended = cast("datetime | None", previous["endedAt"])
            gap = round((started - ended).total_seconds() * 1000) if started and ended else None
            line.add(
                "transition",
                TRANSITION_MS,
                node=state.id,
                prev=previous["node"],
                gapMs=max(0, gap) if gap is not None else None,
            )
        duration = int(cast("int | float", video.get("durationMs") or 0))
        segment = line.add(
            "video",
            max(duration, 1),
            node=state.id,
            status=state.status,
            page=node_page(state.id, "page-1"),
        )
        entry.update(segment=segment["index"], startMs=segment["startMs"])
        offset = cast("int", segment["startMs"])
        for clip in cast("list[dict[str, object]]", video.get("clips") or []):
            if not isinstance(clip.get("startMs"), int):
                continue
            line.clips.append(
                {
                    **clip,
                    "pageId": node_page(state.id, clip.get("pageId")),
                    "startMs": cast("int", clip["startMs"]) + offset,
                    "node": state.id,
                }
            )
        _add_steps(line, state, data, offset=offset)
        width = width or video.get("width")
        height = height or video.get("height")
        missing_pages = missing_pages or bool(video.get("missingPages"))
        previous = {
            "node": state.id,
            "endedAt": started + timedelta(milliseconds=duration) if started else None,
        }
    if skipped:
        line.add("not_run", NOTE_MS, nodes=skipped)
    if waiting:
        line.add("pending", NOTE_MS, nodes=waiting)
    playable = bool(line.clips)
    first = next((clip for clip in line.clips if clip.get("url")), None)
    cards = [
        {
            "index": segment["index"],
            "kind": segment["kind"],
            "node": segment.get("node"),
            "startMs": segment["startMs"],
            "durationMs": segment["durationMs"],
        }
        for segment in line.segments
        if segment["kind"] != "video"
    ]
    video_data: dict[str, object] | None = None
    if playable:
        video_data = {
            "playable": True,
            "url": first["url"] if first else None,
            "durationMs": line.position,
            "clips": line.clips,
            "cards": cards,
            "segments": [
                {"startMs": s["startMs"], "durationMs": s["durationMs"], "page": s["page"]}
                for s in line.segments
                if s["kind"] == "video"
            ],
            "width": width,
            "height": height,
            "complete": True,
            "missingPages": missing_pages,
        }
    failed = next((step["index"] for step in line.steps if step["status"] == "failed"), None)
    return {
        "video": video_data,
        "steps": line.steps,
        "failedStep": failed,
        "checks": line.checks,
        "stages": [],
        "error": record.error,
        "neighbors": {"previous": None, "next": None, "previousFailed": None},
        "workflow": None,
        "editUrl": "",
        "composite": {
            "id": record.id,
            "status": record.status,
            "finished": record.finished,
            "segments": line.segments,
            "nodes": nodes,
            "durationMs": line.position,
        },
    }, report


def _add_steps(
    line: _Timeline,
    state: WorkflowNodeState,
    data: Mapping[str, object] | None,
    *,
    offset: int | None,
) -> None:
    """一個節點的步驟與斷言接到整條時間軸；沒有錄影（offset 是 None）時步驟沒有時間。"""
    if data is None:
        return
    edit = str(data.get("editUrl") or "")
    for step in cast("list[dict[str, object]]", data.get("steps") or []):
        start, end = step.get("startMs"), step.get("endMs")
        line.steps.append(
            {
                **step,
                "index": len(line.steps) + 1,
                "nodeIndex": step.get("index"),
                "node": state.id,
                "label": f"{state.id}·{step.get('index')}",
                "id": f"{state.id}:{step.get('id')}",
                "rawId": step.get("id"),
                "pageId": node_page(state.id, step.get("pageId")),
                "createdPageId": node_page(state.id, step["createdPageId"])
                if step.get("createdPageId")
                else None,
                "startMs": start + offset
                if offset is not None and isinstance(start, int)
                else None,
                "endMs": end + offset if offset is not None and isinstance(end, int) else None,
                "editUrl": edit,
            }
        )
    for check in cast("list[dict[str, object]]", data.get("checks") or []):
        line.checks.append({**check, "node": state.id})
