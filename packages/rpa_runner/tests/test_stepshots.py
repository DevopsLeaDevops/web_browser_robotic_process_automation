"""每一步做完的縮小截圖（2026-10-29，任務 20261029-replay-chapters）：不需要瀏覽器。

真的拍（Chromium、Firefox）在 test_video_browser.py 的 test_each_step_has_a_screenshot。
"""

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from rpa_core.i18n import use_locale
from rpa_runner.browser import Deadline, StepRecord
from rpa_runner.files import STEP_SHOTS
from rpa_runner.report import render_report
from rpa_runner.stepshots import MAX_SHOTS, StepShots, shot_name

JPEG = b"\xff\xd8\xff\xe0fake"


class FakeSession:
    def __init__(self, metrics: dict[str, dict[str, float]]) -> None:
        self.metrics = metrics
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def send(self, method: str, params: dict[str, object] | None = None) -> object:
        self.calls.append((method, params))
        if method == "Page.getLayoutMetrics":
            return self.metrics
        return {"data": base64.b64encode(JPEG).decode("ascii")}


class FakeContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.opened = 0

    def new_cdp_session(self, _page: object) -> FakeSession:
        self.opened += 1
        return self.session


class FakePage:
    def __init__(self, *, closed: bool = False, fail: bool = False, dpr: float = 1) -> None:
        self.closed = closed
        self.fail = fail
        self.screenshots: list[dict[str, object]] = []
        self.context = FakeContext(
            FakeSession(
                {
                    "cssVisualViewport": {
                        "pageX": 0,
                        "pageY": 120,
                        "clientWidth": 1280,
                        "clientHeight": 720,
                    },
                    "cssContentSize": {"width": 1280, "height": 3000},
                    "contentSize": {"width": 1280 * dpr, "height": 3000 * dpr},
                }
            )
        )

    def is_closed(self) -> bool:
        return self.closed

    def screenshot(self, **options: object) -> bytes:
        if self.fail:
            raise PlaywrightError("Timeout 2000ms exceeded")
        self.screenshots.append(options)
        return JPEG


def shots(tmp_path: Path, *, engine: str = "chromium", headed: bool = False, seconds: float = 60):
    return StepShots(tmp_path, engine=engine, headed=headed, deadline=Deadline.after(seconds))


def record(status: str = "passed") -> StepRecord:
    return StepRecord(id="open", action="goto", name=None, status=status)  # pyright: ignore[reportArgumentType]


def test_headless_chromium_asks_the_browser_for_a_small_jpeg(tmp_path: Path) -> None:
    page = FakePage(dpr=2)
    camera = shots(tmp_path)
    first, second = record(), record()

    camera.take(cast("Page", page), first, 1)
    camera.take(cast("Page", page), second, 2)

    assert first.shot == "steps/001.jpg"
    assert first.shot_at is not None
    assert (tmp_path / "steps" / "001.jpg").read_bytes() == JPEG
    assert second.shot == "steps/002.jpg"
    assert page.context.opened == 1  # 同一個分頁沿用 DevTools 連線
    method, params = page.context.session.calls[1]
    assert method == "Page.captureScreenshot"
    assert params is not None
    assert params["format"] == "jpeg"
    # 縮成 640 寬：1280 的一半，再除掉 2 倍的裝置像素；位置是捲動後看到的那一塊
    assert params["clip"] == {"x": 0, "y": 120, "width": 1280, "height": 720, "scale": 0.25}
    assert not page.screenshots


def test_other_browsers_and_headed_chromium_use_playwright_with_a_timeout(tmp_path: Path) -> None:
    for engine, headed in (("firefox", False), ("chromium", True)):
        page = FakePage()
        step = record()

        shots(tmp_path / engine / str(headed), engine=engine, headed=headed).take(
            cast("Page", page), step, 3
        )

        assert step.shot == "steps/003.jpg"
        assert page.screenshots[0]["type"] == "jpeg"
        assert page.screenshots[0]["caret"] == "initial"  # 不注入藏游標的樣式
        assert 0 < cast("int", page.screenshots[0]["timeout"]) <= 2000
        assert not page.context.session.calls


def test_shots_never_affect_the_step(tmp_path: Path) -> None:
    camera = shots(tmp_path, engine="firefox")
    skipped, closed, failing = record("skipped"), record(), record("failed")

    camera.take(cast("Page", FakePage()), skipped, 1)
    camera.take(cast("Page", FakePage(closed=True)), closed, 2)
    camera.take(cast("Page", FakePage(fail=True)), failing, 3)

    assert (skipped.shot, closed.shot, failing.shot) == (None, None, None)
    assert failing.status == "failed"
    assert not (tmp_path / "steps").exists() or not any((tmp_path / "steps").iterdir())


def test_no_shots_near_the_deadline_or_past_the_limit(tmp_path: Path) -> None:
    late = record()
    shots(tmp_path, seconds=2).take(cast("Page", FakePage()), late, 1)
    assert late.shot is None

    camera = shots(tmp_path)
    camera.taken = MAX_SHOTS
    over = record()
    camera.take(cast("Page", FakePage()), over, MAX_SHOTS + 1)
    assert over.shot is None


def test_records_and_names() -> None:
    step = record()
    step.shot, step.shot_at = shot_name(12), 1793274451.5
    data = step.to_json()

    assert shot_name(12) == f"{STEP_SHOTS}/012.jpg"
    assert data["shot"] == "steps/012.jpg"
    assert data["shotAt"] == "2026-10-29T11:47:31.500Z"


def test_report_shows_each_step_picture_and_lists_the_folder_once() -> None:
    shot = {"id": "open", "action": "goto", "status": "passed", "durationMs": 30}
    result = SimpleNamespace(
        run_id="r1",
        scenario_id="s1",
        scenario_name="場景",
        kind="dsl",
        status="passed",
        engine="chromium",
        started_at="—",
        duration_seconds=1.0,
        stages=[],
        checks=[],
        problems=[],
        error=None,
        input={},
        output={},
        scenario_hash="abc",
        steps=[
            {**shot, "shot": "steps/001.jpg"},
            {**shot, "id": "go", "action": "click", "shot": None},
        ],
        files=["result.json", "steps/001.jpg", "steps/002.jpg", "video.webm"],
    )

    with use_locale("zh-Hant"):  # 報告用目前的語言；別的測試可能留下英文
        html = render_report(result)  # pyright: ignore[reportArgumentType]

    assert '<img class="shot" src="steps/001.jpg"' in html
    assert html.count('class="shot"') == 1
    assert '<a href="steps/002.jpg">' not in html
    assert "2 張" in html
    assert '<a href="video.webm">video.webm</a>' in html
