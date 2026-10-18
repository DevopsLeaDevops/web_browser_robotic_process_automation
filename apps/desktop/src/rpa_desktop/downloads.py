"""下載瀏覽器（M10.1）：用 App 內附的 Playwright driver，邊下載邊回報進度。

直接啟動 Playwright 的 driver（Node），不經過 ``rpa-child``：視窗版沒有主控台，多一層主控台程式
就會跳出一個主控台視窗（:func:`rpa_runner.commands.no_window_flags`）。driver 的位置用 Playwright
內部的 ``compute_driver_executable``；找不到時退回 ``python -m playwright install``。

進度：Playwright 每下載一段印一行 ``|■■■■      |  40% of 167.3 MiB``，格式不是公開的介面；
解析不到時回報 None（畫面只顯示「下載中」）。
"""

import importlib
import logging
import os
import re
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import IO, Final, cast

from rpa_runner.commands import no_window_flags, playwright_command

__all__ = ["DownloadResult", "download_browser", "driver_command", "parse_percent"]

logger = logging.getLogger("rpa_desktop.downloads")

_PERCENT: Final = re.compile(r"\|\s*(\d{1,3})%\s+of\s")
_TAIL_LINES: Final = 12

Progress = Callable[[int | None], None]
"""下載進度（0～100；不知道時 None）。"""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    code: int
    """driver 的結束碼；0 是成功。"""
    tail: str
    """最後幾行輸出（不含進度列），失敗時給人看原因。"""


def parse_percent(text: str) -> int | None:
    """從一段輸出取出最後一個進度百分比。"""
    found = _PERCENT.findall(text)
    if not found:
        return None
    return max(0, min(100, int(found[-1])))


def driver_command(args: list[str]) -> list[str]:
    """直接執行 Playwright driver 的命令；找不到 driver 時退回 ``python -m playwright``。"""
    try:
        module = importlib.import_module("playwright._impl._driver")
        compute = cast("Callable[[], tuple[str, str]]", module.compute_driver_executable)
        executable, cli = compute()
    except (ImportError, AttributeError, OSError) as error:
        logger.warning("找不到 Playwright driver，改用 playwright 模組：%s", error)
        return playwright_command(args)
    return [str(executable), str(cli), *args]


def _driver_env(environ: Mapping[str, str]) -> dict[str, str]:
    env = dict(environ)
    try:
        module = importlib.import_module("playwright._impl._driver")
        extra = cast("Callable[[], Mapping[str, str]]", module.get_driver_env)()
    except (ImportError, AttributeError):
        return env
    merged = dict(extra)
    merged.update(env)  # 呼叫的人給的（瀏覽器位置、鏡像）優先
    return merged


def _pieces(stream: IO[bytes]) -> list[str] | None:
    """讀出目前有的輸出（不等滿 4 KB），依換行與歸位字元切開；結束時回傳 None。"""
    chunk = os.read(stream.fileno(), 4096)
    if not chunk:
        return None
    return re.split(r"[\r\n]+", chunk.decode("utf-8", errors="replace"))


def download_browser(
    engine: str,
    on_progress: Progress,
    environ: Mapping[str, str],
    *,
    cancel: threading.Event | None = None,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> DownloadResult:
    """下載一個瀏覽器（``chromium``、``firefox``）；回傳結束碼與最後幾行輸出。

    ``cancel`` 被設定時結束 driver（結束 App、重新配對時不必等下載完）。
    """
    command = driver_command(["install", engine])
    logger.info("下載瀏覽器：%s", engine)
    process = popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=_driver_env(environ),
        creationflags=no_window_flags(),
    )
    if cancel is not None:

        def watch() -> None:
            while process.poll() is None:
                if cancel.wait(0.5):
                    if process.poll() is None:
                        logger.info("取消下載 %s", engine)
                        process.terminate()
                    return

        threading.Thread(target=watch, name=f"download-{engine}-cancel", daemon=True).start()
    tail: deque[str] = deque(maxlen=_TAIL_LINES)
    pending = ""
    last: int | None = None
    on_progress(None)
    stream = process.stdout
    assert stream is not None
    while True:
        pieces = _pieces(stream)
        if pieces is None:
            break
        pieces[0] = pending + pieces[0]
        pending = pieces.pop()  # 最後一段可能還沒印完
        for line in pieces:
            percent = parse_percent(line)
            if percent is not None:
                if percent != last:
                    last = percent
                    on_progress(percent)
                continue
            if line.strip():
                tail.append(line.strip())
                logger.info("playwright: %s", line.strip())
    if pending.strip():
        percent = parse_percent(pending)
        if percent is None:
            tail.append(pending.strip())
        elif percent != last:
            on_progress(percent)
    code = process.wait()
    logger.info("下載 %s 結束：%s", engine, code)
    return DownloadResult(code, "\n".join(tail))
