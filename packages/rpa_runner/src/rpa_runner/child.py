"""自動化子程序：開瀏覽器、執行 DSL 步驟、寫出頁面事實。由 run.py 以子程序啟動。

    python -m rpa_runner.child --scenario 快照.yaml --input input.json \
        --out 執行目錄 --deadline 秒數 [--video]

寫出 facts.json、steps.json、screenshot.png；失敗時另寫 diagnostic.json。
``--video`` 時錄影到執行目錄的 .video/（M12）：離開時先關 context，影片才寫完；
由父程序整理成 video.webm（見 video.py）。
Firefox 從預熱設定檔的複本啟動，避免每次初始化全新設定檔而卡住（見 profiles.py）。
場景有 login 時，``--storage-state`` 是角色的登入狀態檔（已在登入檢查階段確認過）。
退出碼：0 成功、1 步驟失敗、3 總期限已到。父程序另外設有硬期限，逾時會終止整個程序群組。
"""

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import Page, Playwright, ViewportSize, sync_playwright

from rpa_core.dsl import Scenario, validate_file
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, DeadlineExceeded, plan_records, run_steps
from rpa_runner.contexts import Engine, open_context
from rpa_runner.files import DIAGNOSTIC, FACTS, SCREENSHOT, STEPS, VIDEO_TMP, write_json
from rpa_runner.i18n import t
from rpa_runner.secrets import mask, read_secrets
from rpa_runner.video import mark_page, video_size

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
    video: Path | None = None,
) -> Page:
    """開瀏覽器與頁面；關閉的動作登記在 stack，離開時依相反順序執行。

    ``video`` 是執行目錄時錄影：記下主要頁面的影片檔名與開頁面的時間。Firefox 的預熱設定檔
    （持久化 context）啟動時就有一個分頁，這個分頁錄到的畫面少了工具列的高度（Windows、Linux
    都是，例如 640×360 的頁面只錄到 640×273，下方是 ffmpeg 補的灰色）；錄影時改用新開的分頁，
    畫面才完整，原本的分頁關掉（2026-10-21 在 CI 用 Playwright 1.64 實測）。
    """
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
        video_dir=video / VIDEO_TMP if video is not None else None,
        video_size=video_size(_viewport(scenario)) if video is not None else None,
    )
    if video is not None and context.pages:
        first = context.pages[0]
        page = context.new_page()
        with contextlib.suppress(Exception):  # 關不掉也不影響，只是多一段沒用到的影片
            first.close()
    else:
        page = context.pages[0] if context.pages else context.new_page()
    if video is not None:
        name: str | None = None
        with contextlib.suppress(Exception):  # 只是讓父程序找得到主要頁面的影片
            name = str(page.video.path()) if page.video is not None else None
        mark_page(video, name, time.time())
    return page


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
        steps = [record.to_json() for record in records]
        for step in steps:
            if isinstance(step["url"], str):
                step["url"] = mask(step["url"], secrets)
        write_json(out / STEPS, steps)

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
                video=out if args.video else None,
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
    parser.add_argument("--video", action="store_true", help="錄影（M12）")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
