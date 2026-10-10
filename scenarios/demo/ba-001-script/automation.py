"""BA-001 的自動化：填表、建立紀錄，把畫面上的紀錄詳情寫成頁面事實。

只負責操作與觀察；成功與否由 assertion.py 獨立判斷。每次等待只用總期限剩下的時間。
"""

import argparse
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("input", "facts", "screenshot", "target-url"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    params = json.loads(Path(args.input).read_text(encoding="utf-8"))
    deadline = time.monotonic() + float(os.environ.get("RPA_DEADLINE_SECONDS", "45"))

    def remaining() -> int:
        milliseconds = int((deadline - time.monotonic()) * 1000)
        if milliseconds <= 0:
            raise TimeoutError("總期限已到")
        return min(milliseconds, 15_000)

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, os.environ.get("RPA_BROWSER", "firefox"))
        browser = browser_type.launch(timeout=remaining())
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        try:
            page.goto(args.target_url, wait_until="domcontentloaded", timeout=remaining())
            page.get_by_label("標題", exact=True).fill(params["title"], timeout=remaining())
            page.get_by_label("數量", exact=True).fill(str(params["quantity"]), timeout=remaining())
            # 有副作用：只點擊一次，不重試
            page.get_by_role("button", name="建立紀錄", exact=True).click(timeout=remaining())
            page.locator("#receipt").wait_for(state="visible", timeout=remaining())
            facts = {
                "recordId": page.locator("#record-id").inner_text(timeout=remaining()),
                "title": page.locator("#record-title").inner_text(timeout=remaining()),
                "quantity": int(page.locator("#record-quantity").inner_text(timeout=remaining())),
                "status": page.locator("#record-status").inner_text(timeout=remaining()),
            }
            Path(args.facts).write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")
            page.screenshot(path=args.screenshot, full_page=True, timeout=remaining())
        finally:
            browser.close()


if __name__ == "__main__":
    main()
