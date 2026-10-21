"""運行回看（M12，ADR 0016）：回看頁需要的資料。

- 影片：執行目錄的 video.json（開始時間、長度、畫面大小）＋ runs 的錄影狀態
  （釘選、刪除、保留到何時）。
- 步驟：result.json（或執行中的 steps.json）每一步的開始、結束時間換算成影片裡的毫秒；再加上
  執行目錄裡場景快照的那一段原文與行號、定位器、填入的值（場景檔的寫法，不是代入後的值）、抽到的事實。
- 斷言與階段：result.json。影片只涵蓋自動化階段，斷言與出參在瀏覽器關閉後才執行。
- 前後：同一個場景的上一次、下一次、上一次沒通過的運行；組合場景的各個節點。
"""

import contextlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from rpa_core.dsl import validate_file
from rpa_core.dsl.yaml_loader import YamlLoadError, load_yaml
from rpa_core.dsl.yaml_writer import flow
from rpa_runner.files import FACTS, RESULT, SCENARIO_DIR, STEPS, read_json_or
from rpa_runner.video import read_info
from rpa_server.models import Run
from rpa_server.storage import Storage
from rpa_server.videos import VideoSettings, video_details

__all__ = ["NOT_PASSED", "build_replay", "step_sources"]

NOT_PASSED: Final = ("failed", "timed_out", "cancelled", "needs_login")
_DETAIL_FIELDS: Final = ("value", "key", "option", "as", "text", "url", "title", "count", "state")


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _offset(moment: datetime | None, start: datetime | None) -> int | None:
    if moment is None or start is None:
        return None
    return round((moment - start).total_seconds() * 1000)


def step_sources(text: str) -> list[tuple[int, str]]:
    """場景檔裡每一步的原文：(第一行的行號, 那一段文字)，依步驟的順序。讀不懂時回傳空清單。"""
    try:
        _, positions = load_yaml(text)
    except YamlLoadError:
        return []
    lines = text.splitlines()
    starts: list[tuple[int, int]] = []
    # 用 values 直接查：locate 找不到時會往上找祖先，永遠不是 None
    while (position := positions.values.get(("steps", len(starts)))) is not None:
        starts.append((position.line, max(0, position.column - 3)))
    found: list[tuple[int, str]] = []
    for index, (line, dash) in enumerate(starts):
        end = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        block = [lines[line - 1]]
        for text_line in lines[line:end]:
            stripped = text_line.strip()
            indent = len(text_line) - len(text_line.lstrip())
            if stripped and indent <= dash:
                break
            block.append(text_line)
        while len(block) > 1 and not block[-1].strip():
            block.pop()
        found.append((line, "\n".join(block)))
    return found


def _snapshot(folder: Path) -> Path | None:
    """執行目錄裡的場景快照（scenario/ 下的場景檔）。"""
    directory = folder / SCENARIO_DIR
    preferred = directory / "scenario.yaml"
    if preferred.is_file():
        return preferred
    candidates = sorted(directory.glob("*.yaml"))
    return candidates[0] if candidates else None


def _definitions(snapshot: Path | None) -> tuple[list[dict[str, object]], list[tuple[int, str]]]:
    """快照裡各步驟的定義（JSON）與原文。"""
    if snapshot is None:
        return [], []
    scenario = validate_file(snapshot).scenario
    steps: list[dict[str, object]] = []
    for step in scenario.steps or [] if scenario is not None else []:
        dumped = step.model_dump(mode="json", by_alias=True, exclude_unset=True)
        steps.append(cast("dict[str, object]", dumped))
    text = ""
    with contextlib.suppress(OSError, UnicodeDecodeError):
        text = snapshot.read_text(encoding="utf-8")
    return steps, step_sources(text)


def _describe(definition: Mapping[str, object]) -> tuple[str | None, str | None]:
    """(定位器或網址, 其他重點)：例如 ``{ label: 標題 }`` 與 ``value: '{{ inputs.title }}'``。"""
    target = definition.get("target")
    where = flow(target) if target is not None else None
    if where is None and isinstance(definition.get("url"), str):
        where = str(definition["url"])
    details = [
        f"{name}: {flow(definition[name])}"
        for name in _DETAIL_FIELDS
        if name in definition and not (name == "url" and where == definition[name])
    ]
    return where, "  ".join(details) or None


