"""同一個資料夾只執行一份 RPA Worker（M10.1，ADR 0014）。

用資料夾裡 ``instance.lock`` 的獨占鎖判斷：視窗版、``--no-window`` 與主控台版（``--worker``）
都拿同一把鎖，所以同一份配對不會有兩個程序同時領任務。程序結束（含當掉）時作業系統自動釋放鎖。

第二份開啟時不另外執行：寫一個 ``show.request`` 檔案後結束；第一份每半秒看一次，看到就叫出視窗。
用檔案而不用 Windows 的具名事件：各系統的行為一樣，Linux 的 CI 也測得到。
"""

import contextlib
import logging
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Final

__all__ = ["LOCK_FILE", "SHOW_FILE", "InstanceLock"]

logger = logging.getLogger("rpa_desktop.single_instance")

LOCK_FILE: Final = "instance.lock"
SHOW_FILE: Final = "show.request"


def _try_lock(handle: IO[bytes]) -> bool:
    if sys.platform == "win32":
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class InstanceLock:
    """一個資料夾的單一執行鎖。"""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._handle: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> bool:
        """取得鎖；已經有另一份在執行時回傳 False。"""
        if self._handle is not None:
            return True
        self.folder.mkdir(parents=True, exist_ok=True)
        handle = (self.folder / LOCK_FILE).open("a+b")
        if handle.tell() == 0:
            handle.write(b"\0")  # Windows 鎖的是位元組範圍，檔案至少要有一個位元組
            handle.flush()
        if not _try_lock(handle):
            handle.close()
            return False
        self._handle = handle
        (self.folder / SHOW_FILE).unlink(missing_ok=True)  # 之前留下的請求不算
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        with contextlib.suppress(OSError):
            _unlock(self._handle)
        self._handle.close()
        self._handle = None

    def request_show(self) -> None:
        """（第二份）請已經在執行的那份叫出視窗。"""
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / SHOW_FILE).write_text(str(os.getpid()), encoding="utf-8")

    def watch(
        self, on_show: Callable[[], None], stop: threading.Event, interval: float = 0.5
    ) -> threading.Thread:
        """（第一份）在背景看有沒有叫出視窗的請求。"""
        request = self.folder / SHOW_FILE

        def loop() -> None:
            while not stop.wait(interval):
                if not request.exists():
                    continue
                request.unlink(missing_ok=True)
                try:
                    on_show()
                except Exception:
                    logger.exception("叫出視窗失敗")

        thread = threading.Thread(target=loop, name="rpa-show-request", daemon=True)
        thread.start()
        return thread
