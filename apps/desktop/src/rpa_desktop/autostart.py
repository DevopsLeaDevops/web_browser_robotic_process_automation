"""登入 Windows 時自動啟動 RPA Worker（M10.1，ADR 0014）。

寫在目前使用者的「登入時執行」（``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``）：
有頭模式需要使用者登入桌面，所以不做成系統服務，也不需要管理員權限。
自動啟動時加上 ``--background``：只出現在通知區，不開視窗。

免安裝版的資料夾可能被搬走：每次啟動時，已經開啟的話就把路徑改成目前的位置（:meth:`AutoStart.refresh`）。
使用者在工作管理員的「啟動」頁停用時，Windows 另外記錄停用，這裡不會把它改回來。
開發環境與其他系統不支援（:attr:`AutoStart.supported` 為 False）。
"""

import sys
from pathlib import Path
from typing import Final, Protocol

from rpa_runner.commands import is_frozen

__all__ = ["BACKGROUND_FLAG", "RUN_KEY", "VALUE_NAME", "AutoStart", "WindowsRun", "command_line"]

RUN_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME: Final = "RPA Worker"
BACKGROUND_FLAG: Final = "--background"


class RunEntry(Protocol):
    """「登入時執行」裡的一個值（測試用替身）。"""

    def get(self) -> str | None: ...

    def set(self, command: str) -> None: ...

    def delete(self) -> None: ...


class WindowsRun:
    """Windows 登錄檔裡目前使用者的「登入時執行」。"""

    def __init__(self, name: str = VALUE_NAME) -> None:
        self.name = name

    def get(self) -> str | None:
        if sys.platform != "win32":
            raise OSError("only on Windows")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, kind = winreg.QueryValueEx(key, self.name)
        except FileNotFoundError:
            return None
        return value if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and value else None

    def set(self, command: str) -> None:
        if sys.platform != "win32":
            raise OSError("only on Windows")
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, self.name, 0, winreg.REG_SZ, command)

    def delete(self) -> None:
        if sys.platform != "win32":
            raise OSError("only on Windows")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.name)
        except FileNotFoundError:
            return


def command_line(executable: Path) -> str:
    """登入時執行的命令：路徑加引號（可能有空白），只開通知區。"""
    return f'"{executable}" {BACKGROUND_FLAG}'


class AutoStart:
    """開啟、關閉與更新自動啟動。``entry`` 為 None 表示這個環境不支援。"""

    def __init__(self, entry: RunEntry | None, executable: Path) -> None:
        self.entry = entry
        self.command = command_line(executable)

    @classmethod
    def for_this_app(cls) -> "AutoStart":
        """打包後的 Windows App 才支援；開發環境不寫登錄檔。"""
        supported = sys.platform == "win32" and is_frozen()
        return cls(WindowsRun() if supported else None, Path(sys.executable))

    @property
    def supported(self) -> bool:
        return self.entry is not None

    def enabled(self) -> bool:
        if self.entry is None:
            return False
        try:
            return self.entry.get() is not None
        except OSError:
            return False

    def enable(self) -> None:
        if self.entry is None:
            raise OSError("autostart is not supported here")
        self.entry.set(self.command)

    def disable(self) -> None:
        if self.entry is not None:
            self.entry.delete()

    def refresh(self) -> bool:
        """已經開啟、但路徑不是目前這份 App 時改過來；回傳有沒有改。"""
        if self.entry is None:
            return False
        try:
            current = self.entry.get()
            if current is None or current == self.command:
                return False
            self.entry.set(self.command)
        except OSError:
            return False
        return True
