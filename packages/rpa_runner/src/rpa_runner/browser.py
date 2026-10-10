"""在瀏覽器中執行 DSL 步驟，留下頁面事實。在子程序裡執行（見 child.py）。

- 每次執行用獨立的瀏覽器與 BrowserContext，結束就關閉。
- 每一步的逾時 = min(步驟 timeout 或 defaults.timeout 或 30 秒, 總期限剩下的時間)。
- 步驟欄位中的 ``{{ }}`` 在執行該步驟前才代入，所以可以用前面步驟抽到的 facts。
- 有副作用的動作（點擊、填寫、按鍵）不會因為逾時自動重試。
"""

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, cast

from playwright.sync_api import Locator as PwLocator
from playwright.sync_api import Page, expect
from pydantic import TypeAdapter

from rpa_core.dsl import (
    ClickStep,
    ExpectStep,
    ExtractField,
    ExtractStep,
    FillStep,
    GotoStep,
    Locator,
    PressStep,
    Scenario,
    ScreenshotStep,
    SelectStep,
    Step,
    WaitForStep,
)
from rpa_runner.templates import Context, render_tree

__all__ = [
    "DEFAULT_STEP_TIMEOUT_MS",
    "Deadline",
    "DeadlineExceeded",
    "StepRecord",
    "plan_records",
    "run_steps",
]

DEFAULT_STEP_TIMEOUT_MS: Final = 30_000
_STEP: Final = TypeAdapter[Step](Step)
_TABLE_JS: Final = """
(table) => {
  const rows = [...table.querySelectorAll('tr')];
  if (!rows.length) return [];
  const headerRow = table.querySelector('thead tr') || rows[0];
  const headers = [...headerRow.querySelectorAll('th,td')].map((cell) => cell.innerText.trim());
  const body = rows.filter((row) => row !== headerRow && row.querySelector('td'));
  return body.map((row) => Object.fromEntries(
    [...row.querySelectorAll('td,th')].map(
      (cell, i) => [headers[i] || `column${i + 1}`, cell.innerText.trim()]
    )
  ));
}
"""


class DeadlineExceeded(Exception):  # noqa: N818 - 與 TimeoutError 區分，名稱照語意
    """總期限已到。"""


@dataclass(frozen=True, slots=True)
class Deadline:
    """以單調時鐘計算的總期限。"""

    expires_at: float

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        return cls(time.monotonic() + seconds)

    def remaining_ms(self) -> int:
        return int((self.expires_at - time.monotonic()) * 1000)

    def budget(self, step_ms: int) -> int:
        """這一步可以用的毫秒數；總期限已到就拋出 DeadlineExceeded。"""
        remaining = self.remaining_ms()
        if remaining <= 0:
            raise DeadlineExceeded
        return max(1, min(step_ms, remaining))


@dataclass(slots=True)
class StepRecord:
    """一個步驟的執行紀錄（寫進 steps.json）。"""

    id: str
    action: str
    name: str | None
    status: Literal["passed", "failed", "skipped"] = "skipped"
    duration_ms: int = 0
    error: str | None = None
    artifacts: list[str] = field(default_factory=list[str])

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "action": self.action,
            "name": self.name,
            "status": self.status,
            "durationMs": self.duration_ms,
            "error": self.error,
            "artifacts": self.artifacts,
        }


# ---------------------------------------------------------------- 定位器


