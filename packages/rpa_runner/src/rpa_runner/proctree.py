"""Windows 的程序樹（M12）：錄影時取消，要結束子程序與瀏覽器，但留下錄影的 ffmpeg 把影片寫完。

``taskkill /T`` 會連 ffmpeg 一起結束，影片沒有長度與索引、最後幾秒也沒寫進去。其他系統不需要：
Playwright 把瀏覽器與 ffmpeg 放在自己的程序群組，終止子程序的程序群組不會碰到它們；ffmpeg 發現
輸入斷了就自己收尾。

用 ``CreateToolhelp32Snapshot`` 列出全部程序，從子程序往下找子孫（要在結束任何一個之前找，
父程序結束後就找不到它的子孫了）。只在 Windows 上有作用；其他系統呼叫時回傳空的結果。
"""

import ctypes
import sys
import time
from dataclasses import dataclass
from typing import Final

__all__ = ["ProcessInfo", "descendants", "terminate", "wait_exit"]

_TH32CS_SNAPPROCESS: Final = 0x00000002
_PROCESS_TERMINATE: Final = 0x0001
_SYNCHRONIZE: Final = 0x00100000
_WAIT_TIMEOUT: Final = 0x00000102


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    parent: int
    name: str
    """執行檔名稱，例如 ffmpeg-win64.exe。"""


if sys.platform == "win32":  # pragma: no cover - Windows 在 CI 的 Worker 測試涵蓋
    from ctypes import wintypes

    class _Entry(ctypes.Structure):
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        )

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Entry))
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Entry))
    _kernel32.Process32NextW.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _INVALID: Final = wintypes.HANDLE(-1).value

    def _snapshot() -> list[ProcessInfo]:
        handle = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not handle or handle == _INVALID:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
        found: list[ProcessInfo] = []
        try:
            entry = _Entry()
            entry.dwSize = ctypes.sizeof(_Entry)
            ok = _kernel32.Process32FirstW(handle, ctypes.byref(entry))
            while ok:
                found.append(
                    ProcessInfo(entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile)
                )
                ok = _kernel32.Process32NextW(handle, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(handle)
        return found

    def _terminate(pid: int) -> None:
        handle = _kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if handle:
            try:
                _kernel32.TerminateProcess(handle, 1)
            finally:
                _kernel32.CloseHandle(handle)

    def _wait(pid: int, milliseconds: int) -> bool:
        handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return True  # 已經結束
        try:
            return _kernel32.WaitForSingleObject(handle, milliseconds) != _WAIT_TIMEOUT
        finally:
            _kernel32.CloseHandle(handle)

else:

    def _snapshot() -> list[ProcessInfo]:
        return []

    def _terminate(pid: int) -> None:
        return None

    def _wait(pid: int, milliseconds: int) -> bool:
        return True


def descendants(root: int, processes: list[ProcessInfo] | None = None) -> list[ProcessInfo]:
    """root 的子孫（不含 root），由上往下；``processes`` 給測試用，預設列出這台電腦的程序。"""
    every = _snapshot() if processes is None else processes
    children: dict[int, list[ProcessInfo]] = {}
    for item in every:
        if item.pid != item.parent:  # 系統程序的父程序可能是自己
            children.setdefault(item.parent, []).append(item)
    found: list[ProcessInfo] = []
    queue = [root]
    seen = {root}
    while queue:
        for child in children.get(queue.pop(0), []):
            if child.pid not in seen:
                seen.add(child.pid)
                found.append(child)
                queue.append(child.pid)
    return found


def terminate(pid: int) -> None:
    """立即結束一個程序（Windows 的 TerminateProcess）；已經結束或沒有權限時不做事。"""
    _terminate(pid)


def wait_exit(pids: list[int], timeout: float) -> list[int]:
    """等這些程序結束，最多 timeout 秒；回傳還沒結束的。"""
    ends = time.monotonic() + timeout
    left = list(pids)
    while left:
        remaining = max(0, int((ends - time.monotonic()) * 1000))
        left = [pid for pid in left if not _wait(pid, min(remaining, 200))]
        if remaining <= 0:
            break
    return left
