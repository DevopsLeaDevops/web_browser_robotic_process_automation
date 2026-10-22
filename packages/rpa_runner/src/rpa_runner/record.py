"""接著既有場景錄製（M4）：先在瀏覽器執行既有的步驟，再從那個畫面開始錄製。

由管理 Portal 啟動::

    python -m rpa_runner.record --scenario 場景.yaml --input input.json --output 錄製稿.py \
        --out 目錄 [--engine 瀏覽器] [--base-url 網址] [--storage-state 登入狀態檔]

- 瀏覽器視窗與 Playwright Inspector 開在這台電腦上（有頭模式）。
- 先依序執行既有的步驟（``{{ }}`` 以入參的預設值與 Secrets 代入）；任何一步失敗就結束，不錄製。
- 之後開始錄製：使用者的操作由 Playwright 的錄製器寫進 ``--output``，寫法和 ``playwright codegen``
  相同。既有的步驟不會出現在錄製稿（也不會出現在 Inspector）裡；轉換後由管理 Portal 接在既有
  場景的最後。
- 使用者關掉瀏覽器視窗就結束。

Playwright 沒有公開「在已經開好的瀏覽器上開始錄製」的 API，這裡用 codegen 自己用的通訊命令
``enableRecorder``（1.56～1.63 相同）；Playwright 改版時由測試發現。

標準輸出一行一個 JSON 事件：``replaying``、``recording``、``error``（含 step、message）。
結束碼：0 正常結束、3 既有步驟執行失敗、1 其他錯誤。
"""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import BrowserContext, sync_playwright

from rpa_core.dsl import Scenario, validate_file
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, plan_records, run_steps
from rpa_runner.contexts import Engine, open_context
from rpa_runner.contract import check_inputs
from rpa_runner.i18n import t
from rpa_runner.secrets import mask, read_secrets

__all__ = ["EXIT_REPLAY_FAILED", "REPLAY_SECONDS", "enable_recorder", "main"]

EXIT_REPLAY_FAILED: Final = 3
REPLAY_SECONDS: Final = 300.0
"""執行既有步驟最多這麼久（場景有 deadline 時用它）。"""


def _emit(event: str, **details: object) -> None:
    sys.stdout.write(json.dumps({"event": event, **details}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def enable_recorder(context: BrowserContext, output: Path) -> None:
    """在已經開好的 context 上開始錄製，錄製稿（Python）寫到 ``output``。"""
    impl = context._impl_obj  # pyright: ignore[reportPrivateUsage]
    params = {
        "language": "python",
        "mode": "recording",
        "outputFile": str(output.absolute()),
        "handleSIGINT": False,
    }
    context._sync(  # pyright: ignore[reportPrivateUsage]
        # 內部 API：Playwright 1.64 起 send 的 params 型別是 Dict[Unknown, Unknown]
        impl._channel.send(  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
            "enableRecorder", None, params
        )
    )


def _wait_closed(context: BrowserContext) -> None:
    """等使用者關掉所有分頁（瀏覽器視窗）。"""
    while True:
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            return
        try:
            pages[0].wait_for_event("close", timeout=0)  # pyright: ignore[reportUnknownMemberType]
        except Exception:  # 瀏覽器被關掉（或當掉）：一樣當作錄製結束
            return


def _load(args: argparse.Namespace) -> tuple[Scenario, dict[str, object]]:
    validated = validate_file(Path(args.scenario))
    if validated.scenario is None:
        raise ValueError(t("child.invalid_scenario"))
    inputs = cast("dict[str, object]", json.loads(Path(args.input).read_text(encoding="utf-8")))
    resolved, problems = check_inputs(validated.scenario, inputs)
    if problems:
        raise ValueError("; ".join(problem.message for problem in problems))
    return validated.scenario, resolved


def record(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scenario, inputs = _load(args)
    (out / "input.json").write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
    secrets = read_secrets(scenario)
    with sync_playwright() as playwright, contextlib.ExitStack() as stack:
        viewport = scenario.browser.viewport
        context = open_context(
            playwright,
            cast("Engine", args.engine),
            headed=True,
            timeout_ms=120_000,
            budget_seconds=120,
            stack=stack,
            viewport={"width": viewport.width, "height": viewport.height} if viewport else None,
            locale=scenario.browser.locale,
            storage_state=Path(args.storage_state) if args.storage_state else None,
        )
        page = context.pages[0] if context.pages else context.new_page()
        records = plan_records(scenario)
        _emit("replaying", steps=len(records))
        seconds = scenario.deadline / 1000 if scenario.deadline else REPLAY_SECONDS
        try:
            run_steps(
                page,
                scenario,
                records=records,
                context={"inputs": inputs, "secrets": secrets, "env": dict(os.environ)},
                base_url=args.base_url or scenario.browser.base_url,
                artifacts=out,
                deadline=Deadline.after(seconds),
            )
        except Exception as error:
            failed = next((item for item in records if item.status == "failed"), None)
            message = mask(f"{type(error).__name__}: {error}".splitlines()[0], secrets)
            _emit("error", step=failed.id if failed else None, message=message)
            return EXIT_REPLAY_FAILED
        enable_recorder(context, Path(args.output))
        _emit("recording")
        _wait_closed(context)
    return 0


def main(argv: list[str] | None = None) -> int:
    set_locale(parse_locale(os.environ.get(ENV_VAR, "")) or DEFAULT_LOCALE)
    parser = argparse.ArgumentParser(prog="python -m rpa_runner.record")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--engine", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--base-url")
    parser.add_argument("--storage-state")
    args = parser.parse_args(argv)
    try:
        return record(args)
    except Exception as error:
        _emit("error", step=None, message=f"{type(error).__name__}: {error}".splitlines()[0])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
