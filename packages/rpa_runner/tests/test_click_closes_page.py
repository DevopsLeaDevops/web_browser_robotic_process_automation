"""點了之後頁面自己關掉（2026-10-28，任務 20261028-main-ci-red）：不需要瀏覽器。

按鈕執行 window.close() 時，Playwright 有時在點擊收尾才發現頁面已關，回報「Target page … has been
closed」；點擊其實已經完成，這一步算通過。頁面還開著時的錯誤照舊是失敗。
"""

from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from rpa_core.dsl.scenario import Scenario
from rpa_core.dsl.steps import ClickStep
from rpa_runner import browser
from rpa_runner.browser import StepRecord, Tabs

CLOSED = "Locator.click: Target page, context or browser has been closed"


class FakeLocator:
    def click(self, **_options: object) -> None:
        raise PlaywrightError(CLOSED)


class FakePage:
    def __init__(self, closed: bool) -> None:
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed


def click(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, closed: bool) -> None:
    def locate(*_args: object) -> FakeLocator:
        return FakeLocator()

    monkeypatch.setattr(browser, "locate", locate)
    step = ClickStep.model_validate({"id": "close", "action": "click", "target": {"css": "#close"}})
    run = browser._Run(  # pyright: ignore[reportPrivateUsage]
        tabs=cast("Tabs", None),
        scenario=cast("Scenario", None),
        base_url=None,
        artifacts=tmp_path,
        facts={},
    )
    record = StepRecord(id="close", action="click", name=None)
    run._act(cast("Page", FakePage(closed)), step, 1000, record)  # pyright: ignore[reportPrivateUsage]


def test_click_that_closes_its_own_page_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    click(monkeypatch, tmp_path, closed=True)


def test_click_error_on_an_open_page_still_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(PlaywrightError, match="has been closed"):
        click(monkeypatch, tmp_path, closed=False)
