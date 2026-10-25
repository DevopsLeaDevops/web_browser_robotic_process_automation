"""真實錄影（M12）：影片和步驟對得上、失敗與取消的影片也能播放與拖曳、關閉時不錄。

在 Chromium 與 Firefox 各錄一次；影片一律用 Chromium 播放、讀出某個時間點的顏色：
頁面原本是白色，點「變紅」的那一步之後變成紅色。這一步開始前 0.3 秒應該是白的、結束後 0.3 秒
應該是紅的——影片的時間＝錄影開始時間＋t，和步驟記下的實際時間是同一個時鐘（ADR 0016）。
CI 的 Worker 測試在 Windows 上跑這些測試（取消時要留下 ffmpeg 把影片寫完）。
"""

import base64
import json
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import sync_playwright

from rpa_core.i18n import use_locale
from rpa_runner.files import STEPS, VIDEO, VIDEO_INFO, VIDEO_TMP
from rpa_runner.run import execute
from testsite.browsers import ENGINES, require_engine
from testsite.video import PAGES_SCENARIO, recording_site

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[3]
BA_001_SCRIPT = ROOT / "scenarios" / "demo" / "ba-001-script" / "scenario.yaml"
TOLERANCE = 0.3
"""對時允許的誤差（秒）。"""


SCENARIO = """\
schemaVersion: 1
id: video-sync
name: 錄影對時
browser:
  engine: chromium
  baseUrl: {base}
  viewport: {{ width: 640, height: 360 }}
deadline: {deadline}
steps:
  - id: open
    action: goto
    url: /page.html
  - id: wait-ready
    action: waitFor
    target: {{ css: '#ready' }}
  - id: turn-red
    action: click
    target: {{ css: '#go' }}
  - id: wait-done
    action: waitFor
    target: {{ css: '{last}' }}
    timeout: {timeout}
"""

_SAMPLE = """async ({ data, times }) => {
  const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
  const video = document.createElement('video');
  video.muted = true;
  video.src = URL.createObjectURL(new Blob([bytes], { type: 'video/webm' }));
  await new Promise((ok, fail) => {
    video.onloadeddata = ok;
    video.onerror = () => fail(video.error);
  });
  const canvas = document.createElement('canvas');
  canvas.width = 64; canvas.height = 36;
  const context = canvas.getContext('2d');
  const colors = [];
  for (const time of times) {
    await new Promise((ok) => { video.onseeked = ok; video.currentTime = time; });
    // 跳到之後那一格可能還沒解碼好，畫出來是黑的：等到可以畫，黑色（頁面上不會有）就再畫一次
    for (let wait = 0; video.readyState < 2 && wait < 50; wait += 1) {
      await new Promise((ok) => setTimeout(ok, 20));
    }
    let color = [0, 0, 0];
    for (let attempt = 0; attempt < 5; attempt += 1) {
      context.drawImage(video, 0, 0, 64, 36);
      color = Array.from(context.getImageData(56, 30, 1, 1).data.slice(0, 3));
      if (Math.max(...color) > 30) break;
      await new Promise((ok) => setTimeout(ok, 100));
    }
    colors.push(color);
  }
  return { duration: video.duration, colors };
}"""


@pytest.fixture(params=ENGINES)
def engine(request: pytest.FixtureRequest) -> str:
    return require_engine(str(request.param))


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    with recording_site(tmp_path_factory.mktemp("site")) as url:
        yield url


def _scenario(tmp: Path, site: str, *, last: str = "#done", timeout: int = 10000) -> Path:
    path = tmp / "video-sync.yaml"
    deadline = 60000
    text = SCENARIO.format(base=site, deadline=deadline, last=last, timeout=timeout)
    path.write_text(text, encoding="utf-8")
    return path


def _moment(text: object) -> float:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


