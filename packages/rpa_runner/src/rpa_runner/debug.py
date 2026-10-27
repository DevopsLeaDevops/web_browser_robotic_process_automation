"""調試工作階段的子程序：握有一個瀏覽器，一次執行一個步驟（M4）。

由管理 Portal 啟動，存在到使用者關閉或閒置太久為止::

    python -m rpa_runner.debug --scenario 場景.yaml --input input.json --out 目錄 \
        [--engine 瀏覽器] [--headed] [--base-url 網址] [--storage-state 登入狀態檔] \
        [--file 入參 檔案 …]

``--file``（M7c，可以重複）：管理 Portal 以原始檔名準備好的檔案入參（上傳檔、場景附件）；
``path`` 值的檔案在這台找，只能在 ``RPA_INPUT_FOLDERS`` 裡。

標準輸入一行一個 JSON 命令，標準輸出一行一個 JSON 回覆（帶著命令的 id）：

- ``{"cmd": "step", "index": 2}``：執行第 3 步（``{{ }}`` 以入參、Secrets 與目前的 facts 代入），
  回覆步驟紀錄、目前網址、標題、截圖檔名與 facts。
- ``{"cmd": "locate", "locator": {…}}``：測試定位器：找到幾個、前幾個的文字，截圖時框出來。
- ``{"cmd": "screenshot"}``：目前頁面的截圖。
- ``{"cmd": "snapshot", "within": {…}}``：目前頁面的結構（M14，給 Agent 寫定位器）：無障礙樹
  （Playwright 的 ARIA 快照）、表單欄位、iframe 與分頁；``within`` 只看頁面的一部分。
  密碼欄位與 Secrets 的值一律遮罩；太大時截斷並標 ``truncated``。

新分頁（M7b）：步驟開出的新分頁在整個工作階段都在（:class:`rpa_runner.browser.Tabs`）；
「目前頁面」是最後一步所在（或剛開出）的分頁，截圖、網址與定位器測試都在這個分頁。
- ``{"cmd": "load", "revision": 3, "scenarioText": 場景 YAML, "inputs": {…}}``：
  換成新的場景版本或入參（瀏覽器與 facts 保留）。直接帶內容：這個子程序可能在
  錄製端（另一台電腦），讀不到伺服器的檔案（v0.6.3）。舊的伺服器送
  ``"scenario": 路徑, "input": 路徑``，仍然接受。場景校驗失敗時回覆 ``issues``
  （行號、步驟、欄位與說明）。
- ``{"cmd": "reset"}``：關掉目前的頁面，從頭開始（facts 清空，重新載入登入狀態）。
- ``{"cmd": "close"}``：結束。

哪些步驟執行過、能不能重跑由管理 Portal 決定；這裡只照命令執行，不會自己重試任何步驟。
截圖寫在 ``--out``（shot-0001.png…），只保留最近的幾十張。
"""

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from pydantic import ValidationError

from rpa_core.dsl import Locator, Scenario, ValidationResult, validate_file, validate_text
from rpa_core.dsl.issues import Issue, format_issue
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, Tabs, resolve, run_step
from rpa_runner.contexts import Engine, open_context
from rpa_runner.contract import check_inputs
from rpa_runner.i18n import t
from rpa_runner.inputfiles import given_files, remove_staging, session_files
from rpa_runner.secrets import MASK, mask, read_secrets

__all__ = [
    "COMMAND_SECONDS",
    "KEEP_SHOTS",
    "SNAPSHOT_ARIA_CHARS",
    "SNAPSHOT_FIELDS",
    "ScenarioInvalidError",
    "main",
]

