"""rpa_script：Python 節點的腳本介面（ADR 0020）。只用標準函式庫。

用法（運行環境模式的 Python 節點，由 ``python -m rpa_script`` 啟動）::

    from rpa_script import Run, StepError, automation

    @automation
    def main(run: Run) -> None:
        with run.step("read", "讀取報表"):
            ...
        run.facts["total"] = 42

不用這個套件、照檔案契約自己讀寫 ``--input``、``--facts`` 的腳本照樣能跑；
相容模式（沒有 ``runtime``）的腳本也可以 import 它，用 :func:`current` 拿到 :class:`Run`。
"""

import platform
import sys
from importlib.metadata import PackageNotFoundError, version

from rpa_script.core import MASK, Run, StepError, automation, current

__all__ = ["MASK", "Run", "StepError", "__version__", "automation", "current", "selfcheck"]

try:
    __version__: str = version("rpa-script")
except PackageNotFoundError:  # 直接從原始碼執行（沒有安裝）
    __version__ = "0"


def selfcheck() -> dict[str, str]:
    """運行環境的自我檢查用：回傳版本資訊（能 import 就代表套件完整）。"""
    return {
        "rpaScript": __version__,
        "python": platform.python_version(),
        "executable": sys.executable,
    }
