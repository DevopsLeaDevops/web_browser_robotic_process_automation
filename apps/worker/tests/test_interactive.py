"""錄製端互動子程序的檔案同步（rpa_worker.interactive，M10.2）。"""

import os
import time
import zipfile
from pathlib import Path

import pytest

from rpa_worker.interactive import (
    INPUTS,
    MAX_SYNC_FILES,
    SyncError,
    changed_files,
    is_safe_relative,
    pack_files,
    scan,
    unpack_files,
)


@pytest.mark.parametrize(
    "name",
    ["scenario.yaml", ".recording.py", "replay/step-1.png", "a/b/c.txt", "debug.log"],
)
def test_safe_relative_names(name: str) -> None:
    assert is_safe_relative(name)


@pytest.mark.parametrize(
    "name",
    ["", "/etc/passwd", "../x", "a/../b", "a//b", "a\\b", "./a", "a/.", "x\0y", "a" * 401],
)
def test_unsafe_relative_names(name: str) -> None:
    assert not is_safe_relative(name)


def test_changed_files_skip_inputs_and_unchanged(tmp_path: Path) -> None:
    (tmp_path / "scenario.yaml").write_text("a", encoding="utf-8")
    (tmp_path / INPUTS).mkdir()
    (tmp_path / INPUTS / "0-state.json").write_text("{}", encoding="utf-8")
    before = scan(tmp_path)
    assert set(before) == {"scenario.yaml"}  # 輸入檔不同步回去
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "shot.png").write_bytes(b"png")
    assert changed_files(before, scan(tmp_path)) == ["out/shot.png"]
    stamp = time.time_ns() + 5_000_000_000
    os.utime(tmp_path / "scenario.yaml", ns=(stamp, stamp))
    assert changed_files(before, scan(tmp_path)) == ["out/shot.png", "scenario.yaml"]


def test_pack_and_unpack_overwrite(tmp_path: Path) -> None:
    source, target = tmp_path / "device", tmp_path / "server"
    (source / "replay").mkdir(parents=True)
    (source / ".recording.py").write_text("page.goto('x')", encoding="utf-8")
    (source / "replay" / "a.png").write_bytes(b"\x89PNG")
    target.mkdir()
    (target / ".recording.py").write_text("old", encoding="utf-8")
    archive = tmp_path / "sync.zip"
    assert pack_files(source, [".recording.py", "replay/a.png", "gone.txt"], archive) == 2
    assert sorted(unpack_files(archive, target)) == [".recording.py", "replay/a.png"]
    assert (target / ".recording.py").read_text(encoding="utf-8") == "page.goto('x')"
    assert (target / "replay" / "a.png").read_bytes() == b"\x89PNG"
    assert not list(target.rglob("*.sync"))


@pytest.mark.parametrize("name", ["../escape.txt", f"{INPUTS}/x.json", "/abs.txt"])
def test_unpack_rejects_unsafe_entries(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("ok.txt", "fine")
        handle.writestr(name, "nope")
    target = tmp_path / "server"
    target.mkdir()
    with pytest.raises(SyncError):
        unpack_files(archive, target)
    assert list(target.iterdir()) == []  # 整個拒絕：連安全的那個也不寫


def test_unpack_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "server"
    target.mkdir()
    (target / "link").symlink_to(outside, target_is_directory=True)
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("link/evil.txt", "nope")
    with pytest.raises(SyncError):
        unpack_files(archive, target)
    assert list(outside.iterdir()) == []


def test_unpack_limits(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for index in range(MAX_SYNC_FILES + 1):
            handle.writestr(f"f{index}.txt", "")
    with pytest.raises(SyncError, match="too many"):
        unpack_files(archive, tmp_path / "server")
    (tmp_path / "not.zip").write_bytes(b"plain")
    with pytest.raises(SyncError, match="not a zip"):
        unpack_files(tmp_path / "not.zip", tmp_path / "server")


def test_unpack_rejects_before_writing_anything(tmp_path: Path) -> None:
    folder = tmp_path / "work"
    folder.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    archive = tmp_path / "sync.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("a.txt", "first")
        handle.writestr("link/escape.txt", "x")
    with pytest.raises(SyncError, match="unsafe path"):
        unpack_files(archive, folder)
    assert not (folder / "a.txt").exists()  # 第一個檔案也沒寫
    assert not (outside / "escape.txt").exists()

    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("out", "file")
        handle.writestr("out/shot.png", "png")
    with pytest.raises(SyncError, match="same name"):
        unpack_files(archive, folder)
    (folder / "shots").mkdir()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("shots", "file")
    with pytest.raises(SyncError, match="folder already"):
        unpack_files(archive, folder)