COMMAND_SECONDS: Final = 600.0
"""一個命令最多執行這麼久（步驟本身另有逾時）。"""
KEEP_SHOTS: Final = 40
_OUTLINE: Final = """
(elements) => {
  for (const element of elements) {
    element.dataset.rpaOutline = element.style.outline || '';
    element.style.outline = '3px solid #e5484d';
    element.style.outlineOffset = '2px';
  }
}
"""
_RESTORE: Final = """
(elements) => {
  for (const element of elements) {
    element.style.outline = element.dataset.rpaOutline || '';
    element.style.outlineOffset = '';
    delete element.dataset.rpaOutline;
  }
}
"""
SNAPSHOT_ARIA_CHARS: Final = 60_000
"""頁面結構的無障礙樹最多這麼多字；超過就截斷（Agent 可以用 within 只看一部分）。"""
SNAPSHOT_FIELDS: Final = 200
"""頁面結構最多列出這麼多個表單欄位。"""
_FIELD_ROLES: Final = {
    "checkbox": "checkbox",
    "radio": "radio",
    "number": "spinbutton",
    "range": "slider",
    "search": "searchbox",
    "button": "button",
    "submit": "button",
    "reset": "button",
    "image": "button",
}
_FIELDS: Final = """
([root, limit]) => {
  const scope = root || document;
  const selector = 'input, select, textarea, [contenteditable="true"], [role="textbox"], '
    + '[role="combobox"], [role="checkbox"], [role="radio"], [role="switch"], [role="spinbutton"]';
  const text = value => (value || '').trim().replace(/\\s+/g, ' ').slice(0, 120);
  const labelOf = element => {
    const labelled = element.getAttribute('aria-labelledby');
    if (labelled) {
      const parts = labelled.split(/\\s+/).map(id => document.getElementById(id))
        .filter(Boolean).map(item => item.innerText || item.textContent);
      if (parts.length) return text(parts.join(' '));
    }
    if (element.getAttribute('aria-label')) return text(element.getAttribute('aria-label'));
    const labels = element.labels ? [...element.labels] : [];
    if (labels.length) {
      const label = labels[0].cloneNode(true);
      label.querySelectorAll('input, select, textarea').forEach(item => item.remove());
      return text(label.innerText || label.textContent);
    }
    return text(element.getAttribute('placeholder') || element.getAttribute('title'));
  };
  const fields = [];
  for (const element of scope.querySelectorAll(selector)) {
    const tag = element.tagName.toLowerCase();
    const type = tag === 'input' ? (element.getAttribute('type') || 'text').toLowerCase() : tag;
    if (type === 'hidden') continue;
    const style = getComputedStyle(element);
    const visible = element.getClientRects().length > 0 && style.visibility !== 'hidden';
    const field = {
      tag, type, role: element.getAttribute('role'), label: labelOf(element),
      name: element.getAttribute('name'), id: element.id || null,
      testId: element.getAttribute('data-testid'),
      placeholder: element.getAttribute('placeholder'),
      required: element.required === true || element.getAttribute('aria-required') === 'true',
      disabled: element.disabled === true || element.getAttribute('aria-disabled') === 'true',
      visible,
    };
    if (type === 'checkbox' || type === 'radio') field.checked = element.checked === true;
    else if (tag === 'select') {
      field.multiple = element.multiple;
      const label = option => option.label || option.text;
      field.options = [...element.options].slice(0, 30).map(option => text(label(option)));
      field.value = text([...element.selectedOptions].map(label).join(', '));
    } else if ('value' in element) field.value = String(element.value ?? '').slice(0, 200);
    else field.value = text(element.innerText);
    fields.push(field);
    if (fields.length > limit) break;
  }
  return fields;
}
"""
_DESCRIBE: Final = """
(elements) => elements.slice(0, 5).map((element) => ({
  tag: element.tagName.toLowerCase(),
  text: (element.innerText || element.value || element.getAttribute('aria-label') || '')
    .trim().replace(/\\s+/g, ' ').slice(0, 80),
}))
"""


class ScenarioInvalidError(ValueError):
    """場景校驗失敗。訊息寫出第一個問題（行號與說明），``issues`` 是全部問題，欄位和管理 Portal
    存版本時回報的相同（line、column、step、stepId、field、path、code、message、text）。"""

    def __init__(self, result: ValidationResult) -> None:
        self.issues: list[dict[str, object]] = [_issue_json(issue) for issue in result.issues]
        if not result.issues:
            super().__init__(t("child.invalid_scenario"))
            return
        first = result.issues[0]
        detail = format_issue(first)
        if first.position is not None:
            detail = t("debug.issue_at", line=first.position.line, issue=detail)
        if len(result.issues) > 1:
            detail = t("debug.more_issues", issue=detail, count=len(result.issues) - 1)
        super().__init__(t("debug.invalid_scenario", detail=detail))


def _issue_json(issue: Issue) -> dict[str, object]:
    position = issue.position
    return {
        "line": position.line if position else None,
        "column": position.column if position else None,
        "step": issue.step,
        "stepId": issue.step_id,
        "field": issue.field or None,
        "path": list(issue.path),
        "code": issue.code,
        "message": issue.message,
        "text": format_issue(issue),
    }


