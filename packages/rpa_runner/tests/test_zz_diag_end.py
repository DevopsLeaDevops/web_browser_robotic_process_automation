"""暫時的診斷（不合併）：Firefox 失敗的運行，影片結尾有沒有黑畫面。"""

import json
import sys
from pathlib import Path

import pytest

from rpa_runner.files import DIAGNOSTIC, STEPS, VIDEO, VIDEO_INFO
from rpa_runner.run import execute

from .test_video_browser import _moment, _sample, _scenario, site  # noqa: F401  # pyright: ignore[reportUnusedImport]

pytestmark = [pytest.mark.browser, pytest.mark.role_worker]


@pytest.mark.parametrize("engine", ["firefox", "chromium"])
@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_diag_end(site: str, tmp_path: Path, engine: str, attempt: int) -> None:  # noqa: F811
    result = execute(
        _scenario(tmp_path, site, last="#never", timeout=2000),
        {},
        out_root=tmp_path / "runs",
        engine=engine,
        record_video=True,
    )
    info = json.loads((result.directory / VIDEO_INFO).read_text(encoding="utf-8"))
    steps = json.loads((result.directory / STEPS).read_text(encoding="utf-8"))
    start = _moment(info["startedAt"])
    failed = steps[3]
    end = _moment(failed["endedAt"]) - start
    began = _moment(failed["startedAt"]) - start
    offsets = [-1.5, -1.0, -0.6, -0.3, -0.15, 0.0, 0.15, 0.3, 0.6, 1.0]
    times = [max(0.0, end + o) for o in offsets] + [1e6]
    duration, colors = _sample(result.directory / VIDEO, times)
    diag = json.loads((result.directory / DIAGNOSTIC).read_text(encoding="utf-8"))
    out = {
        "engine": engine,
        "status": result.status,
        "duration": round(duration, 2),
        "failedStart": round(began, 2),
        "failedEnd": round(end, 2),
        "firstFrameMs": info.get("firstFrameMs"),
        "startedAtSource": info.get("startedAtSource"),
        "samples": {f"{o:+}": c for o, c in zip(offsets + ["last"], colors, strict=True)},
        "diag": {k: diag.get(k) for k in ("errorType", "remainingMs")},
    }
    if engine == "chromium" and attempt > 1:
        return
    pytest.fail(f"DIAG {sys.platform}: " + json.dumps(out, ensure_ascii=False))
