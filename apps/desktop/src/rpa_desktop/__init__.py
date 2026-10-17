"""rpa_desktop：桌面端（M10，ADR 0014）。

「RPA 錄製端」（macOS）與「RPA Worker」（Windows）共用這個套件，各自一份 PyInstaller 建置設定
（``apps/desktop/packaging``）。打包後的 App 只有一個入口 :func:`rpa_desktop.entry.main`：
子程序（runner、登入檢查、錄製、調試、codegen）也經由它執行，見 :mod:`rpa_runner.commands`。
設計見 docs/design/desktop.html。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-desktop")
