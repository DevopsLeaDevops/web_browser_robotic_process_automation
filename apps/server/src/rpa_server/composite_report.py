"""組合運行的匯總報告（2026-10-27，任務 20261027-composite-report-replay）。

一次組合運行（workflow_runs 一筆）的所有節點彙整成一份報告，不必逐一打開各節點的報告：

- 結論：全部通過，或停在哪個節點的哪一步、錯誤是什麼、那時的截圖；後面哪些節點沒有執行。
- 數字：節點、步驟、斷言的通過數與總數；總耗時（開始到結束）與各節點實際執行的時間加總。
- 流程與時間：各節點的狀態（畫 DAG 用）與實際開始、結束（甘特時間軸）。
- 每個節點：入參（值與來源）、出參（值與流向）、階段、步驟（含定位器）、斷言、截圖、檔案。

資料來自資料庫的組合運行紀錄（WorkflowRunRecord）與各節點執行目錄的 result.json；還沒結束或
沒有 result.json 時退回 steps.json。頁面、JSON API、Agent API、離線 HTML 共用這一份資料。
時間欄位是 datetime（樣板直接用）；給 API 時用 :func:`report_json` 轉成文字。
"""

import base64
import contextlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from rpa_core.workflow import OutputBinding, Workflow
from rpa_runner.files import LOGIN_SCREENSHOT, RESULT, SCREENSHOT, STEPS, read_json_or
from rpa_server.domain import RunRecord, WorkflowNodeState, WorkflowRunRecord, now
from rpa_server.replay import step_targets
from rpa_server.storage import Storage

__all__ = [
    "NOT_PASSED_NODES",
    "build_composite_report",
    "embedded_screenshots",
    "report_json",
]

NOT_PASSED_NODES: Final = frozenset({"failed", "timed_out", "cancelled", "needs_login"})
"""沒通過的節點：報告裡預設展開，離線報告嵌入它們的截圖（D4）。"""
_PASSED_NODES: Final = frozenset({"passed", "reused"})
_ACTIVE_NODES: Final = frozenset({"pending", "queued", "running"})
_EMBED_LIMIT: Final = 8 * 1024 * 1024
"""離線報告嵌入一張截圖的大小上限；更大的只放檔名。"""


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _read_dict(path: Path) -> dict[str, object] | None:
    data = read_json_or(path, None)
    return cast("dict[str, object]", data) if isinstance(data, dict) else None


def _dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


def _flows(workflow: Workflow | None) -> dict[str, dict[str, list[str]]]:
    """節點 → 出參名稱 → 用到它的下游（``n3.recordId``），依定義的順序。"""
    flows: dict[str, dict[str, list[str]]] = {}
    if workflow is None:
        return flows
    for node in workflow.nodes:
        for name, binding in node.inputs.items():
            if isinstance(binding, OutputBinding):
                targets = flows.setdefault(binding.node, {}).setdefault(binding.output, [])
                targets.append(f"{node.id}.{name}")
    return flows


def _steps(folder: Path, result: Mapping[str, object] | None) -> list[dict[str, object]]:
    """一個節點的步驟：result.json（或執行中的 steps.json）加上場景快照裡的定位器。"""
    raw: object = result.get("steps") if result is not None else None
    source = cast("object", raw) if isinstance(raw, list) else read_json_or(folder / STEPS, [])
    records = _dicts(source)
    targets: list[str | None] = []
    if records:
        with contextlib.suppress(Exception):  # 快照讀不懂時只少了定位器，報告照樣產生
            targets = step_targets(folder)
    steps: list[dict[str, object]] = []
    for index, record in enumerate(records):
        steps.append(
            {
                "index": index + 1,
                "id": record.get("id"),
                "name": record.get("name"),
                "action": record.get("action"),
                "status": record.get("status") or "skipped",
                "durationMs": record.get("durationMs"),
                "error": record.get("error"),
                "url": record.get("url"),
                "target": targets[index] if index < len(targets) else None,
            }
        )
    return steps


def _inputs(state: WorkflowNodeState) -> list[dict[str, object]]:
    """入參：名稱、實際的值（執行過才有）與來源（預設值、固定值、前面節點的出參）。"""
    run = state.run
    given = run.input if run is not None else {}
    items: list[dict[str, object]] = []
    for name, source in state.sources.items():
        kind = source.get("kind")
        if name in given:
            value, has_value = given[name], True
        elif kind in ("value", "default"):
            value, has_value = source.get("value"), True
        else:
            value, has_value = None, False
        items.append(
            {
                "name": name,
                "value": value,
                "hasValue": has_value,
                "given": name in given,
                "source": dict(source),
            }
        )
    return items


