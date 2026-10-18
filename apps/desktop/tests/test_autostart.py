"""登入時自動啟動（rpa_desktop.autostart）：命令、開啟與關閉、資料夾搬家後更新路徑。

Windows 上另外用真的登錄檔測一次（用測試專用的值名稱，不碰使用者的設定）。
"""

import sys
import uuid
from pathlib import Path

import pytest

from rpa_desktop.autostart import AutoStart, WindowsRun, command_line


class FakeRun:
    def __init__(self, value: str | None = None) -> None:
        self.value = value

    def get(self) -> str | None:
        return self.value

    def set(self, command: str) -> None:
        self.value = command

    def delete(self) -> None:
        self.value = None


EXE = Path(r"C:\Users\amy\RPA Worker\rpa-worker.exe")


def test_command_quotes_the_path_and_starts_in_the_tray() -> None:
    assert command_line(EXE) == f'"{EXE}" --background'


def test_enable_disable_and_refresh() -> None:
    entry = FakeRun()
    autostart = AutoStart(entry, EXE)
    assert autostart.supported
    assert not autostart.enabled()
    assert not autostart.refresh()  # 沒有開啟就不寫入

    autostart.enable()
    assert autostart.enabled()
    assert entry.value == command_line(EXE)
    assert not autostart.refresh()  # 路徑相同不必改

    entry.value = '"D:\\old\\rpa-worker.exe" --background'  # 資料夾被搬走了
    assert autostart.refresh()
    assert entry.value == command_line(EXE)

    autostart.disable()
    assert not autostart.enabled()


def test_unsupported_environment() -> None:
    autostart = AutoStart(None, EXE)
    assert not autostart.supported
    assert not autostart.enabled()
    assert not autostart.refresh()
    autostart.disable()
    with pytest.raises(OSError, match="not supported"):
        autostart.enable()


def test_development_environment_does_not_touch_the_registry() -> None:
    assert not AutoStart.for_this_app().supported  # 測試時不是打包版


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 的登錄檔")
def test_real_windows_registry() -> None:
    entry = WindowsRun(name=f"RPA Worker test {uuid.uuid4().hex[:8]}")
    autostart = AutoStart(entry, EXE)
    try:
        assert not autostart.enabled()
        autostart.enable()
        assert entry.get() == command_line(EXE)
        entry.set("other")
        assert autostart.refresh()
        assert entry.get() == command_line(EXE)
    finally:
        autostart.disable()
    assert entry.get() is None
    autostart.disable()  # 已經沒有也不算錯
