"""RPA Worker 的發布位置（M10.1 PR 3，安裝檔）。

安裝檔在推版本標籤（``v0.2.0``）時由 CI 建好、放進 GitHub Release（草稿，維護者確認後發布）。
狀態視窗的「版本不同」提醒連到最新的 Release，下載新的安裝檔覆蓋安裝即可（配對與設定保留）。
倉庫是公開的，Release 也公開；下載的 Worker 沒有管理 Portal 的邀請就連不上。
"""

from typing import Final

__all__ = ["RELEASES_URL", "REPOSITORY"]

REPOSITORY: Final = "https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation"
RELEASES_URL: Final = f"{REPOSITORY}/releases/latest"
"""最新的正式 Release（草稿與預先發布不算）。"""