def _outputs(run: RunRecord | None, flows: Mapping[str, list[str]]) -> list[dict[str, object]]:
    """出參：名稱、值與流向哪些下游的入參。沒有通過的節點沒有出參，只列流向。"""
    published = run.output if run is not None and run.output is not None else {}
    names = list(published)
    names.extend(name for name in flows if name not in published)
    return [
        {
            "name": name,
            "value": published.get(name),
            "hasValue": name in published,
            "to": list(flows.get(name, [])),
        }
        for name in names
    ]


def _screenshot(storage: Storage, run: RunRecord | None, status: str) -> str | None:
    """節點最後的截圖（執行目錄裡的檔名）；需要登入時沒有就用登入檢查的截圖。"""
    if run is None:
        return None
    if storage.run_file(run.id, SCREENSHOT) is not None:
        return SCREENSHOT
    if status == "needs_login" and storage.run_file(run.id, LOGIN_SCREENSHOT) is not None:
        return LOGIN_SCREENSHOT
    return None


def _node(
    storage: Storage, state: WorkflowNodeState, flows: Mapping[str, list[str]]
) -> dict[str, object]:
    run = state.run
    folder = storage.run_dir(run.id) if run is not None else None
    result = _read_dict(folder / RESULT) if folder is not None else None
    steps = _steps(folder, result) if folder is not None else []
    checks = _dicts((result or {}).get("checks"))
    stages = _dicts((result or {}).get("stages"))
    problems = [str(item) for item in cast("list[object]", (result or {}).get("problems") or [])]
    failed_step = next((step for step in steps if step["status"] == "failed"), None)
    failed_stage = next(
        (stage for stage in stages if stage.get("status") not in ("passed", "skipped")), None
    )
    reused = state.status == "reused"
    screenshot = _screenshot(storage, run, state.status)
    video = (run.video or {}) if run is not None else {}
    error = state.error or (run.error if run is not None else None)
    if state.status in _PASSED_NODES:
        error = None
    return {
        "index": state.index + 1,
        "id": state.id,
        "sceneId": state.scene_id,
        "sceneName": state.scene_name,
        "revision": state.revision,
        "status": state.status,
        "open": state.status in NOT_PASSED_NODES,
        "error": error,
        "runId": run.id if run is not None else None,
        "reusedFrom": run.workflow_run_id if reused and run is not None else None,
        "startedAt": (run.started_at or run.created_at) if run is not None else None,
        "finishedAt": run.finished_at if run is not None else None,
        "durationSeconds": run.duration_seconds if run is not None else None,
        "engine": (result or {}).get("engine") or (run.engine if run is not None else None),
        "inputs": _inputs(state),
        "outputs": _outputs(run if state.status in _PASSED_NODES else None, flows),
        "stages": stages,
        "failedStage": failed_stage,
        "steps": steps,
        "stepCounts": {
            "passed": sum(step["status"] == "passed" for step in steps),
            "total": len(steps),
        },
        "failedStep": failed_step,
        "checks": checks,
        "checkCounts": {
            "passed": sum(bool(check.get("passed")) for check in checks),
            "total": len(checks),
        },
        "problems": problems,
        "screenshot": screenshot,
        "screenshotUrl": f"/runs/{run.id}/files/{screenshot}"
        if run is not None and screenshot
        else None,
        "runUrl": f"/runs/{run.id}" if run is not None else None,
        "reportUrl": f"/runs/{run.id}/files/report.html"
        if run is not None and run.finished
        else None,
        "replayUrl": f"/runs/{run.id}/replay" if run is not None and video.get("url") else None,
        "videoDeleted": bool(video.get("deletedAt")),
        "reusedUrl": f"/playground/runs/{run.workflow_run_id}"
        if reused and run is not None and run.workflow_run_id
        else None,
    }


def _timeline(
    record: WorkflowRunRecord, nodes: Sequence[Mapping[str, object]], end: datetime
) -> dict[str, object]:
    """甘特時間軸：這次運行裡真的執行的節點，相對於整次運行的開始與結束（百分比）。"""
    start = record.created_at
    span = max(_seconds(start, end) or 0.0, 0.001)
    bars: list[dict[str, object]] = []
    for node in nodes:
        began = cast("datetime | None", node["startedAt"])
        if node["status"] == "reused" or began is None:
            continue
        finished = cast("datetime | None", node["finishedAt"]) or end
        left = min(100.0, max(0.0, (_seconds(start, began) or 0.0) / span * 100))
        width = min(100.0 - left, max(0.0, (_seconds(began, finished) or 0.0) / span * 100))
        bars.append(
            {
                "id": node["id"],
                "status": node["status"],
                "left": round(left, 3),
                "width": round(max(width, 0.4), 3),
                "seconds": _seconds(began, finished),
            }
        )
    return {"start": start, "end": end, "seconds": _seconds(start, end), "bars": bars}


