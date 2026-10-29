"""每一步做完時的縮小截圖（2026-10-29，任務 20261029-replay-chapters，ADR 0016 的修訂）。

回看的時間軸、滑過預覽與步驟清單用它當那一步的縮圖。錄影的對時是觀測精度（Chromium 用第一格的
觀測時間，測試容許 ±0.3 秒），每格 40 毫秒；快的步驟（10～80 毫秒）從錄影取不到「那一步做完」的
畫面，所以錄影時每一步結束後另外拍一張：

- 存在執行目錄的 ``steps/<序號>.jpg``（三位數，從 001 起，和步驟的順序一樣）；steps.json 的
  ``shot`` 是相對路徑，``shotAt`` 是開始拍的實際時間（和 startedAt、endedAt 同一個時鐘）。
- 無頭的 Chromium 用 DevTools 的 ``Page.captureScreenshot``，請瀏覽器直接縮成最多 640 寬的 JPEG：
  和 Playwright 的 ``page.screenshot`` 是同一個指令，少了等字型、藏游標等準備，也不用拍原尺寸再縮。
  其他情況（Firefox、WebKit、有頭的 Chromium：背景分頁不一定有畫面，要有逾時）用 Playwright 的
  JPEG 截圖，原尺寸、品質低一點。
- 盡力而為：拍不到（頁面關了、出錯、總期限只剩不到 3 秒）就不拍，不影響步驟的結果；略過的步驟
  不拍；最多 500 張（遠端 Worker 上傳的執行目錄最多 2000 個檔案）。
- 步驟的 durationMs、endedAt 不含拍照的時間；下一步晚一點開始（實測每步約幾十毫秒）。
- 截圖和錄影一樣會留下畫面上的一切（ADR 0016 的 D3），跟著執行紀錄保存（不跟錄影一起刪）。
"""

import base64
import contextlib
import time
import weakref
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import CDPSession, Page

from rpa_runner.browser import Deadline, StepRecord
from rpa_runner.files import STEP_SHOTS

__all__ = ["MAX_SHOTS", "SHOT_WIDTH", "StepShots", "shot_name"]

SHOT_WIDTH: Final = 640
"""截圖的最大寬度（Chromium 無頭時由瀏覽器縮小；其他情況是頁面原本的寬度）。"""
MAX_SHOTS: Final = 500
_SCALED_QUALITY: Final = 70
_FULL_QUALITY: Final = 50
_TIMEOUT_MS: Final = 2000
_RESERVE_MS: Final = 3000
"""總期限剩下不到這麼多就不拍：留給失敗截圖與收尾。"""


def _send(session: CDPSession, method: str, params: dict[str, object] | None = None) -> object:
    # Playwright 的型別把 DevTools 指令的參數與結果寫成沒有型別的 Dict
    return cast("object", session.send(method, params))  # pyright: ignore[reportUnknownMemberType]


def shot_name(index: int) -> str:
    """第 ``index`` 步（從 1 起）的截圖在執行目錄裡的相對路徑：``steps/001.jpg``。"""
    return f"{STEP_SHOTS}/{index:03d}.jpg"


class StepShots:
    """錄影時，每一步做完拍一張縮小的截圖（見模組說明）。"""

    def __init__(self, folder: Path, *, engine: str, headed: bool, deadline: Deadline) -> None:
        self.folder = folder
        self.deadline = deadline
        self.scaled = engine == "chromium" and not headed
        self.taken = 0
        self._sessions: weakref.WeakKeyDictionary[Page, CDPSession] = weakref.WeakKeyDictionary()

    def take(self, page: Page, record: StepRecord, index: int) -> None:
        """拍第 ``index`` 步做完的畫面，記在 ``record``；拍不到就算了。"""
        if record.status == "skipped" or self.taken >= MAX_SHOTS:
            return
        if self.deadline.remaining_ms() < _RESERVE_MS:
            return
        with contextlib.suppress(Exception):
            if page.is_closed():
                return
            relative = shot_name(index)
            target = self.folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            moment = time.time()
            data = self._scaled(page) if self.scaled else self._full(page)
            target.write_bytes(data)
            record.shot = relative
            record.shot_at = moment
            self.taken += 1

    def _full(self, page: Page) -> bytes:
        return page.screenshot(
            type="jpeg",
            quality=_FULL_QUALITY,
            scale="css",
            caret="initial",
            animations="allow",
            timeout=min(_TIMEOUT_MS, max(1, self.deadline.remaining_ms() - _RESERVE_MS)),
        )

    def _scaled(self, page: Page) -> bytes:
        session = self._sessions.get(page)
        if session is None:
            session = page.context.new_cdp_session(page)
            self._sessions[page] = session
        metrics = cast("dict[str, dict[str, float]]", _send(session, "Page.getLayoutMetrics"))
        view = metrics["cssVisualViewport"]
        width, height = view["clientWidth"], view["clientHeight"]
        # 高 DPI 時一個 CSS 像素有好幾個裝置像素：縮放比要再除掉（同 Playwright 的 scale="css"）
        css = metrics.get("cssContentSize", {}).get("width") or 0
        device = metrics.get("contentSize", {}).get("width") or 0
        ratio = device / css if css and device else 1
        scale = min(1.0, SHOT_WIDTH / width) / ratio if width else 1 / ratio
        result = cast(
            "dict[str, str]",
            _send(
                session,
                "Page.captureScreenshot",
                {
                    "format": "jpeg",
                    "quality": _SCALED_QUALITY,
                    "clip": {
                        "x": view["pageX"],
                        "y": view["pageY"],
                        "width": width,
                        "height": height,
                        "scale": scale,
                    },
                    "captureBeyondViewport": False,
                },
            ),
        )
        return base64.b64decode(result["data"])
