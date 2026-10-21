"""錄影時被終止（M12）：Windows 先只結束瀏覽器，讓 Playwright 把影片寫完。

用假的程序樹與假的子程序，不需要 Windows；真的取消在 test_video_browser.py（CI 在 Windows 上跑）。
"""

import os
import subprocess
from pathlib import Path
from typing import cast

import pytest

from rpa_runner import run
from rpa_runner.files import read_json
from rpa_runner.proctree import ProcessInfo

TREE = [
    ProcessInfo(11, 10, "python.exe"),
    ProcessInfo(12, 11, "node.exe"),
    ProcessInfo(13, 12, "chrome-headless-shell.exe"),
    ProcessInfo(14, 13, "chrome-headless-shell.exe"),
    ProcessInfo(15, 12, "ffmpeg-win64.exe"),
    ProcessInfo(16, 11, "conhost.exe"),
]


class FakeChild:
    """假的子程序：``exits`` 為 False 時 wait 一直逾時（子程序沒有自己結束）。"""

    def __init__(self, *, exits: bool = True) -> None:
        self.pid = 10
        self.exits = exits

    def wait(self, timeout: float | None = None) -> int:
        if not self.exits:
            raise subprocess.TimeoutExpired("child", timeout or 0)
        return 1


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {"terminated": [], "stopped": [], "waited": []}

    def wait_exit(pids: list[int], timeout: float) -> list[int]:
        found["waited"].extend(pids)
        return []

    def stop(process: object, *, graceful: Path | None = None) -> None:
        found["stopped"].append(cast("FakeChild", process).pid)

    def terminate(pid: int) -> None:
        found["terminated"].append(pid)

    monkeypatch.setattr(run, "terminate", terminate)
    monkeypatch.setattr(run, "wait_exit", wait_exit)
    monkeypatch.setattr(run, "_stop", stop)
    return found


def _tree(processes: list[ProcessInfo]) -> object:
    def descendants(root: int) -> list[ProcessInfo]:
        return processes

    return descendants


def _stop(child: FakeChild) -> dict[str, object]:
    return run._stop_browsers_first(cast("subprocess.Popen[bytes]", child))  # pyright: ignore[reportPrivateUsage]


def test_only_the_browsers_are_ended_first(
    monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[int]]
) -> None:
    monkeypatch.setattr(run, "descendants", _tree(TREE))

    details = _stop(FakeChild())

    assert calls["terminated"] == [13, 14]  # 子程序、Node、ffmpeg 留著
    assert calls["stopped"] == []
    assert calls["waited"] == [15]  # 子程序結束後再等 ffmpeg 寫完
    assert details["method"] == "browsers_first"
    assert details["browsers"] == 2
    assert details["ffmpegKilled"] == 0


def test_no_browser_yet_stops_right_away(
    monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[int]]
) -> None:
    monkeypatch.setattr(run, "descendants", _tree(TREE[:2]))

    details = _stop(FakeChild())

    assert calls["terminated"] == []
    assert calls["stopped"] == [10]
    assert details["method"] == "taskkill"


def test_a_child_that_does_not_exit_is_stopped(
    monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[int]]
) -> None:
    monkeypatch.setattr(run, "descendants", _tree(TREE))
    monkeypatch.setattr(run, "_BROWSER_STOP_SECONDS", 0.01)

    details = _stop(FakeChild(exits=False))

    assert calls["terminated"] == [13, 14]
    assert calls["stopped"] == [10]
    assert details["method"] == "browsers_then_taskkill"


def test_the_stop_is_recorded_for_the_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """終止的經過寫在錄影的暫存資料夾，整理影片時放進 video.json。"""

    def stop(process: object, *, graceful: Path | None = None) -> None:
        return None

    def browsers_first(process: object) -> dict[str, object]:
        return {"method": "browsers_first"}

    monkeypatch.setattr(run, "_stop", stop)
    monkeypatch.setattr(run, "_stop_browsers_first", browsers_first)
    record = tmp_path / ".video" / "stop.json"

    run._stop_gracefully(cast("subprocess.Popen[bytes]", FakeChild()), record)  # pyright: ignore[reportPrivateUsage]

    details = cast("dict[str, object]", read_json(record))
    expected = "browsers_first" if os.name == "nt" else "process_group"
    assert details["method"] == expected
    assert isinstance(details["stopMs"], int)
