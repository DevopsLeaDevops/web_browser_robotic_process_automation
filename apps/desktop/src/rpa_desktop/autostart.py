"""登入時自動啟動 RPA Worker（M10.1，ADR 0014；macOS 2026-10-22 起）。

- Windows：寫在目前使用者的「登入時執行」
  （``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``）。
- macOS：目前使用者的 LaunchAgent（``~/Library/LaunchAgents/<代號>.plist``，:class:`LaunchAgent`），
  只在登入的桌面工作階段（Aqua）啟動；macOS 13 起會出現在「系統設定 › 一般 › 登入項目」。

有頭模式需要使用者登入桌面，所以不做成系統服務，也不需要管理員權限。
自動啟動時加上 ``--background``：只出現在通知區（macOS 是選單列），不開視窗。

App 的位置可能改變（免安裝版的資料夾被搬走、App 從「下載項目」拖進「應用程式」）：每次啟動時，
已經開啟的話就把路徑改成目前的位置（:meth:`AutoStart.refresh`）。使用者在系統裡停用時（工作管理員的
「啟動」頁、macOS 的登入項目），系統另外記錄停用，這裡不會把它改回來。
開發環境與其他系統不支援（:attr:`AutoStart.supported` 為 False）。
"""

import plistlib
import shlex
import sys
from pathlib import Path
from typing import Final, Protocol, cast

from rpa_runner.commands import is_frozen

__all__ = [
    "AGENT_LABEL",
    "BACKGROUND_FLAG",
    "RUN_KEY",
    "VALUE_NAME",
    "AutoStart",
    "LaunchAgent",
    "WindowsRun",
    "command_line",
]

RUN_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME: Final = "RPA Worker"
BACKGROUND_FLAG: Final = "--background"
AGENT_LABEL: Final = "io.github.devopsleadevops.rpa.worker"
"""macOS 的 LaunchAgent 代號（和 App 的 bundle identifier 相同）。"""


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


class LaunchAgent:
    """macOS 目前使用者的 LaunchAgent：launchd 在登入時啟動 ``ProgramArguments``。

    介面和 :class:`WindowsRun` 相同，命令是同一種字串（``"路徑" --background``）：存檔時拆成
    參數，讀檔時再組回來，比較時就和 Windows 一樣。讀不懂的檔案當成沒有開啟。
    """

    def __init__(self, label: str = AGENT_LABEL, folder: Path | None = None) -> None:
        self.label = label
        base = Path.home() / "Library" / "LaunchAgents" if folder is None else folder
        self.path = base / f"{label}.plist"

    def get(self) -> str | None:
        try:
            with self.path.open("rb") as handle:
                data: object = plistlib.load(handle)
        except FileNotFoundError:
            return None
        except (plistlib.InvalidFileException, ValueError, OverflowError):
            return None
        if not isinstance(data, dict):
            return None
        arguments = cast("dict[str, object]", data).get("ProgramArguments")
        if not isinstance(arguments, list) or not arguments:
            return None
        parts = cast("list[object]", arguments)
        if not all(isinstance(part, str) and part for part in parts):
            return None
        first, *rest = (str(part) for part in parts)
        return " ".join([f'"{first}"', *rest])

    def set(self, command: str) -> None:
        agent: dict[str, object] = {
            "Label": self.label,
            "ProgramArguments": shlex.split(command),
            "RunAtLoad": True,
            # 只在登入的桌面工作階段啟動（有頭模式要有畫面），不在 SSH 之類的工作階段
            "LimitLoadToSessionType": "Aqua",
            "ProcessType": "Interactive",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("wb") as handle:
            plistlib.dump(agent, handle)
        temporary.replace(self.path)

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


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
        """打包後的 App 才支援（Windows、macOS）；開發環境不寫登錄檔，也不放 LaunchAgent。"""
        entry: RunEntry | None = None
        if is_frozen() and sys.platform == "win32":
            entry = WindowsRun()
        elif is_frozen() and sys.platform == "darwin":
            entry = LaunchAgent()
        return cls(entry, Path(sys.executable))

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
