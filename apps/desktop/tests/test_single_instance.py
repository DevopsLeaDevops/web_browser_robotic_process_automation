"""同一個資料夾只執行一份（rpa_desktop.single_instance）。"""

import sys
import threading
from pathlib import Path

import pytest

from rpa_desktop.single_instance import APP_MUTEX, SHOW_FILE, STOP_FILE, InstanceLock


def test_second_copy_cannot_take_the_lock(tmp_path: Path) -> None:
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    assert first.acquire()  # 同一份重複取得沒有影響
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_other_folders_are_independent(tmp_path: Path) -> None:
    a, b = InstanceLock(tmp_path / "a"), InstanceLock(tmp_path / "b")
    assert a.acquire()
    assert b.acquire()
    a.release()
    b.release()


def test_show_request_reaches_the_running_copy(tmp_path: Path) -> None:
    first = InstanceLock(tmp_path)
    assert first.acquire()
    shown = threading.Event()
    stop = threading.Event()
    first.watch(shown.set, stop, interval=0.02)
    try:
        InstanceLock(tmp_path).request_show()
        assert shown.wait(5)
        assert not (tmp_path / SHOW_FILE).exists()
    finally:
        stop.set()
        first.release()


def test_stale_show_request_is_ignored(tmp_path: Path) -> None:
    (tmp_path / SHOW_FILE).write_text("1", encoding="utf-8")  # 上次留下的
    lock = InstanceLock(tmp_path)
    assert lock.acquire()
    assert not (tmp_path / SHOW_FILE).exists()
    lock.release()


def test_stop_request_reaches_the_running_copy(tmp_path: Path) -> None:
    first = InstanceLock(tmp_path)
    assert first.acquire()
    stopped = threading.Event()
    finished = threading.Event()
    first.watch(None, finished, interval=0.02, on_stop=stopped.set)
    try:
        InstanceLock(tmp_path).request_show()  # 沒有處理叫出視窗的動作：不理會
        InstanceLock(tmp_path).request_stop()
        assert stopped.wait(5)
    finally:
        finished.set()
        first.release()


def test_watch_retries_a_request_still_being_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows：寫入的那一方還開著檔案時刪不掉（PermissionError）。下一輪再試，監看不能停。"""
    lock = InstanceLock(tmp_path)
    assert lock.acquire()
    original = Path.unlink
    refused: list[Path] = []

    def busy_once(self: Path, missing_ok: bool = False) -> None:
        if self.name == STOP_FILE and not refused:
            refused.append(self)
            raise PermissionError(13, "檔案正在使用中", str(self))
        original(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy_once)
    stopped, finished = threading.Event(), threading.Event()
    lock.watch(None, finished, interval=0.02, on_stop=stopped.set)
    try:
        lock.request_stop()
        assert stopped.wait(5)
        assert refused
        assert not (tmp_path / STOP_FILE).exists()
    finally:
        finished.set()
        lock.release()


def _mutex_exists() -> bool:
    """和 Inno Setup 的 CheckForMutexes 一樣，用 SYNCHRONIZE 權限打開看看。"""
    if sys.platform != "win32":
        raise AssertionError("只在 Windows 上")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_mutex = kernel32.OpenMutexW
    open_mutex.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    open_mutex.restype = wintypes.HANDLE
    close = kernel32.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    handle = open_mutex(0x00100000, False, APP_MUTEX)
    if handle:
        close(handle)
    return bool(handle)


def test_running_copy_holds_the_named_mutex(tmp_path: Path) -> None:
    """安裝檔用 CheckForMutexes 判斷 App 是否在執行：拿到鎖時有、釋放後沒有。"""
    if sys.platform != "win32":
        pytest.skip("Windows 的具名 mutex")
    lock, other = InstanceLock(tmp_path / "a"), InstanceLock(tmp_path / "b")
    assert not _mutex_exists()
    assert lock.acquire()
    assert _mutex_exists()
    assert other.acquire()  # 另一個資料夾的那份也持有，釋放其中一份時仍然在
    lock.release()
    assert _mutex_exists()
    other.release()
    assert not _mutex_exists()
