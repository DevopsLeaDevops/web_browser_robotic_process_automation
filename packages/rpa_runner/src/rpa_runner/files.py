"""執行目錄裡的檔案名稱，與原型 sample-run/ 的執行契約一致。

見 docs/design/architecture.html#mvp。
"""

import json
from pathlib import Path
from typing import Final

__all__ = [
    "ASSERTION_LOG",
    "AUTOMATION_LOG",
    "CANDIDATE",
    "DIAGNOSTIC",
    "FACTS",
    "INPUT",
    "OUTPUT",
    "REPORT",
    "RESULT",
    "SCENARIO_DIR",
    "SCREENSHOT",
    "STEPS",
    "read_json",
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
SCENARIO_DIR: Final = "scenario"
"""本次使用的場景快照（含 Python 腳本）。"""
RESULT: Final = "result.json"
REPORT: Final = "report.html"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
