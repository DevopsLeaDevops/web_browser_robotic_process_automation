"""write_json 改名寫入：Windows 上目標檔被別的程序開著時要等它關掉，不能讓執行失敗。"""

import sys
import threading
import time
from pathlib import Path

import pytest

from rpa_runner.files import REPLACE_ATTEMPTS, STEPS, read_json, write_json


@pytest.mark.skipif(sys.platform != "win32", reason="只有 Windows 會因為目標檔開著而改名失敗")
def test_write_json_waits_for_a_reader_on_windows(tmp_path: Path) -> None:
    # 執行中的 steps.json 會被回看或測試讀取；讀的一方開著檔案約 0.2 秒
    path = tmp_path / STEPS
    write_json(path, {"steps": 0})
    opened = threading.Event()

    def read_slowly() -> None:
        with path.open(encoding="utf-8"):
            opened.set()
            time.sleep(0.2)

    reader = threading.Thread(target=read_slowly)
    reader.start()
    try:
        assert opened.wait(5)
        # 確認真的重現：開著時直接改名會失敗（WinError 5）
        other = tmp_path / "other.json"
        other.write_text("{}", encoding="utf-8")
        with pytest.raises(PermissionError):
            other.replace(path)
        write_json(path, {"steps": 1})
    finally:
        reader.join()

    assert read_json(path) == {"steps": 1}
    assert not (tmp_path / f".{STEPS}.tmp").exists()


def replace_attempts_when_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """改名一直被拒絕時，write_json 試了幾次才把 PermissionError 丟出。"""
    attempts = 0

    def denied(self: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "replace", denied)
    with pytest.raises(PermissionError):
        write_json(tmp_path / STEPS, {"steps": 0})
    return attempts


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 才重試")
def test_write_json_gives_up_after_a_second_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert replace_attempts_when_denied(tmp_path, monkeypatch) == REPLACE_ATTEMPTS


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 會重試")
def test_write_json_does_not_retry_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 其他系統的 PermissionError 是真的沒有權限，重試也沒用
    assert replace_attempts_when_denied(tmp_path, monkeypatch) == 1
