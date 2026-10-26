"""automation.log 的內容：自動化階段的逐步紀錄（DSL 場景），給人讀。

自動化子程序（child.py）把這些行寫到標準輸出，父程序把標準輸出與標準錯誤一起存成
automation.log；Playwright 印出的訊息也會夾在中間。格式（目前語言）：

    自動化日誌：ba-001 新增紀錄
    這份檔案逐步記下……
    執行編號 … · 瀏覽器 Chromium · 有頭（顯示視窗）· 起始網址 http://…
    開始時間 2026-10-25 21:30:12（這台電腦的時間，UTC−07:00）

    21:30:13.902  瀏覽器已開啟，共 5 步
    21:30:14.714  第 1/5 步  打開首頁（goto）  通過  812 ms
                  網址 http://127.0.0.1:8765/
    21:30:45.100  第 3/5 步  送出（click）  失敗  30000 ms
                  錯誤 TimeoutError: Locator.click: Timeout 30000ms exceeded.
                  略過 第 4～5 步（前一步失敗）

    21:30:45.120  失敗：第 3 步「送出」，……

時間是執行這次運行的那台電腦的當地時間。網址與錯誤都遮罩 Secrets 的值；不寫入參的值
（在 input.json）。每寫一行就 flush，執行到一半也看得到進度。
"""

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final, TextIO

from rpa_core.dsl import Scenario
from rpa_runner.browser import StepRecord
from rpa_runner.i18n import t
from rpa_runner.installed import DISPLAY_NAMES
from rpa_runner.secrets import mask

__all__ = ["StepLog"]

_INDENT: Final = " " * 14
"""明細行對齊時間後面的文字（「HH:MM:SS.mmm」加兩個空白）。"""


def _offset(moment: datetime) -> str:
    """UTC 偏移，例如 UTC−07:00、UTC+08:00（減號用 U+2212，和文件的寫法一致）。"""
    delta = moment.utcoffset() or timedelta(0)
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    minutes = abs(minutes)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


class StepLog:
    """寫 automation.log 的一行行內容；``stream`` 通常是子程序的標準輸出。"""

    def __init__(
        self,
        stream: TextIO,
        *,
        secrets: Mapping[str, str],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.stream = stream
        self.secrets = secrets
        self.clock = clock
        self.started = clock()
        self.logged = 0

    # ------------------------------------------------------------ 輸出

    def _write(self, *lines: str) -> None:
        self.stream.write("".join(line + "\n" for line in lines))
        self.stream.flush()

    def _now(self, moment: float | None = None) -> str:
        local = datetime.fromtimestamp(self.clock() if moment is None else moment).astimezone()
        return local.strftime("%H:%M:%S.") + f"{local.microsecond // 1000:03d}"

    def _mask(self, text: str) -> str:
        return mask(text, self.secrets)

    # ------------------------------------------------------------ 段落

    def header(
        self,
        scenario: Scenario,
        *,
        run_id: str,
        engine: str,
        headed: bool,
        base_url: str | None,
    ) -> None:
        """檔案開頭：這是什麼、這次的設定、開始時間。"""
        start = datetime.fromtimestamp(self.started).astimezone()
        window = t("steplog.window_headed") if headed else t("steplog.window_headless")
        url = self._mask(base_url) if base_url else t("steplog.no_url")
        self._write(
            t("steplog.title", id=scenario.id, name=scenario.name),
            t("steplog.about"),
            t(
                "steplog.meta",
                run_id=run_id,
                engine=DISPLAY_NAMES.get(engine, engine),
                window=window,
                url=url,
            ),
            t(
                "steplog.started",
                time=start.strftime("%Y-%m-%d %H:%M:%S"),
                offset=_offset(start),
            ),
            "",
        )

    def browser_ready(self, total: int) -> None:
        self._write(f"{self._now()}  " + t("steplog.browser", total=total))

    def progress(self, records: Sequence[StepRecord]) -> None:
        """記下剛結束的步驟（run_steps 每一步結束時呼叫）。"""
        total = len(records)
        while self.logged < total and records[self.logged].ended_at is not None:
            record = records[self.logged]
            self.logged += 1
            self._step(self.logged, total, record)

    def _step(self, number: int, total: int, record: StepRecord) -> None:
        status = t("steplog.passed") if record.status == "passed" else t("steplog.failed")
        lines = [
            f"{self._now(record.ended_at)}  "
            + t(
                "steplog.step",
                n=number,
                total=total,
                name=record.name or record.id,
                action=record.action,
                status=status,
                ms=record.duration_ms,
            )
        ]
        if record.error:
            lines.append(_INDENT + t("steplog.error", error=self._mask(record.error)))
        if record.url and (record.action == "goto" or record.status != "passed"):
            # 每一步都印網址太吵：只在打開網頁與出錯時印（每一步的網址在 steps.json）
            lines.append(_INDENT + t("steplog.url", url=self._mask(record.url)))
        for name in record.artifacts:
            lines.append(_INDENT + t("steplog.artifact", file=name))
        if record.status != "passed" and number < total:
            first, last = number + 1, total
            key = "steplog.skipped_one" if first == last else "steplog.skipped"
            lines.append(_INDENT + t(key, first=first, last=last))
        self._write(*lines)

    def finished(self, facts: Mapping[str, object]) -> None:
        """全部步驟通過：總結、抽取到哪些事實、下一階段。"""
        seconds = f"{self.clock() - self.started:.1f}"
        lines = ["", f"{self._now()}  " + t("steplog.done", total=self.logged, seconds=seconds)]
        if facts:
            lines.append(_INDENT + t("steplog.facts", names=", ".join(facts)))
        lines.append(_INDENT + t("steplog.next"))
        self._write(*lines)

    def failed(
        self, records: Sequence[StepRecord], error: BaseException, *, timed_out: bool
    ) -> None:
        """失敗或逾時：停在哪一步、證據在哪裡；最後附上完整的錯誤原文。"""
        self.progress(records)
        seconds = f"{self.clock() - self.started:.1f}"
        failed = next(
            (
                (index, record)
                for index, record in enumerate(records, 1)
                if record.status == "failed"
            ),
            None,
        )
        if failed is None:
            key = "steplog.timed_out_before" if timed_out else "steplog.failed_before"
            summary = t(key, seconds=seconds)
        else:
            number, record = failed
            key = "steplog.timed_out_step" if timed_out else "steplog.failed_step"
            summary = t(key, n=number, name=record.name or record.id, seconds=seconds)
        detail = self._mask(f"{type(error).__name__}: {error}")
        self._write(
            "",
            f"{self._now()}  {summary}",
            _INDENT + t("steplog.evidence"),
            "",
            t("steplog.details"),
            detail,
        )