def _steps(
    folder: Path, result: Mapping[str, object] | None, start: datetime | None
) -> list[dict[str, object]]:
    raw = result.get("steps") if result is not None else None
    if not isinstance(raw, list):
        raw = read_json_or(folder / STEPS, [])
    records = [
        cast("dict[str, object]", item)
        for item in cast("list[object]", raw if isinstance(raw, list) else [])
        if isinstance(item, dict)
    ]
    definitions, sources = _definitions(_snapshot(folder))
    facts_raw = read_json_or(folder / FACTS, {})
    facts = cast("dict[str, object]", facts_raw) if isinstance(facts_raw, dict) else {}
    steps: list[dict[str, object]] = []
    for index, record in enumerate(records):
        definition = definitions[index] if index < len(definitions) else {}
        line, text = sources[index] if index < len(sources) else (None, None)
        where, detail = _describe(definition)
        name = definition.get("as")
        steps.append(
            {
                "index": index + 1,
                "id": record.get("id"),
                "name": record.get("name"),
                "action": record.get("action"),
                "status": record.get("status"),
                "durationMs": record.get("durationMs"),
                "error": record.get("error"),
                "url": record.get("url"),
                "startedAt": record.get("startedAt"),
                "endedAt": record.get("endedAt"),
                "startMs": _offset(_moment(record.get("startedAt")), start),
                "endMs": _offset(_moment(record.get("endedAt")), start),
                "target": where,
                "detail": detail,
                "fact": facts.get(name) if isinstance(name, str) and name in facts else None,
                "hasFact": isinstance(name, str) and name in facts,
                "line": line,
                "source": text,
                "artifacts": record.get("artifacts") or [],
            }
        )
    return steps


def _neighbors(session: Session, run: Run) -> dict[str, str | None]:
    """同一個場景的上一次、下一次、上一次沒通過的運行。"""
    same = Run.scene_id == run.scene_id
    earlier = (Run.created_at < run.created_at) | (
        (Run.created_at == run.created_at) & (Run.id < run.id)
    )
    later = (Run.created_at > run.created_at) | (
        (Run.created_at == run.created_at) & (Run.id > run.id)
    )
    newest_first = (Run.created_at.desc(), Run.id.desc())
    previous = session.scalar(select(Run.id).where(same, earlier).order_by(*newest_first).limit(1))
    following = session.scalar(
        select(Run.id).where(same, later).order_by(Run.created_at, Run.id).limit(1)
    )
    failed = session.scalar(
        select(Run.id)
        .where(same, earlier, Run.status.in_(NOT_PASSED))
        .order_by(*newest_first)
        .limit(1)
    )
    return {"previous": previous, "next": following, "previousFailed": failed}


def _workflow(session: Session, run: Run) -> dict[str, object] | None:
    """組合場景的序列執行：各節點的運行（依開始的順序）。"""
    if run.workflow_run_id is None:
        return None
    nodes = session.scalars(
        select(Run).where(Run.workflow_run_id == run.workflow_run_id).order_by(Run.created_at)
    ).all()
    return {
        "id": run.workflow_run_id,
        "nodes": [
            {
                "nodeId": node.node_id,
                "runId": node.id,
                "sceneId": node.scene_id,
                "status": node.status,
                "video": node.video_seconds is not None and node.video_deleted_at is None,
            }
            for node in nodes
        ],
    }


def build_replay(
    session: Session, storage: Storage, run: Run, settings: VideoSettings
) -> dict[str, object]:
    """回看頁的資料（API 與頁面共用）。"""
    folder = storage.run_dir(run.id)
    result_raw = read_json_or(folder / RESULT, None)
    result = cast("dict[str, object]", result_raw) if isinstance(result_raw, dict) else None
    info = read_info(folder) or {}
    state = video_details(run, settings)
    playable = state is not None and state.get("url") is not None and info.get("file") is not None
    start = _moment(info.get("startedAt")) if playable else None
    video: dict[str, object] | None = None
    if state is not None:
        video = {
            **state,
            "playable": playable,
            "startedAt": info.get("startedAt"),
            "durationMs": info.get("durationMs"),
            "width": info.get("width"),
            "height": info.get("height"),
            "complete": info.get("complete"),
            "repaired": info.get("repaired"),
        }
    elif info:
        video = {"playable": False, "error": info.get("error")}
    steps = _steps(folder, result, start)
    failed = next((step["index"] for step in steps if step["status"] == "failed"), None)
    return {
        "video": video,
        "steps": steps,
        "failedStep": failed,
        "checks": cast("Sequence[object]", (result or {}).get("checks") or []),
        "stages": cast("Sequence[object]", (result or {}).get("stages") or []),
        "error": run.error,
        "neighbors": _neighbors(session, run),
        "workflow": _workflow(session, run),
        "editUrl": f"/scenes/{run.scene_id}/edit?revision={run.revision_number}&file=scenario.yaml",
    }


def dumps(data: Mapping[str, object]) -> str:
    """嵌進頁面的 JSON：``</`` 換成 ``<\\/``，不會提前結束 ``<script>``。"""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
