"""子程序的命令列（M10，ADR 0014）：開發環境與打包後的桌面 App 用同一套寫法。

Runner、登入檢查、錄製、逐步調試與 codegen 都在子程序執行。所有啟動子程序的地方都經由這裡
產生命令，不直接寫 ``sys.executable -m …``：

- **開發環境**：``python -m 模組 …``、``python 腳本 …``，和以前完全一樣。
- **打包後**（PyInstaller，``sys.frozen``）：``sys.executable`` 是 App 本身，沒有 ``-m`` 可用，
  改成 App 自己的入口：``rpa-child --rpa-module 模組 …``、``rpa-child --rpa-script 腳本 …``。
  ``rpa-child`` 是 App 資料夾裡另一個主控台程式（和 App 共用同一份程式碼）：Windows 上有視窗的
  App 沒有標準輸出，子程序要用主控台程式才能逐行回報。找不到時退回 App 本身。
  入口的處理在 ``rpa_desktop.entry``；兩邊只靠這裡的旗標與檔名約定。

codegen 用 ``playwright`` 模組本身（``python -m playwright codegen …``），打包後一樣經由
``--rpa-module``，由 Playwright 自己找到內附的 driver。
"""

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

__all__ = [
    "CHILD_EXECUTABLE",
    "FROZEN_MODULE",
    "FROZEN_SCRIPT",
    "interpreter",
    "is_frozen",
    "module_command",
    "playwright_command",
    "script_command",
]

FROZEN_MODULE: Final = "--rpa-module"
"""打包後的 App 收到這個旗標時，把下一個參數當成模組名稱，以 ``__main__`` 執行。"""
FROZEN_SCRIPT: Final = "--rpa-script"
"""打包後的 App 收到這個旗標時，把下一個參數當成 Python 腳本的路徑執行（Python 腳本場景）。"""
CHILD_EXECUTABLE: Final = "rpa-child"
"""打包後跑子程序用的主控台程式名稱（Windows 加 .exe），和 App 放在同一個資料夾。"""


def is_frozen() -> bool:
    """目前是不是打包後的 App（PyInstaller 會設定 ``sys.frozen``）。"""
    return bool(getattr(sys, "frozen", False))


def interpreter() -> str:
    """子程序用的執行檔：開發環境是目前的 Python；打包後是同資料夾的 rpa-child。"""
    if not is_frozen():
        return sys.executable
    name = CHILD_EXECUTABLE + (".exe" if os.name == "nt" else "")
    child = Path(sys.executable).with_name(name)
    return str(child) if child.is_file() else sys.executable


def module_command(module: str, args: Sequence[str] = ()) -> list[str]:
    """以 ``__main__`` 執行一個模組的命令：``python -m 模組 …``。"""
    if is_frozen():
        return [interpreter(), FROZEN_MODULE, module, *args]
    return [sys.executable, "-m", module, *args]


def script_command(script: Path | str, args: Sequence[str] = ()) -> list[str]:
    """執行一個 Python 腳本的命令：``python 腳本 …``（Python 腳本場景的自動化與斷言）。"""
    if is_frozen():
        return [interpreter(), FROZEN_SCRIPT, str(script), *args]
    return [sys.executable, str(script), *args]


def playwright_command(args: Sequence[str]) -> list[str]:
    """Playwright 命令列（例如 ``codegen``、``install``）：``python -m playwright …``。"""
    return module_command("playwright", args)