def _failure(
    record: WorkflowRunRecord, nodes: Sequence[Mapping[str, object]]
) -> dict[str, object] | None:
    """沒通過時停在哪裡：哪個節點、哪一步（或哪個階段、哪些斷言）、錯誤與截圖。"""
    if record.status in ("passed", "running"):
        return None
    stopped = next((node for node in nodes if node["id"] == record.failed_node), None)
    if stopped is None:
        stopped = next((node for node in nodes if node["status"] in NOT_PASSED_NODES), None)
    if stopped is None:
        return {"node": None, "error": record.error, "status": record.status}
    checks = cast("list[dict[str, object]]", stopped["checks"])
    return {
        "node": stopped,
        "status": stopped["status"],
        "step": stopped["failedStep"],
        "stage": stopped["failedStage"],
        "failedChecks": [check for check in checks if not check.get("passed")],
        "error": stopped["error"] or record.error,
    }


def build_composite_report(
    record: WorkflowRunRecord, workflow: Workflow | None, storage: Storage
) -> dict[str, object]:
    """一次組合運行的匯總報告（見模組說明）。``workflow`` 是這次運行的定義快照。"""
    flows = _flows(workflow)
    nodes = [_node(storage, state, flows.get(state.id, {})) for state in record.nodes]
    end = record.finished_at or now()
    steps = [step for node in nodes for step in cast("list[dict[str, object]]", node["steps"])]
    checks = [check for node in nodes for check in cast("list[dict[str, object]]", node["checks"])]
    executed = [
        node
        for node in nodes
        if node["status"] not in ("reused", "skipped") and node["runId"] is not None
    ]
    busy = [
        cast("float", node["durationSeconds"])
        for node in executed
        if node["durationSeconds"] is not None
    ]
    return {
        "id": record.id,
        "status": record.status,
        "finished": record.finished,
        "workflowName": record.workflow_name,
        "workflowVersion": record.workflow_version,
        "purpose": record.purpose,
        "createdAt": record.created_at,
        "finishedAt": record.finished_at,
        "counts": {
            "nodes": {
                "passed": sum(node["status"] in _PASSED_NODES for node in nodes),
                "total": len(nodes),
            },
            "steps": {
                "passed": sum(step["status"] == "passed" for step in steps),
                "total": len(steps),
            },
            "checks": {
                "passed": sum(bool(check.get("passed")) for check in checks),
                "total": len(checks),
            },
            "reused": sum(node["status"] == "reused" for node in nodes),
        },
        "durationSeconds": _seconds(record.created_at, end),
        "busySeconds": sum(busy) if busy else None,
        "failure": _failure(record, nodes),
        "skipped": [node["id"] for node in nodes if node["status"] == "skipped"],
        "active": [node["id"] for node in nodes if node["status"] in _ACTIVE_NODES],
        "nodes": nodes,
        "statuses": {str(node["id"]): node["status"] for node in nodes},
        "timeline": _timeline(record, nodes, end),
    }


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Mapping):
        items = cast("Mapping[str, object]", value)
        return {key: _jsonable(item) for key, item in items.items()}
    if isinstance(value, list | tuple):
        elements = cast("Sequence[object]", value)
        return [_jsonable(item) for item in elements]
    return value


def report_json(report: Mapping[str, object]) -> dict[str, object]:
    """API 用的報告：時間轉成 ISO 文字；失敗摘要只留節點代號，不重複整個節點。"""
    data = cast("dict[str, object]", _jsonable(report))
    failure = data.get("failure")
    if isinstance(failure, dict):
        failure = cast("dict[str, object]", failure)
        node = failure.get("node")
        failure["node"] = (
            cast("dict[str, object]", node).get("id") if isinstance(node, dict) else None
        )
    data.pop("statuses", None)
    return data


def embedded_screenshots(report: Mapping[str, object], storage: Storage) -> dict[str, str]:
    """離線報告要嵌入的截圖（D4：只有沒通過的節點）：節點代號 → data URI。"""
    images: dict[str, str] = {}
    for node in cast("list[dict[str, object]]", report["nodes"]):
        name, run_id = node.get("screenshot"), node.get("runId")
        if node["status"] not in NOT_PASSED_NODES or not name or not run_id:
            continue
        path = storage.run_file(str(run_id), str(name))
        if path is None:
            continue
        with contextlib.suppress(OSError):
            if path.stat().st_size > _EMBED_LIMIT:
                continue
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            images[str(node["id"])] = "data:image/png;base64," + encoded
    return images
