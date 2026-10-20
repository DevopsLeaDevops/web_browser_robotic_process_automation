"""開瀏覽器時給 Firefox 的偏好設定與視窗大小（:mod:`rpa_runner.contexts`）。

不需要瀏覽器：用假的 Playwright 記下收到的參數。
"""

import contextlib
from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Playwright

from rpa_runner import contexts
from rpa_runner.contexts import FIREFOX_PREFS, open_context


class FakeContext:
    def __init__(self) -> None:
        self.pages: list[object] = []

    def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self) -> None:
        self.context_options: dict[str, object] = {}

    def new_context(self, **options: object) -> FakeContext:
        self.context_options = options
        return FakeContext()

    def close(self) -> None:
        return None


class FakeBrowserType:
    def __init__(self) -> None:
        self.launch_options: dict[str, object] = {}
        self.persistent_options: dict[str, object] = {}
        self.browser = FakeBrowser()

    def launch(self, **options: object) -> FakeBrowser:
        self.launch_options = options
        return self.browser

    def launch_persistent_context(self, folder: Path, **options: object) -> FakeContext:
        self.persistent_options = options
        return FakeContext()


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeBrowserType()
        self.firefox = FakeBrowserType()
        self.webkit = FakeBrowserType()


def fake() -> tuple[FakePlaywright, Playwright]:
    playwright = FakePlaywright()
    return playwright, cast("Playwright", playwright)


def test_firefox_gets_the_background_preferences() -> None:
    """Firefox 不在最前面、視窗被蓋住時也不要被調低優先權或暫停繪製（macOS 上人工登入會卡住）。"""
    playwright, typed = fake()
    contexts.launch(typed, "firefox", headed=True, timeout_ms=1000)
    prefs = cast("dict[str, object]", playwright.firefox.launch_options["firefox_user_prefs"])
    assert prefs["threads.lower_mainthread_priority_in_background.enabled"] is False
    assert prefs["dom.ipc.processPriorityManager.enabled"] is False
    assert prefs["widget.windows.window_occlusion_tracking.enabled"] is False
    assert playwright.firefox.launch_options["headless"] is False

    contexts.launch(typed, "chromium", headed=False, timeout_ms=1000)
    assert "firefox_user_prefs" not in playwright.chromium.launch_options


def test_manual_login_window_keeps_its_own_size() -> None:
    playwright, typed = fake()
    with contextlib.ExitStack() as stack:
        open_context(
            typed,
            "firefox",
            headed=True,
            timeout_ms=1000,
            budget_seconds=1,
            stack=stack,
            persistent=False,
            no_viewport=True,
        )
    assert playwright.firefox.browser.context_options["no_viewport"] is True
    assert playwright.firefox.launch_options["firefox_user_prefs"] == FIREFOX_PREFS

    with contextlib.ExitStack() as stack:
        open_context(
            typed, "chromium", headed=False, timeout_ms=1000, budget_seconds=1, stack=stack
        )
    assert playwright.chromium.browser.context_options["no_viewport"] is None  # 照舊模擬固定大小


def test_firefox_template_profile_gets_the_preferences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextlib.contextmanager
    def profile(playwright: object, *, budget_seconds: float) -> Generator[Path]:
        yield tmp_path

    monkeypatch.setattr(contexts, "firefox_profile", profile)
    playwright, typed = fake()
    with contextlib.ExitStack() as stack:
        open_context(typed, "firefox", headed=False, timeout_ms=1000, budget_seconds=1, stack=stack)
    assert playwright.firefox.persistent_options["firefox_user_prefs"] == FIREFOX_PREFS
    assert playwright.firefox.persistent_options["no_viewport"] is None
