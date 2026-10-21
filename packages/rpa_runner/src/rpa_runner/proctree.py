"""Windows 的程序樹（M12）：錄影時取消，要先只結束瀏覽器，讓 Playwright 把影片寫完。

``taskkill /T`` 會連 ffmpeg 一起結束；只留下 ffmpeg 也不夠：Node（Playwright 的 driver）把子程序
放在「Node 結束時一起結束」的 Job Object，結束 Node 時 ffmpeg 也被結束。所以先列出子孫、只結束
瀏覽器（見 run._stop_browsers_first）。其他系統不需要：Playwright 把瀏覽器與 ffmpeg 放在自己的
程序群組，終止子程序的程序群組不會碰到它們；ffmpeg 發現輸入斷了就自己收尾。

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
_QUERY_LIMITED: Final = 0x1000
"""PROCESS_QUERY_LIMITED_INFORMATION：讀建立時間用。"""
_WAIT_TIMEOUT: Final = 0x00000102


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    parent: int
    name: str
    """執行檔名稱，例如 ffmpeg-win64.exe。"""
    created: int | None = None
    """建立的時間（FILETIME，100 奈秒）；讀不到時是 None。"""


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
    _kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    _kernel32.GetProcessTimes.restype = wintypes.BOOL

    def _created(pid: int) -> int | None:
        handle = _kernel32.OpenProcess(_QUERY_LIMITED, False, pid)
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not _kernel32.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            _kernel32.CloseHandle(handle)

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

    def _created(pid: int) -> int | None:
        return None


def descendants(root: int, processes: list[ProcessInfo] | None = None) -> list[ProcessInfo]:
    """root 的子孫（不含 root），由上往下；``processes`` 給測試用，預設列出這台電腦的程序。

    Windows 的程序代號會重複使用，只記父程序的代號：父程序結束後，它的子程序還指著那個代號，
    之後拿到同一個代號的程序就會被誤認成父程序。所以子程序的建立時間要晚於父程序，
    不是的就不算（兩邊都讀得到建立時間時才判斷；只讀走訪到的程序）。
    """
    every = _snapshot() if processes is None else processes
    born: dict[int, int | None] = {}

    def created(item: ProcessInfo) -> int | None:
        if item.pid not in born:
            born[item.pid] = item.created if processes is not None else _created(item.pid)
        return born[item.pid]

    children: dict[int, list[ProcessInfo]] = {}
    top: ProcessInfo | None = None
    for item in every:
        if item.pid == root:
            top = item
        if item.pid != item.parent:  # 系統程序的父程序可能是自己
            children.setdefault(item.parent, []).append(item)
    found: list[ProcessInfo] = []
    queue: list[tuple[int, int | None]] = [(root, created(top) if top is not None else None)]
    seen = {root}
    while queue:
        parent, parent_born = queue.pop(0)
        for child in children.get(parent, []):
            if child.pid in seen:
                continue
            child_born = created(child)
            if parent_born is not None and child_born is not None and child_born < parent_born:
                continue  # 代號被重複使用：這是先前同一個代號的程序留下的子程序
            seen.add(child.pid)
            found.append(ProcessInfo(child.pid, child.parent, child.name, child_born))
            queue.append((child.pid, child_born))
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
