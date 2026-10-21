"""錄影的整理（M12）：畫面大小、WebM 標頭、ffmpeg 的位置、修復、整理成 video.webm 與 video.json。

不需要瀏覽器；真實錄影在 test_video_browser.py。
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rpa_runner import video
from rpa_runner.files import VIDEO, VIDEO_INFO, VIDEO_TMP
from rpa_runner.proctree import ProcessInfo, descendants
from rpa_runner.video import (
    browsers_dir,
    finalize,
    find_ffmpeg,
    mark_page,
    read_info,
    read_webm,
    video_size,
)
from testsite.webm import tiny_webm

STARTED = datetime(2026, 10, 21, 3, 30, 12, 41000, tzinfo=UTC)


@pytest.mark.parametrize(
    ("viewport", "expected"),
    [
        (None, {"width": 1280, "height": 720}),
        ({"width": 1280, "height": 800}, {"width": 1280, "height": 800}),
        ({"width": 1920, "height": 1080}, {"width": 1280, "height": 720}),
        ({"width": 2560, "height": 1601}, {"width": 1280, "height": 800}),
        ({"width": 801, "height": 451}, {"width": 800, "height": 450}),
    ],
)
def test_video_size_follows_the_page_up_to_1280_wide(
    viewport: dict[str, int] | None, expected: dict[str, int]
) -> None:
    assert video_size(viewport) == expected  # pyright: ignore[reportArgumentType]


def test_read_webm_finished_file(tmp_path: Path) -> None:
    path = tmp_path / "a.webm"
    path.write_bytes(tiny_webm(duration_ms=2500, started_at=STARTED, width=640, height=360))

    info = read_webm(path)

    assert info is not None
    assert info.started_at == STARTED
    assert info.duration_ms == 2500
    assert (info.width, info.height) == (640, 360)
    assert info.first_frame_ms == 40
    assert info.cues
    assert info.complete


def test_read_webm_cut_off_file(tmp_path: Path) -> None:
    path = tmp_path / "a.webm"
    path.write_bytes(tiny_webm(finished=False, started_at=STARTED))

    info = read_webm(path)

    assert info is not None
    assert info.started_at == STARTED  # 標頭在開頭，被終止也讀得到
    assert info.duration_ms is None
    assert not info.cues
    assert not info.complete


@pytest.mark.parametrize("content", [b"", b"not a webm", b"\x1a\x45\xdf\xa3\x81"])
def test_read_webm_rejects_other_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "a.webm"
    path.write_bytes(content)
    assert read_webm(path) is None
    assert read_webm(tmp_path / "missing.webm") is None


def test_browsers_dir_follows_playwright() -> None:
    assert browsers_dir({"PLAYWRIGHT_BROWSERS_PATH": "/opt/pw"}, "linux") == Path("/opt/pw")
    assert browsers_dir({"HOME": "/home/u"}, "linux") == Path("/home/u/.cache/ms-playwright")
    assert browsers_dir({"HOME": "/home/u", "XDG_CACHE_HOME": "/c"}, "linux") == Path(
        "/c/ms-playwright"
    )
    assert browsers_dir({"HOME": "/Users/u"}, "darwin") == Path(
        "/Users/u/Library/Caches/ms-playwright"
    )
    assert browsers_dir({"LOCALAPPDATA": "C:/Users/u/AppData/Local"}, "win32") == Path(
        "C:/Users/u/AppData/Local/ms-playwright"
    )
    assert browsers_dir({"PLAYWRIGHT_BROWSERS_PATH": "0"}).name == ".local-browsers"


def test_find_ffmpeg_prefers_the_newest_playwright_download(tmp_path: Path) -> None:
    for folder, name in (("ffmpeg-1011", "ffmpeg-linux"), ("ffmpeg-1013", "ffmpeg-win64.exe")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / name).write_bytes(b"")
    (tmp_path / "chromium-1248").mkdir()

    found = find_ffmpeg({"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path), "PATH": ""})

    assert found == tmp_path / "ffmpeg-1013" / "ffmpeg-win64.exe"


def _recorded(folder: Path, content: bytes, *, name: str = "page1.webm") -> None:
    mark_page(folder, f"/somewhere/{name}", STARTED.timestamp())
    (folder / VIDEO_TMP / name).write_bytes(content)


def test_finalize_moves_the_video_and_describes_it(tmp_path: Path) -> None:
    _recorded(tmp_path, tiny_webm(duration_ms=3200, started_at=STARTED, width=1280, height=720))
    # 其他頁面（彈出視窗）的影片不留
    (tmp_path / VIDEO_TMP / "popup.webm").write_bytes(tiny_webm())

    details = finalize(tmp_path, engine="chromium")

    assert details == read_info(tmp_path)
    assert details == {
        "version": 1,
        "file": VIDEO,
        "engine": "chromium",
        "startedAt": "2026-10-21T03:30:12.041Z",
        "startedAtSource": "file",
        "durationMs": 3200,
        "firstFrameMs": 40,
        "width": 1280,
        "height": 720,
        "bytes": (tmp_path / VIDEO).stat().st_size,
        "complete": True,
        "repaired": False,
    }
    assert not (tmp_path / VIDEO_TMP).exists()


def test_finalize_uses_the_page_time_when_the_file_has_none(tmp_path: Path) -> None:
    _recorded(tmp_path, tiny_webm(started_at=None))

    details = finalize(tmp_path)

    assert details is not None
    assert details["startedAt"] == "2026-10-21T03:30:12.041Z"
    assert details["startedAtSource"] == "page"


def test_finalize_repairs_a_cut_off_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _recorded(tmp_path, tiny_webm(finished=False, started_at=STARTED))
    calls: list[Path] = []

    def fake_repair(path: Path, ffmpeg: Path | None = None, *, timeout: float = 0) -> bool:
        calls.append(path)
        path.write_bytes(tiny_webm(duration_ms=900, started_at=STARTED))
        return True

    monkeypatch.setattr(video, "repair", fake_repair)

    details = finalize(tmp_path, wait_seconds=0.6)

    assert details is not None
    assert len(calls) == 1
    assert details["repaired"] is True
    assert details["complete"] is True
    assert details["durationMs"] == 900


def _cannot_repair(*args: object, **kwargs: object) -> bool:
    return False


def test_finalize_keeps_a_video_that_cannot_be_repaired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """修不了（例如找不到 ffmpeg）也留著：瀏覽器還是能從頭播放，只是不能拖曳。"""
    _recorded(tmp_path, tiny_webm(finished=False, started_at=STARTED))
    monkeypatch.setattr(video, "repair", _cannot_repair)

    details = finalize(tmp_path, wait_seconds=0.6)

    assert details is not None
    assert details["file"] == VIDEO
    assert details["complete"] is False
    assert details["repaired"] is False
    assert (tmp_path / VIDEO).is_file()


@pytest.mark.parametrize(("content", "error"), [(None, "no_video"), (b"", "unreadable")])
def test_finalize_without_a_usable_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes | None, error: str
) -> None:
    mark_page(tmp_path, None, STARTED.timestamp())
    if content is not None:
        (tmp_path / VIDEO_TMP / "page1.webm").write_bytes(content)
    monkeypatch.setattr(video, "repair", _cannot_repair)

    details = finalize(tmp_path, wait_seconds=0.6)

    assert details == {"version": 1, "file": None, "engine": None, "error": error}
    assert json.loads((tmp_path / VIDEO_INFO).read_text(encoding="utf-8")) == details
    assert not (tmp_path / VIDEO).exists()
    assert not (tmp_path / VIDEO_TMP).exists()


def test_finalize_without_recording(tmp_path: Path) -> None:
    assert finalize(tmp_path) is None
    assert not (tmp_path / VIDEO_INFO).exists()


def test_descendants_walks_the_process_tree() -> None:
    processes = [
        ProcessInfo(4, 0, "System"),
        ProcessInfo(0, 0, "Idle"),
        ProcessInfo(100, 50, "python.exe"),
        ProcessInfo(101, 100, "node.exe"),
        ProcessInfo(102, 101, "chrome.exe"),
        ProcessInfo(103, 102, "chrome.exe"),
        ProcessInfo(104, 101, "ffmpeg-win64.exe"),
        ProcessInfo(200, 50, "other.exe"),
    ]

    found = descendants(100, processes)

    assert [item.pid for item in found] == [101, 102, 104, 103]
    assert descendants(999, processes) == []