def _sample(video: Path, times: list[float]) -> tuple[float, list[list[int]]]:
    """用 Chromium 播放影片，讀出各時間點右下角的顏色。"""
    require_engine("chromium")
    data = base64.b64encode(video.read_bytes()).decode("ascii")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            values = page.evaluate(_SAMPLE, {"data": data, "times": times})
            result = cast("dict[str, object]", values)
        finally:
            browser.close()
    return float(cast("float", result["duration"])), cast("list[list[int]]", result["colors"])


def _red(color: list[int]) -> bool:
    return color[0] > 200 and color[1] < 80 and color[2] < 80


def _white(color: list[int]) -> bool:
    return min(color) > 200


def test_video_lines_up_with_the_steps(site: str, engine: str, tmp_path: Path) -> None:
    result = execute(
        _scenario(tmp_path, site), {}, out_root=tmp_path / "runs", engine=engine, record_video=True
    )

    assert result.status == "passed", result.error
    folder = result.directory
    info = json.loads((folder / VIDEO_INFO).read_text(encoding="utf-8"))
    assert info["file"] == VIDEO
    assert info["complete"] is True, info
    assert info["repaired"] is False, info
    assert (info["width"], info["height"]) == (640, 360)
    assert not (folder / VIDEO_TMP).exists()
    steps = json.loads((folder / STEPS).read_text(encoding="utf-8"))
    assert [step["status"] for step in steps] == ["passed"] * 4
    assert steps[0]["url"].endswith("/page.html")
    start = _moment(info["startedAt"])
    click = steps[2]
    before = _moment(click["startedAt"]) - start - TOLERANCE
    after = _moment(click["endedAt"]) - start + TOLERANCE
    assert before > 0.5, (info, click)  # 有等 #ready，點擊不會在影片一開頭

    duration, colors = _sample(folder / VIDEO, [before, after])

    assert duration >= _moment(steps[3]["endedAt"]) - start - TOLERANCE, (duration, info)
    assert _white(colors[0]), (colors, info, click)
    assert _red(colors[1]), (colors, info, click)


def test_failed_step_is_in_the_video(site: str, engine: str, tmp_path: Path) -> None:
    result = execute(
        _scenario(tmp_path, site, last="#never", timeout=2000),
        {},
        out_root=tmp_path / "runs",
        engine=engine,
        record_video=True,
    )

    assert result.status == "failed"
    info = json.loads((result.directory / VIDEO_INFO).read_text(encoding="utf-8"))
    assert info["complete"] is True, info
    steps = json.loads((result.directory / STEPS).read_text(encoding="utf-8"))
    failed = steps[3]
    assert failed["status"] == "failed"
    start = _moment(info["startedAt"])
    duration, colors = _sample(
        result.directory / VIDEO, [_moment(failed["endedAt"]) - start - TOLERANCE]
    )
    assert duration >= _moment(failed["endedAt"]) - start - TOLERANCE
    assert _red(colors[0]), colors


