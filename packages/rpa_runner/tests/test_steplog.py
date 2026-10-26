"""automation.log 的逐步紀錄（steplog.py）：不需要瀏覽器。"""

import io
from datetime import datetime

from rpa_core.dsl import validate_text
from rpa_core.i18n import use_locale
from rpa_runner.browser import StepRecord
from rpa_runner.steplog import StepLog

SCENE = """\
schemaVersion: 1
id: demo-log
name: 新增紀錄
browser: { engine: chromium, baseUrl: http://127.0.0.1:8765 }
steps:
  - { id: open, name: 打開首頁, action: goto, url: / }
  - { id: title, name: 填入標題, action: fill, target: { label: 標題 }, value: x }
  - { id: submit, name: 送出, action: click, target: { role: button, name: 送出 } }
  - { id: read, action: extract, target: { css: '#id' }, as: recordId }
"""


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 25, 21, 30, 12).timestamp()

    def __call__(self) -> float:
        return self.now


def _records() -> list[StepRecord]:
    return [
        StepRecord("open", "goto", "打開首頁"),
        StepRecord("title", "fill", "填入標題"),
        StepRecord("submit", "click", "送出"),
        StepRecord("read", "extract", None),
    ]


def _finish(record: StepRecord, clock: Clock, ms: int, *, error: str | None = None) -> None:
    record.started_at = clock.now
    clock.now += ms / 1000
    record.ended_at = clock.now
    record.duration_ms = ms
    record.status = "failed" if error else "passed"
    record.error = error
    record.url = "http://127.0.0.1:8765/new?token=s3cr3t-value"


def test_passed_run_reads_like_a_story() -> None:
    scenario = validate_text(SCENE).scenario
    assert scenario is not None
    clock = Clock()
    out = io.StringIO()
    records = _records()
    with use_locale("zh-Hant"):
        log = StepLog(out, secrets={"TOKEN": "s3cr3t-value"}, clock=clock)
        log.header(
            scenario,
            run_id="demo-log-20261026-043012-abcdef",
            engine="chromium",
            headed=True,
            base_url="http://127.0.0.1:8765",
        )
        log.browser_ready(len(records))
        for record in records:
            _finish(record, clock, 250)
            log.progress(records)
        log.progress(records)  # 重複呼叫不會重複寫
        log.finished({"recordId": "R-1"})
    text = out.getvalue()

    assert text.startswith("自動化日誌：demo-log 新增紀錄\n")
    assert "瀏覽器 Chromium · 有頭（顯示視窗） · 起始網址 http://127.0.0.1:8765" in text
    assert "開始時間 2026-10-25 21:30:12（這台電腦的時間，UTC" in text
    assert "第 1/4 步  打開首頁（goto）  通過  250 ms" in text
    assert text.count("第 2/4 步") == 1
    assert "第 4/4 步  read（extract）  通過" in text  # 沒有名稱時用步驟 id
    # 只有打開網頁的那一步印網址，而且遮罩 Secret
    assert text.count("\n              網址 ") == 1
    assert "網址 http://127.0.0.1:8765/new?token=***" in text
    assert "s3cr3t-value" not in text
    assert "完成：4 步全部通過，耗時 1.0 秒。" in text
    assert "抽取的頁面事實：recordId（值在 facts.json）" in text


def test_failed_step_explains_where_to_look() -> None:
    scenario = validate_text(SCENE).scenario
    assert scenario is not None
    clock = Clock()
    out = io.StringIO()
    records = _records()
    with use_locale("en"):
        log = StepLog(out, secrets={}, clock=clock)
        log.header(scenario, run_id="r", engine="firefox", headed=False, base_url=None)
        _finish(records[0], clock, 100)
        _finish(records[1], clock, 30000, error="TimeoutError: Locator.fill: Timeout 30000ms")
        log.progress(records)
        log.failed(
            records, TimeoutError("Locator.fill: Timeout 30000ms\ncall log: ..."), timed_out=False
        )
    text = out.getvalue()

    assert "browser Firefox · headless (no window) · start URL (not set in the scene)" in text
    assert "Step 2/4  填入標題 (fill)  FAILED  30000 ms" in text
    assert "Error TimeoutError: Locator.fill: Timeout 30000ms" in text
    assert "Skipped steps 3–4 (the step before failed)" in text
    assert "Failed at step 2 “填入標題” after 30.1 s." in text
    assert "screenshot.png" in text
    # 最後附上完整的錯誤原文（多行），找不到原因時看這裡
    assert text.rstrip().endswith("call log: ...")


def test_failure_before_the_first_step() -> None:
    scenario = validate_text(SCENE).scenario
    assert scenario is not None
    out = io.StringIO()
    with use_locale("zh-Hant"):
        log = StepLog(out, secrets={}, clock=Clock())
        log.failed(_records(), RuntimeError("瀏覽器沒有開起來"), timed_out=False)
    assert "失敗：在第一步之前" in out.getvalue()
    assert "RuntimeError: 瀏覽器沒有開起來" in out.getvalue()