def _valid(result: ValidationResult) -> Scenario:
    if result.scenario is None:
        raise ScenarioInvalidError(result)
    return result.scenario


def _read_inputs(path: Path) -> dict[str, object]:
    return _inputs_object(json.loads(path.read_text(encoding="utf-8")))


def _inputs_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(t("debug.inputs_not_object"))
    return cast("dict[str, object]", value)


def _resolved(
    scenario: Scenario, inputs: Mapping[str, object], *, preserved: frozenset[str] = frozenset()
) -> dict[str, object]:
    """入參依場景校驗（動態值在這台求值）；``preserved`` 是已求過值、允許暫時不符合新規則的入參。"""
    resolved, problems = check_inputs(scenario, inputs)
    problems = [problem for problem in problems if problem.name not in preserved]
    if problems:
        raise ValueError("; ".join(problem.message for problem in problems))
    return resolved


def _error_text(error: Exception) -> str:
    """回覆給管理 Portal 的錯誤：場景校驗失敗本身就是完整的說明，其他的加上例外的種類。"""
    if isinstance(error, ScenarioInvalidError):
        return str(error).splitlines()[0]
    return f"{type(error).__name__}: {error}".splitlines()[0]


class _Session:
    def __init__(self, args: argparse.Namespace, playwright: Playwright) -> None:
        self.args = args
        self.playwright = playwright
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = cast("Engine", args.engine)
        self.scenario = _valid(validate_file(Path(args.scenario)))
        self.inputs = _resolved(self.scenario, _read_inputs(Path(args.input)))
        # 檔案入參（M7c）：path 值暫存在系統的暫存資料夾（不在 --out 裡，錄製端不會同步回伺服器）
        self.staging = Path(tempfile.mkdtemp(prefix="rpa-debug-files-"))
        prepared = session_files(
            self.scenario,
            self.inputs,
            given_files(cast("list[list[str]] | None", getattr(args, "file", None))),
            Path(args.scenario).parent,
            self.staging,
        )
        if prepared.problems:
            remove_staging(self.staging)
            raise ValueError("; ".join(problem.message for problem in prepared.problems))
        self.inputs.update(prepared.meta)
        self.files = prepared.paths
        self.secrets = read_secrets(self.scenario)
        self.facts: dict[str, object] = {}
        self.shots = 0
        self.stack = contextlib.ExitStack()
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.tabs: Tabs | None = None
        """整個工作階段的分頁（M7b）：步驟開出的新分頁在步驟之間一直都在。"""

    # ------------------------------------------------------------ 瀏覽器

    def open(self) -> Page:
        self.close_browser()
        self.stack = contextlib.ExitStack()
        viewport = self.scenario.browser.viewport
        self.context = open_context(
            self.playwright,
            self.engine,
            headed=bool(self.args.headed),
            timeout_ms=120_000,
            budget_seconds=120,
            stack=self.stack,
            viewport={"width": viewport.width, "height": viewport.height} if viewport else None,
            locale=self.scenario.browser.locale,
            storage_state=Path(self.args.storage_state) if self.args.storage_state else None,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.tabs = Tabs(self.page)
        self.facts = {}
        return self.page

    def close_browser(self) -> None:
        with contextlib.suppress(Exception):
            self.stack.close()
        self.context = None
        self.page = None
        self.tabs = None

    def current_page(self) -> Page:
        """目前的頁面；使用者把視窗關掉了就開一個新的。"""
        if self.page is None or self.page.is_closed():
            context = self.context
            if context is None:
                return self.open()
            try:
                self.page = context.pages[0] if context.pages else context.new_page()
            except Exception:
                return self.open()
            self.tabs = Tabs(self.page)
        return self.page

    def active_page(self) -> Page:
        """目前在用的分頁：最後一步所在（或剛開出）的分頁（M7b）；截圖與定位器測試都在這裡。"""
        page = self.current_page()
        return self.tabs.active if self.tabs is not None else page

    def screenshot(self, page: Page) -> str | None:
        self.shots += 1
        name = f"shot-{self.shots:04d}.png"
        try:
            page.screenshot(path=self.out / name, timeout=10_000)
        except Exception:
            return None
        old = self.out / f"shot-{self.shots - KEEP_SHOTS:04d}.png"
        old.unlink(missing_ok=True)
        return name

    def page_state(self, page: Page, *, shot: bool = True) -> dict[str, object]:
        try:
            title = page.title()
        except Exception:
            title = ""
        return {
            "url": page.url,
            "title": title,
            "screenshot": self.screenshot(page) if shot else None,
            "facts": self.facts,
        }

    # ------------------------------------------------------------ 命令

    def step(self, index: int) -> dict[str, object]:
        steps = self.scenario.steps or []
        if not 0 <= index < len(steps):
            raise IndexError(index)
        page = self.current_page()
        record = run_step(
            page,
            self.scenario,
            steps[index],
            facts=self.facts,
            context={"inputs": self.inputs, "secrets": self.secrets, "env": dict(os.environ)},
            base_url=self.args.base_url or self.scenario.browser.base_url,
            artifacts=self.out,
            deadline=Deadline.after(COMMAND_SECONDS),
            tabs=self.tabs,
            files=self.files,
        )
        if record.error:
            record.error = mask(record.error, self.secrets)
        return {"index": index, "record": record.to_json(), **self.page_state(self.active_page())}

    def locate(self, data: object) -> dict[str, object]:
        try:
            locator = Locator.model_validate(data)
        except ValidationError as error:
            return {"ok": False, "error": error.errors()[0]["msg"]}
        page = self.active_page()
        found = resolve(page, locator)
        count = found.count()
        matches: list[dict[str, str]] = []
        if count:
            with contextlib.suppress(Exception):
                found.first.scroll_into_view_if_needed(timeout=2_000)
            matches = cast("list[dict[str, str]]", found.evaluate_all(_DESCRIBE))
            found.evaluate_all(_OUTLINE)
        try:
            state = self.page_state(page)
        finally:
            if count:
                with contextlib.suppress(Exception):
                    found.evaluate_all(_RESTORE)
        return {"count": count, "matches": matches, **state}

    def snapshot(self, data: object) -> dict[str, object]:
        """目前頁面的結構（M14）：無障礙樹、表單欄位、iframe 與分頁，給 Agent 寫定位器。

        ``data`` 是 DSL 定位器時只看那個元素裡面（第一個符合的）；可以帶 ``frame`` 進入 iframe。
        密碼欄位的值換成 ***，Secrets 的值在無障礙樹與欄位裡都遮罩。
        """
        page = self.active_page()
        root = None
        if data is not None:
            try:
                within = Locator.model_validate(data)
            except ValidationError as error:
                return {"ok": False, "error": error.errors()[0]["msg"]}
            found = resolve(page, within)
            if not found.count():
                return {"ok": False, "error": t("debug.snapshot_not_found")}
            root = found.first
        target = root if root is not None else page.locator("body")
        aria = target.aria_snapshot(timeout=10_000)
        # 在元素所在的 iframe 裡求值（跨網域的 iframe 不能從頁面本身讀）
        found_fields = (
            root.evaluate(f"(element, limit) => ({_FIELDS})([element, limit])", SNAPSHOT_FIELDS)
            if root is not None
            else page.evaluate(_FIELDS, [None, SNAPSHOT_FIELDS])
        )
        raw = cast("list[dict[str, object]]", found_fields)
        hidden = dict(self.secrets)
        fields: list[dict[str, object]] = []
        for item in raw[:SNAPSHOT_FIELDS]:
            field = {key: value for key, value in item.items() if value is not None}
            value = field.get("value")
            if item.get("type") == "password" and isinstance(value, str):
                if value:
                    hidden[f"password-{len(hidden)}"] = value
                field["value"] = MASK if value else ""
            elif isinstance(value, str):
                field["value"] = mask(value, self.secrets)
            kind = str(item.get("type"))
            field["role"] = item.get("role") or _FIELD_ROLES.get(
                kind, "combobox" if kind == "select" else "textbox"
            )
            fields.append(field)
        aria = mask(aria, hidden)
        truncated = len(raw) > SNAPSHOT_FIELDS or len(aria) > SNAPSHOT_ARIA_CHARS
        try:
            title = page.title()
        except Exception:
            title = ""
        return {
            "url": page.url,
            "title": title,
            "tabs": self._tabs(page),
            "frames": [
                {
                    "name": frame.name or None,
                    "url": frame.url,
                    "parent": _frame_index(page, frame.parent_frame),
                }
                for frame in page.frames[1:]
            ],
            "fields": fields,
            "aria": aria[:SNAPSHOT_ARIA_CHARS],
            "truncated": truncated,
            "facts": self.facts,
        }

    def _tabs(self, active: Page) -> list[dict[str, object]]:
        """工作階段的分頁：一開始的分頁（page 是 None）與步驟用 popup 開出、取了名字的分頁。"""
        tabs = self.tabs
        if tabs is None:
            return []
        pages: list[tuple[str | None, Page]] = [(None, tabs.main)]
        pages += [(name, page) for name, page in tabs.named.items() if not page.is_closed()]
        listed: list[dict[str, object]] = []
        for name, page in pages:
            try:
                title = page.title()
            except Exception:
                title = ""
            listed.append({"page": name, "url": page.url, "title": title, "active": page == active})
        return listed

    def load(self, command: Mapping[str, object]) -> dict[str, object]:
        """換成新的場景版本或入參；瀏覽器、分頁與 facts 保留。

        管理 Portal 直接送場景內容（``scenarioText``）與入參（``inputs``）：這個子程序可能在另一台
        電腦（錄製端），讀不到伺服器的檔案。``scenario``／``input`` 路徑是 v0.6.2 以前的伺服器送的，
        只在和伺服器同一台時讀得到，保留相容。
        """
        text = command.get("scenarioText")
        if isinstance(text, str):
            scenario = _valid(validate_text(text))
            inputs = _inputs_object(command.get("inputs", {}))
        else:
            scenario = _valid(validate_file(Path(str(command["scenario"]))))
            inputs = _read_inputs(Path(str(command["input"])))
        # 保留已求值的舊值（允許與新約束暫時不一致）；新增預設值仍須通過運行態校驗。
        self.inputs = _resolved(scenario, inputs, preserved=frozenset(self.inputs))
        self.scenario = scenario
        self.secrets = read_secrets(self.scenario)
        return {"steps": len(self.scenario.steps or []), "inputs": self.inputs}

    def handle(self, command: dict[str, object]) -> dict[str, object] | None:
        name = command.get("cmd")
        handlers: dict[str, Callable[[], dict[str, object]]] = {
            "step": lambda: self.step(int(cast("int", command.get("index")))),
            "locate": lambda: self.locate(command.get("locator")),
            "screenshot": lambda: self.page_state(self.active_page()),
            "snapshot": lambda: self.snapshot(command.get("within")),
            "load": lambda: self.load(command),
            "reset": lambda: self.page_state(self.open(), shot=False),
        }
        if name == "close":
            return None
        handler = handlers.get(str(name))
        if handler is None:
            return {"ok": False, "error": f"unknown command {name!r}"}
        return {"ok": True, **handler()}


def _frame_index(page: Page, frame: object) -> int | None:
    """iframe 的上一層在 ``page.frames[1:]`` 裡的位置；上一層是頁面本身時是 None。"""
    frames = page.frames
    for index, item in enumerate(frames[1:]):
        if item == frame:
            return index
    return None


def _reply(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve(args: argparse.Namespace) -> int:
    with sync_playwright() as playwright:
        try:
            session = _Session(args, playwright)
            session.open()
        except Exception as error:
            _reply({"event": "error", "error": _error_text(error)})
            return 1
        _reply(
            {"event": "ready", "steps": len(session.scenario.steps or []), "inputs": session.inputs}
        )
        try:
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    command = cast("dict[str, object]", json.loads(line))
                except ValueError:
                    _reply({"ok": False, "error": "invalid JSON"})
                    continue
                try:
                    reply = session.handle(command)
                except Exception as error:
                    failure: dict[str, object] = {
                        "ok": False,
                        "error": mask(_error_text(error), session.secrets),
                    }
                    if isinstance(error, ScenarioInvalidError):
                        failure["issues"] = error.issues
                    reply = failure
                if reply is None:
                    break
                _reply({"id": command.get("id"), **reply})
        finally:
            session.close_browser()
            remove_staging(session.staging)
    return 0


def main(argv: list[str] | None = None) -> int:
    set_locale(parse_locale(os.environ.get(ENV_VAR, "")) or DEFAULT_LOCALE)
    parser = argparse.ArgumentParser(prog="python -m rpa_runner.debug")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--engine", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--base-url")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--storage-state")
    parser.add_argument(
        "--file",
        nargs=2,
        action="append",
        metavar=("INPUT", "PATH"),
        help="準備好的檔案入參（M7c）",
    )
    return serve(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