def resolve(scope: Page | PwLocator, locator: Locator) -> PwLocator:
    """DSL 定位器 → Playwright Locator（不含 fallback）。"""
    base: Page | PwLocator = resolve(scope, locator.within) if locator.within else scope
    exact = bool(locator.exact)
    match locator.strategy:
        case "testId":
            result = base.get_by_test_id(cast("str", locator.test_id))
        case "role":
            result = base.get_by_role(
                cast("Literal['button']", locator.role), name=locator.name, exact=exact
            )
        case "label":
            result = base.get_by_label(cast("str", locator.label), exact=exact)
        case "placeholder":
            result = base.get_by_placeholder(cast("str", locator.placeholder), exact=exact)
        case "text":
            result = base.get_by_text(cast("str", locator.text), exact=exact)
        case "altText":
            result = base.get_by_alt_text(cast("str", locator.alt_text), exact=exact)
        case "title":
            result = base.get_by_title(cast("str", locator.title), exact=exact)
        case "css":
            result = base.locator(f"css={locator.css}")
        case _:
            result = base.locator(f"xpath={locator.xpath}")
    if locator.has_text is not None:
        result = result.filter(has_text=locator.has_text)
    if locator.nth is not None:
        result = result.nth(locator.nth)
    return result


def locate(page: Page, locator: Locator, timeout_ms: int) -> PwLocator:
    """有 fallback 時，在逾時內輪流找第一個存在的候選；都找不到就回傳主要定位器。"""
    primary = resolve(page, locator)
    if not locator.fallback:
        return primary
    candidates = [primary, *(resolve(page, item) for item in locator.fallback)]
    ends = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < ends:
        for candidate in candidates:
            if candidate.count() > 0:
                return candidate
        time.sleep(0.1)
    return primary


# ---------------------------------------------------------------- 步驟


def _matcher(text: str, match: str) -> str | re.Pattern[str]:
    match match:
        case "equals":
            return text
        case "regex":
            return re.compile(text)
        case _:
            return re.compile(re.escape(text))


def _url_predicate(text: str, match: str) -> Callable[[str], bool]:
    match match:
        case "equals":
            return lambda url: url == text
        case "regex":
            pattern = re.compile(text)
            return lambda url: pattern.search(url) is not None
        case _:
            return lambda url: text in url


def _read(element: PwLocator, get: str, attribute: str | None, timeout: int) -> object:
    match get:
        case "value":
            return element.input_value(timeout=timeout)
        case "html":
            return element.inner_html(timeout=timeout)
        case "attribute":
            return element.get_attribute(cast("str", attribute), timeout=timeout) or ""
        case "table":
            return element.evaluate(_TABLE_JS, timeout=timeout)  # pyright: ignore[reportUnknownMemberType]
        case _:
            return element.inner_text(timeout=timeout).strip()


def _read_field(element: PwLocator, spec: ExtractField, timeout: int) -> object:
    target = resolve(element, spec.target).first if spec.target else element
    return _read(target, spec.get, spec.attribute, timeout)


def _extract(page: Page, step: ExtractStep, timeout: int) -> object:
    located = locate(page, step.target, timeout)
    located.first.wait_for(state="attached", timeout=timeout)
    elements = located.all() if step.multiple else [located.first]

    def one(element: PwLocator) -> object:
        if step.fields is not None:
            return {name: _read_field(element, spec, timeout) for name, spec in step.fields.items()}
        return _read(element, step.get, step.attribute, timeout)

    values = [one(element) for element in elements]
    return values if step.multiple else values[0]


def _expect(page: Page, step: ExpectStep, timeout: int) -> None:
    if step.target is None:
        if step.url is not None:
            expect(page).to_have_url(_matcher(step.url, step.match), timeout=timeout)
        else:
            expect(page).to_have_title(
                _matcher(cast("str", step.title), step.match), timeout=timeout
            )
        return
    target = locate(page, step.target, timeout)
    assertions = expect(target)
    if step.count is not None:
        assertions.to_have_count(step.count, timeout=timeout)
    elif step.text is not None:
        if step.match == "contains":
            assertions.to_contain_text(step.text, timeout=timeout)
        else:
            assertions.to_have_text(_matcher(step.text, step.match), timeout=timeout)
    elif step.value is not None:
        assertions.to_have_value(_matcher(step.value, step.match), timeout=timeout)
    else:
        match step.state:
            case "hidden":
                assertions.to_be_hidden(timeout=timeout)
            case "enabled":
                assertions.to_be_enabled(timeout=timeout)
            case "disabled":
                assertions.to_be_disabled(timeout=timeout)
            case "checked":
                assertions.to_be_checked(timeout=timeout)
            case "unchecked":
                assertions.to_be_checked(checked=False, timeout=timeout)
            case "editable":
                assertions.to_be_editable(timeout=timeout)
            case _:
                assertions.to_be_visible(timeout=timeout)