def test_cancelled_run_keeps_a_playable_video(site: str, engine: str, tmp_path: Path) -> None:
    """取消時立刻停止操作，影片仍然有長度、能拖曳（Windows 上要留下 ffmpeg 把影片寫完）。

    等「變紅」那一步真的做完（steps.json）再取消，不靠固定的秒數：機器忙時瀏覽器開得慢，
    太早取消時頁面還沒出現，影片是空的。
    """
    cancel = threading.Event()
    steps_file = tmp_path / "runs" / "video-cancel" / STEPS

    def turned_red() -> bool:
        try:
            steps = json.loads(steps_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return any(
            step.get("id") == "turn-red" and step.get("status") == "passed" for step in steps
        )

    def cancel_later() -> None:
        ends = time.monotonic() + 40
        while time.monotonic() < ends and not turned_red():
            time.sleep(0.1)
        time.sleep(1.0)  # 頁面已經變紅、正在等不會出現的元素
        cancel.set()

    threading.Thread(target=cancel_later, daemon=True).start()
    result = execute(
        _scenario(tmp_path, site, last="#never", timeout=30000),
        {},
        out_root=tmp_path / "runs",
        engine=engine,
        record_video=True,
        cancel=cancel,
        run_id="video-cancel",
    )

    assert result.status == "cancelled", result.error
    info = json.loads((result.directory / VIDEO_INFO).read_text(encoding="utf-8"))
    assert info["file"] == VIDEO, info
    assert info["complete"] is True, info
    assert info["repaired"] is False, info
    assert not (result.directory / VIDEO_TMP).exists()
    duration, colors = _sample(result.directory / VIDEO, [0.1, 1e6])
    assert duration > 1.0
    assert _white(colors[0]), colors
    assert _red(colors[1]), colors


def test_timed_out_run_keeps_a_playable_video(site: str, engine: str, tmp_path: Path) -> None:
    result = execute(
        _scenario(tmp_path, site, last="#never", timeout=30000),
        {},
        out_root=tmp_path / "runs",
        engine=engine,
        record_video=True,
        deadline_ms=5000,
    )

    assert result.status == "timed_out", result.error
    info = json.loads((result.directory / VIDEO_INFO).read_text(encoding="utf-8"))
    assert info["complete"] is True, info


def test_no_video_unless_asked(site: str, tmp_path: Path) -> None:
    require_engine("chromium")
    result = execute(_scenario(tmp_path, site), {}, out_root=tmp_path / "runs", engine="chromium")

    assert result.status == "passed", result.error
    assert not (result.directory / VIDEO).exists()
    assert not (result.directory / VIDEO_INFO).exists()
    assert not (result.directory / VIDEO_TMP).exists()


def test_python_script_scenarios_are_not_recorded(tmp_path: Path) -> None:
    """Python 腳本場景自己開瀏覽器，M12 不錄（使用者 2026-10-20 的決定 D5）。"""
    from testsite.server import running

    require_engine("chromium")
    with running() as url:
        result = execute(
            BA_001_SCRIPT,
            {"title": "腳本", "quantity": 1},
            out_root=tmp_path,
            base_url=url,
            engine="chromium",
            record_video=True,
        )

    assert result.status == "passed", result.error
    assert not (result.directory / VIDEO).exists()
    assert not (result.directory / VIDEO_INFO).exists()


@pytest.mark.parametrize("close_child", [False, True], ids=["open-popup", "closed-popup"])
@pytest.mark.parametrize("headed", [False, True], ids=["headless", "headed"])
def test_chromium_keeps_popup_and_return_to_main(
    site: str, tmp_path: Path, headed: bool, close_child: bool
) -> None:
    require_engine("chromium")
    path = tmp_path / "pages.yaml"
    scenario = (
        PAGES_SCENARIO
        if close_child
        else "\n".join(line for line in PAGES_SCENARIO.splitlines() if "id: close," not in line)
    )
    path.write_text(scenario, encoding="utf-8")
    result = execute(
        path,
        {},
        out_root=tmp_path / "runs",
        base_url=site,
        engine="chromium",
        headed=headed,
        record_video=True,
    )
    assert result.status == "passed", result.error
    info = json.loads((result.directory / VIDEO_INFO).read_text())
    steps = json.loads((result.directory / STEPS).read_text())
    clips = info["clips"]
    assert len(clips) == 2
    assert {clip["pageId"] for clip in clips} == {"page-1", "page-2"}
    assert steps[2]["createdPageId"] == "page-2"
    assert [step["pageId"] for step in steps] == ["page-1"] * 3 + ["page-2"] * (
        4 if close_child else 3
    ) + ["page-1"] * 2
    assert all(clip["complete"] for clip in clips)
    for clip, index in ((clips[1], 4), (clips[0], 7 if close_child else 6)):
        click = steps[index]
        start = _moment(clip["startedAt"])
        _, colors = _sample(
            result.directory / clip["file"],
            [
                _moment(click["startedAt"]) - start - TOLERANCE,
                _moment(click["endedAt"]) - start + TOLERANCE,
            ],
        )
        assert not _red(colors[0]), (clip, colors, click)
        assert _red(colors[1]), (clip, colors, click)
    assert not (result.directory / VIDEO_TMP).exists()
