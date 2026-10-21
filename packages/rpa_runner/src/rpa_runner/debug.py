"""調試工作階段的子程序：握有一個瀏覽器，一次執行一個步驟（M4）。

由管理 Portal 啟動，存在到使用者關閉或閒置太久為止::

    python -m rpa_runner.debug --scenario 場景.yaml --input input.json --out 目錄 \
        [--engine 瀏覽器] [--headed] [--base-url 網址] [--storage-state 登入狀態檔]

標準輸入一行一個 JSON 命令，標準輸出一行一個 JSON 回覆（帶著命令的 id）：

- ``{"cmd": "step", "index": 2}``：執行第 3 步（``{{ }}`` 以入參、Secrets 與目前的 facts 代入），
  回覆步驟紀錄、目前網址、標題、截圖檔名與 facts。
- ``{"cmd": "locate", "locator": {…}}``：測試定位器：找到幾個、前幾個的文字，截圖時框出來。
- ``{"cmd": "screenshot"}``：目前頁面的截圖。

新分頁（M7b）：步驟開出的新分頁在整個工作階段都在（:class:`rpa_runner.browser.Tabs`）；
「目前頁面」是最後一步所在（或剛開出）的分頁，截圖、網址與定位器測試都在這個分頁。
- ``{"cmd": "load", "scenario": 路徑, "input": 路徑}``：換成新的場景版本或入參
  （瀏覽器與 facts 保留）。
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
from collections.abc import Callable
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from pydantic import ValidationError

from rpa_core.dsl import Locator, Scenario, validate_file
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, Tabs, resolve, run_step
from rpa_runner.contexts import Engine, open_context
from rpa_runner.i18n import t
from rpa_runner.secrets import mask, read_secrets

__all__ = ["COMMAND_SECONDS", "KEEP_SHOTS", "main"]

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
_DESCRIBE: Final = """
(elements) => elements.slice(0, 5).map((element) => ({
  tag: element.tagName.toLowerCase(),
  text: (element.innerText || element.value || element.getAttribute('aria-label') || '')
    .trim().replace(/\\s+/g, ' ').slice(0, 80),
}))
"""


class _Session:
    def __init__(self, args: argparse.Namespace, playwright: Playwright) -> None:
        self.args = args
        self.playwright = playwright
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = cast("Engine", args.engine)
        self.scenario, self.inputs = self._load(Path(args.scenario), Path(args.input))
        self.secrets = read_secrets(self.scenario)
        self.facts: dict[str, object] = {}
        self.shots = 0
        self.stack = contextlib.ExitStack()
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.tabs: Tabs | None = None
        """整個工作階段的分頁（M7b）：步驟開出的新分頁在步驟之間一直都在。"""

    @staticmethod
    def _load(scenario_path: Path, input_path: Path) -> tuple[Scenario, dict[str, object]]:
        validated = validate_file(scenario_path)
        if validated.scenario is None:
            raise ValueError(t("child.invalid_scenario"))
        inputs = cast("dict[str, object]", json.loads(input_path.read_text(encoding="utf-8")))
        return validated.scenario, inputs

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

    def load(self, scenario: str, input_file: str) -> dict[str, object]:
        self.scenario, self.inputs = self._load(Path(scenario), Path(input_file))
        self.secrets = read_secrets(self.scenario)
        return {"steps": len(self.scenario.steps or [])}

    def handle(self, command: dict[str, object]) -> dict[str, object] | None:
        name = command.get("cmd")
        handlers: dict[str, Callable[[], dict[str, object]]] = {
            "step": lambda: self.step(int(cast("int", command.get("index")))),
            "locate": lambda: self.locate(command.get("locator")),
            "screenshot": lambda: self.page_state(self.active_page()),
            "load": lambda: self.load(str(command["scenario"]), str(command["input"])),
            "reset": lambda: self.page_state(self.open(), shot=False),
        }
        if name == "close":
            return None
        handler = handlers.get(str(name))
        if handler is None:
            return {"ok": False, "error": f"unknown command {name!r}"}
        return {"ok": True, **handler()}


def _reply(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve(args: argparse.Namespace) -> int:
    with sync_playwright() as playwright:
        try:
            session = _Session(args, playwright)
            session.open()
        except Exception as error:
            _reply({"event": "error", "error": f"{type(error).__name__}: {error}".splitlines()[0]})
            return 1
        _reply({"event": "ready", "steps": len(session.scenario.steps or [])})
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
                    message = mask(
                        f"{type(error).__name__}: {error}".splitlines()[0], session.secrets
                    )
                    reply = {"ok": False, "error": message}
                if reply is None:
                    break
                _reply({"id": command.get("id"), **reply})
        finally:
            session.close_browser()
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
    return serve(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