def _url(base_url: str | None, url: str) -> str:
    if url.startswith("/") and base_url:
        return base_url.rstrip("/") + url
    return url


@dataclass(slots=True)
class _Run:
    page: Page
    scenario: Scenario
    base_url: str | None
    artifacts: Path
    facts: dict[str, object]

    def execute(self, step: Step, timeout: int, record: StepRecord) -> None:
        page = self.page
        match step:
            case GotoStep():
                page.goto(
                    _url(self.base_url, step.url), wait_until=step.wait_until, timeout=timeout
                )
            case ClickStep():
                locate(page, step.target, timeout).click(
                    button=step.button,
                    click_count=step.click_count,
                    modifiers=step.modifiers,
                    timeout=timeout,
                )
            case FillStep():
                locate(page, step.target, timeout).fill(step.value, timeout=timeout)
            case SelectStep():
                locate(page, step.target, timeout).select_option(step.option, timeout=timeout)
            case PressStep():
                if step.target is None:
                    page.keyboard.press(step.key)
                else:
                    locate(page, step.target, timeout).press(step.key, timeout=timeout)
            case WaitForStep():
                if step.target is not None:
                    locate(page, step.target, timeout).wait_for(state=step.state, timeout=timeout)
                elif step.url is not None:
                    page.wait_for_url(_url_predicate(step.url, step.match), timeout=timeout)
                else:
                    page.wait_for_load_state(step.load_state, timeout=timeout)
            case ExpectStep():
                _expect(page, step, timeout)
            case ExtractStep():
                self.facts[step.as_] = _extract(page, step, timeout)
            case ScreenshotStep():
                name = f"{step.file or step.id}.png"
                path = self.artifacts / name
                if step.target is not None:
                    locate(page, step.target, timeout).screenshot(path=path, timeout=timeout)
                else:
                    page.screenshot(path=path, full_page=step.full_page, timeout=timeout)
                record.artifacts.append(name)


def plan_records(scenario: Scenario) -> list[StepRecord]:
    """每個步驟一筆紀錄，初始狀態是略過。"""
    return [StepRecord(step.id, step.action, step.name) for step in scenario.steps or []]


def run_steps(
    page: Page,
    scenario: Scenario,
    *,
    records: list[StepRecord],
    context: Mapping[str, object],
    base_url: str | None,
    artifacts: Path,
    deadline: Deadline,
    on_progress: Callable[[], None] = lambda: None,
) -> dict[str, object]:
    """依序執行步驟並更新 records，回傳頁面事實；某一步失敗就拋出，後面的步驟維持略過。"""
    facts: dict[str, object] = {}
    run = _Run(page, scenario, base_url, artifacts, facts)
    steps = scenario.steps or []
    default_ms = scenario.defaults.timeout or DEFAULT_STEP_TIMEOUT_MS
    for step, record in zip(steps, records, strict=True):
        started = time.monotonic()
        try:
            timeout = deadline.budget(step.timeout or default_ms)
            values: Context = {**context, "facts": facts}
            raw = step.model_dump(mode="json", by_alias=True, exclude_unset=True)
            rendered = _STEP.validate_python(render_tree(raw, values, skip=frozenset({"name"})))
            run.execute(rendered, timeout, record)
            record.status = "passed"
        except BaseException as error:
            record.status = "failed"
            record.error = f"{type(error).__name__}: {error}".splitlines()[0]
            raise
        finally:
            record.duration_ms = int((time.monotonic() - started) * 1000)
            on_progress()
    return facts
