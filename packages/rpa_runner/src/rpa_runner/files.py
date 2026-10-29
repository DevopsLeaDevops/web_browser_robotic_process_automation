"""執行目錄裡的檔案名稱，與原型 sample-run/ 的執行契約一致。

見 docs/design/architecture.html#mvp。
"""

import json
import os
import time
from pathlib import Path
from typing import Final

__all__ = [
    "ASSERTION_LOG",
    "AUTOMATION_LOG",
    "CANDIDATE",
    "DIAGNOSTIC",
    "FACTS",
    "INPUT",
    "LOGIN",
    "LOGIN_LOG",
    "LOGIN_SCREENSHOT",
    "OUTPUT",
    "REPLACE_ATTEMPTS",
    "REPLACE_DELAY",
    "REPORT",
    "RESULT",
    "SCENARIO_DIR",
    "SCREENSHOT",
    "STEPS",
    "STEP_SHOTS",
    "VIDEO",
    "VIDEO_INFO",
    "VIDEO_TMP",
    "read_json",
    "read_json_or",
    "write_json",
]

INPUT: Final = "input.json"
"""校驗後的本次入參。"""
FACTS: Final = "facts.json"
"""自動化抽取的頁面事實；不代表成功。"""
OUTPUT: Final = "output.json"
"""只有獨立斷言與出參校驗都通過才會產生。"""
CANDIDATE: Final = "candidate-output.json"
"""Python 腳本場景：assertion.py 寫出的候選出參，校驗後改名為 output.json。"""
STEPS: Final = "steps.json"
DIAGNOSTIC: Final = "diagnostic.json"
SCREENSHOT: Final = "screenshot.png"
AUTOMATION_LOG: Final = "automation.log"
ASSERTION_LOG: Final = "assertion.log"
LOGIN: Final = "login.json"
"""登入檢查的結果：角色、是否已登入、是否自動登入過（不含登入狀態本身）。"""
LOGIN_LOG: Final = "login.log"
LOGIN_SCREENSHOT: Final = "login.png"
"""需要登入時，確認網址的截圖。"""
SCENARIO_DIR: Final = "scenario"
"""本次使用的場景快照（含 Python 腳本）。"""
RESULT: Final = "result.json"
REPORT: Final = "report.html"
VIDEO: Final = "video.webm"
"""自動化階段的錄影（M12）。"""
VIDEO_INFO: Final = "video.json"
"""錄影的說明：開始時間、長度、大小、是否修復過（見 video.py）。"""
VIDEO_TMP: Final = ".video"
"""錄影時 Playwright 寫入的暫存資料夾；執行結束時整理成 video.webm 後刪掉。"""
STEP_SHOTS: Final = "steps"
"""錄影時每一步做完的縮小截圖（``steps/001.jpg``…，見 stepshots.py）；跟著執行紀錄保存。"""

REPLACE_ATTEMPTS: Final = 50
"""Windows 上改名被別的程序擋住時最多試幾次；每次間隔 REPLACE_DELAY 秒，合計約 1 秒。"""
REPLACE_DELAY: Final = 0.02


def write_json(path: Path, value: object) -> None:
    """寫出 JSON：先寫暫存檔再改名，子程序在寫到一半時被終止也不會留下不完整的檔案。

    Windows 上別的程序正開著 path 時（回看、測試在讀執行中的 steps.json），改名會丟
    PermissionError（WinError 5），稍等重試；其他系統的 PermissionError 是真的沒有權限，照舊丟出。
    """
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == REPLACE_ATTEMPTS:
                raise
            time.sleep(REPLACE_DELAY)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_or(path: Path, default: object) -> object:
    """讀取 JSON；檔案不存在或內容不完整（例如舊版寫到一半被終止）時回傳 default。"""
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default
