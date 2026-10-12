"""自動化子程序：開瀏覽器、執行 DSL 步驟、寫出頁面事實。由 run.py 以子程序啟動。

    python -m rpa_runner.child --scenario 快照.yaml --input input.json \
        --out 執行目錄 --deadline 秒數

寫出 facts.json、steps.json、screenshot.png；失敗時另寫 diagnostic.json。
Firefox 從預熱設定檔的複本啟動，避免每次初始化全新設定檔而卡住（見 profiles.py）。
場景有 login 時，``--storage-state`` 是角色的登入狀態檔（已在登入檢查階段確認過）。
退出碼：0 成功、1 步驟失敗、3 總期限已到。父程序另外設有硬期限，逾時會終止整個程序群組。
"""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import Page, Playwright, ViewportSize, sync_playwright

from rpa_core.dsl import Scenario, validate_file
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, DeadlineExceeded, plan_records, run_steps
from rpa_runner.contexts import Engine, open_context
from rpa_runner.files import DIAGNOSTIC, FACTS, SCREENSHOT, STEPS, write_json
from rpa_runner.i18n import t
from rpa_runner.secrets import mask, read_secrets

__all__ = ["EXIT_DEADLINE", "EXIT_FAILED", "main"]

EXIT_FAILED: Final = 1
EXIT_DEADLINE: Final = 3


def _viewport(scenario: Scenario) -> ViewportSize | None:
    viewport = scenario.browser.viewport
    return {"width": viewport.width, "height": viewport.height} if viewport else None


def _open_page(
    playwright: Playwright,
    engine: Engine,
    scenario: Scenario,
    *,
    headed: bool,
    deadline: Deadline,
    stack: contextlib.ExitStack,
    storage_state: Path | None = None,
) -> Page:
    """開瀏覽器與頁面；關閉的動作登記在 stack，離開時依相反順序執行。"""
    context = open_context(
        playwright,
        engine,
        headed=headed,
        timeout_ms=deadline.remaining_ms(),
        budget_seconds=deadline.remaining_ms() / 1000,
        stack=stack,
        viewport=_viewport(scenario),
        locale=scenario.browser.locale,
        storage_state=storage_state,
    )
    return context.pages[0] if context.pages else context.new_page()


def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    result = validate_file(Path(args.scenario))
    if result.scenario is None:  # pragma: no cover - 父程序已校驗過
        sys.stderr.write(t("child.invalid_scenario") + "\n")
        return EXIT_FAILED
    scenario = result.scenario
    inputs = cast("dict[str, object]", json.loads(Path(args.input).read_text(encoding="utf-8")))
    secrets = read_secrets(scenario)
    context: dict[str, object] = {"inputs": inputs, "secrets": secrets, "env": dict(os.environ)}
    deadline = Deadline.after(float(args.deadline))
    engine = cast("Engine", args.engine or scenario.browser.engine)
    base_url = args.base_url or scenario.browser.base_url
    records = plan_records(scenario)

    def save_steps() -> None:
        write_json(out / STEPS, [record.to_json() for record in records])

    save_steps()
    page: Page | None = None
    with sync_playwright() as playwright, contextlib.ExitStack() as stack:
        try:
            page = _open_page(
                playwright,
                engine,
                scenario,
                headed=args.headed,
                deadline=deadline,
                stack=stack,
                storage_state=Path(args.storage_state) if args.storage_state else None,
            )
            facts = run_steps(
                page,
                scenario,
                records=records,
                context=context,
                base_url=base_url,
                artifacts=out,
                deadline=deadline,
                on_progress=save_steps,
            )
            write_json(out / FACTS, facts)
            page.screenshot(path=out / SCREENSHOT, full_page=True, timeout=deadline.budget(10_000))
            sys.stdout.write(t("child.done") + "\n")
            return 0
        except BaseException as error:
            timed_out = isinstance(error, DeadlineExceeded) or deadline.remaining_ms() <= 0
            write_json(
                out / DIAGNOSTIC,
                {
                    "errorType": type(error).__name__,
                    "error": mask(str(error), secrets),
                    "url": page.url if page is not None else None,
                    "timedOut": timed_out,
                    "remainingMs": max(0, deadline.remaining_ms()),
                },
            )
            if page is not None and deadline.remaining_ms() > 0:
                with contextlib.suppress(Exception):  # 失敗截圖盡力而為
                    page.screenshot(path=out / SCREENSHOT, timeout=deadline.budget(5_000))
            sys.stderr.write(mask(f"{type(error).__name__}: {error}", secrets) + "\n")
            return EXIT_DEADLINE if timed_out else EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    # 父程序用 RPA_LANG 傳入目前的語言（Portal 是伺服器設定，命令列是 --lang），日誌跟著它
    set_locale(parse_locale(os.environ.get(ENV_VAR, "")) or DEFAULT_LOCALE)
    parser = argparse.ArgumentParser(prog="python -m rpa_runner.child")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--deadline", required=True, help="總期限剩下的秒數")
    parser.add_argument("--engine", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--base-url")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--storage-state", help="要載入的登入狀態檔（場景有 login 時）")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
