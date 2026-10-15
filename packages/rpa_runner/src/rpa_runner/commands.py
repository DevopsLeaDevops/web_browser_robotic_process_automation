"""子程序的命令列（M10，ADR 0014）：開發環境與打包後的桌面 App 用同一套寫法。

Runner、登入檢查、錄製、逐步調試與 codegen 都在子程序執行。所有啟動子程序的地方都經由這裡
產生命令，不直接寫 ``sys.executable -m …``：

- **開發環境**：``python -m 模組 …``、``python 腳本 …``，和以前完全一樣。
- **打包後**（PyInstaller，``sys.frozen``）：``sys.executable`` 是 App 本身，沒有 ``-m`` 可用，
  改成 App 自己的入口：``App --rpa-module 模組 …``、``App --rpa-script 腳本 …``。
  入口的處理在 ``rpa_desktop.entry``；兩邊只靠這裡的兩個旗標約定。

codegen 用 ``playwright`` 模組本身（``python -m playwright codegen …``），打包後一樣經由
``--rpa-module``，由 Playwright 自己找到內附的 driver。
"""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

__all__ = [
    "FROZEN_MODULE",
    "FROZEN_SCRIPT",
    "is_frozen",
    "module_command",
    "playwright_command",
    "script_command",
]

FROZEN_MODULE: Final = "--rpa-module"
"""打包後的 App 收到這個旗標時，把下一個參數當成模組名稱，以 ``__main__`` 執行。"""
FROZEN_SCRIPT: Final = "--rpa-script"
"""打包後的 App 收到這個旗標時，把下一個參數當成 Python 腳本的路徑執行（Python 腳本場景）。"""


def is_frozen() -> bool:
    """目前是不是打包後的 App（PyInstaller 會設定 ``sys.frozen``）。"""
    return bool(getattr(sys, "frozen", False))


def module_command(module: str, args: Sequence[str] = ()) -> list[str]:
    """以 ``__main__`` 執行一個模組的命令：``python -m 模組 …``。"""
    if is_frozen():
        return [sys.executable, FROZEN_MODULE, module, *args]
    return [sys.executable, "-m", module, *args]


def script_command(script: Path | str, args: Sequence[str] = ()) -> list[str]:
    """執行一個 Python 腳本的命令：``python 腳本 …``（Python 腳本場景的自動化與斷言）。"""
    if is_frozen():
        return [sys.executable, FROZEN_SCRIPT, str(script), *args]
    return [sys.executable, str(script), *args]


def playwright_command(args: Sequence[str]) -> list[str]:
    """Playwright 命令列（例如 ``codegen``、``install``）：``python -m playwright …``。"""
    return module_command("playwright", args)
