"""同一個資料夾只執行一份（rpa_desktop.single_instance）。"""

import threading
from pathlib import Path

from rpa_desktop.single_instance import SHOW_FILE, InstanceLock


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
