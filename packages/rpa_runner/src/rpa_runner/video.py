"""錄影（M12，ADR 0016）：自動化階段的錄影、和步驟對時、存檔與修復。

- 子程序（child.py）開 BrowserContext 時加上 Playwright 的錄影，寫到執行目錄的 ``.video/``；
  開好頁面就用 :func:`mark_page` 記下影片檔名與開頁面的時間（讀不到影片標頭時用）。
  結束時先關 context：Playwright 這時才把影片寫完。
- 父程序（run.py）在執行結束後呼叫 :func:`finalize`：等影片寫完；沒有長度與索引（Cues）時——
  例如 Windows 上連 ffmpeg 一起被強制結束——用 Playwright 自帶的 ffmpeg 重新封裝（不重新編碼）；
  改名成 ``video.webm``，寫出 ``video.json``，刪掉 ``.video/``。
- 對時：Playwright 依每一格畫面的實際時間編碼，影片的第 t 秒 = 錄影開始時間 + t。開始時間在
  WebM 標頭（ffmpeg 的 creation_time → Segment Info 的 DateUTC），由 :func:`read_webm` 讀出；
  步驟在 steps.json 記下開始、結束的時間（UTC、毫秒），相減就是在影片裡的位置。
  舊版 Playwright 沒寫 DateUTC，就用開頁面的時間（誤差約幾十毫秒）。
- 畫面大小跟頁面一樣，寬度最多 1280（:func:`video_size`，使用者 2026-10-20 的決定 D2）。
"""

import contextlib
import os
import shutil
import struct
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Final, cast

import playwright
from playwright.sync_api import ViewportSize

from rpa_runner.commands import no_window_flags
from rpa_runner.files import VIDEO, VIDEO_INFO, VIDEO_TMP, read_json_or, write_json

__all__ = [
    "MAX_WIDTH",
    "VIDEO_INFO_VERSION",
    "VIDEO_STOP",
    "WebmInfo",
    "browsers_dir",
    "finalize",
    "find_ffmpeg",
    "mark_page",
    "read_info",
    "read_webm",
    "repair",
    "video_size",
]

VIDEO_INFO_VERSION: Final = 1
MAX_WIDTH: Final = 1280
"""錄影畫面的最大寬度；頁面更寬時等比例縮小。"""
_DEFAULT_VIEWPORT: Final[ViewportSize] = {"width": 1280, "height": 720}
"""場景沒有指定視窗大小時，Playwright 用的大小。"""
_PAGE_MARK: Final = "page.json"
VIDEO_STOP: Final = "stop.json"
"""錄影時被終止（取消、超過收尾時間）的經過：父程序寫在 ``.video/``，整理時放進 video.json。"""
_SETTLE_SECONDS: Final = 0.5
"""影片檔大小這麼久沒變，才當作寫完了。"""
_REPAIR_TIMEOUT: Final = 120.0


def video_size(viewport: ViewportSize | None) -> ViewportSize:
    """錄影的畫面大小：跟頁面一樣，寬度最多 1280（等比例縮小）；寬高是偶數（編碼器的要求）。"""
    view = viewport or _DEFAULT_VIEWPORT
    width, height = view["width"], view["height"]
    if width > MAX_WIDTH:
        height = round(height * MAX_WIDTH / width)
        width = MAX_WIDTH
    return {"width": max(2, width & ~1), "height": max(2, height & ~1)}


def mark_page(folder: Path, video: str | None, opened_at: float) -> None:
    """子程序開好頁面時記下影片檔名與時間（``.video/page.json``）；被強制終止也留得下來。"""
    (folder / VIDEO_TMP).mkdir(parents=True, exist_ok=True)
    write_json(
        folder / VIDEO_TMP / _PAGE_MARK,
        {"file": Path(video).name if video else None, "openedAt": opened_at},
    )


# ---------------------------------------------------------------- WebM 標頭

_EBML: Final = 0x1A45DFA3
_SEGMENT: Final = 0x18538067
_INFO: Final = 0x1549A966
_TIMECODE_SCALE: Final = 0x2AD7B1
_DURATION: Final = 0x4489
_DATE_UTC: Final = 0x4461
_TRACKS: Final = 0x1654AE6B
_TRACK_ENTRY: Final = 0xAE
_VIDEO_TRACK: Final = 0xE0
_PIXEL_WIDTH: Final = 0xB0
_PIXEL_HEIGHT: Final = 0xBA
_CLUSTER: Final = 0x1F43B675
_CLUSTER_TIMECODE: Final = 0xE7
_SIMPLE_BLOCK: Final = 0xA3
_BLOCK_GROUP: Final = 0xA0
_BLOCK: Final = 0xA1
_CUES: Final = 0x1C53BB6B
_UNKNOWN: Final = -1
"""長度未知的元素（直播格式，或寫到一半）。"""
_MATROSKA_EPOCH: Final = datetime(2001, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class WebmInfo:
    """WebM 標頭裡回看需要的資訊。"""

    started_at: datetime | None
    """錄影開始的實際時間（DateUTC）；舊版 Playwright 沒有寫。"""
    duration_ms: float | None
    width: int | None
    height: int | None
    first_frame_ms: float | None
    """第一格畫面的時間（毫秒，相對影片開頭）。"""
    cues: bool
    """有沒有索引（Cues）：沒有的話瀏覽器不能拖曳。"""

    @property
    def complete(self) -> bool:
        """正常收尾的檔案：有長度、有索引。"""
        return self.cues and bool(self.duration_ms)


def _vint(data: bytes, pos: int, *, marker: bool) -> tuple[int, int]:
    """EBML 的變長整數；``marker`` 時保留長度標記（元素代號的寫法）。回傳 (值, 下一個位置)。"""
    first = data[pos]
    length, mask = 1, 0x80
    while length <= 8 and not first & mask:
        length += 1
        mask >>= 1
    if length > 8 or pos + length > len(data):
        raise ValueError("bad EBML integer")
    value = first if marker else first & (mask - 1)
    for index in range(1, length):
        value = (value << 8) | data[pos + index]
    if not marker and value == (1 << (7 * length)) - 1:
        return _UNKNOWN, pos + length
    return value, pos + length


def _children(data: bytes) -> Iterator[tuple[int, bytes]]:
    """一段已讀進記憶體的元素內容裡的子元素：(代號, 內容)；遇到不完整的就停。"""
    pos = 0
    while pos < len(data):
        try:
            element, pos = _vint(data, pos, marker=True)
            size, pos = _vint(data, pos, marker=False)
        except (ValueError, IndexError):
            return
        if size == _UNKNOWN:
            size = len(data) - pos
        yield element, data[pos : pos + size]
        pos += size


def _header(file: BinaryIO, offset: int) -> tuple[int, int, int] | None:
    """檔案中 offset 處的元素：(代號, 內容開始的位置, 內容長度)；讀不到時回傳 None。"""
    file.seek(offset)
    head = file.read(12)
    try:
        element, pos = _vint(head, 0, marker=True)
        size, pos = _vint(head, pos, marker=False)
    except (ValueError, IndexError):
        return None
    return element, offset + pos, size


def _uint(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _float(data: bytes) -> float | None:
    if len(data) == 4:
        return struct.unpack(">f", data)[0]
    if len(data) == 8:
        return struct.unpack(">d", data)[0]
    return None


def _first_block(cluster: bytes) -> int | None:
    """叢集裡第一格畫面的時間（叢集時間＋區塊的相對時間，單位是 TimecodeScale）。"""
    timecode: int | None = None
    for element, data in _children(cluster):
        if element == _CLUSTER_TIMECODE:
            timecode = _uint(data)
        elif element in (_SIMPLE_BLOCK, _BLOCK_GROUP) and timecode is not None:
            block = data
            if element == _BLOCK_GROUP:
                block = next((part for kind, part in _children(data) if kind == _BLOCK), b"")
            try:
                _, pos = _vint(block, 0, marker=False)  # 軌道編號
            except (ValueError, IndexError):
                return None
            if pos + 2 > len(block):
                return None
            return timecode + struct.unpack(">h", block[pos : pos + 2])[0]
    return None


def read_webm(path: Path) -> WebmInfo | None:
    """讀 WebM 標頭（只讀需要的部分）；不是 WebM 或讀不到時回傳 None。"""
    try:
        size = path.stat().st_size
        file = path.open("rb")
    except OSError:
        return None
    with file:
        head = _header(file, 0)
        if head is None or head[0] != _EBML or head[2] == _UNKNOWN:
            return None
        segment = _header(file, head[1] + head[2])
        if segment is None or segment[0] != _SEGMENT:
            return None
        end = size if segment[2] == _UNKNOWN else min(size, segment[1] + segment[2])
        scale = 1_000_000
        duration: float | None = None
        started: datetime | None = None
        width: int | None = None
        height: int | None = None
        first: int | None = None
        cues = False
        offset = segment[1]
        while offset < end:
            item = _header(file, offset)
            if item is None:
                break
            element, body, length = item
            complete = length != _UNKNOWN and body + length <= size
            if element in (_INFO, _TRACKS) and complete:
                file.seek(body)
                data = file.read(length)
                for child, value in _children(data):
                    if child == _TIMECODE_SCALE:
                        scale = _uint(value) or scale
                    elif child == _DURATION:
                        duration = _float(value)
                    elif child == _DATE_UTC and len(value) == 8:
                        nanoseconds: int = struct.unpack(">q", value)[0]
                        started = _MATROSKA_EPOCH + timedelta(microseconds=nanoseconds // 1000)
                    elif child == _TRACK_ENTRY:
                        for part, video in _children(value):
                            if part == _VIDEO_TRACK:
                                for key, number in _children(video):
                                    if key == _PIXEL_WIDTH:
                                        width = _uint(number)
                                    elif key == _PIXEL_HEIGHT:
                                        height = _uint(number)
            elif element == _CLUSTER and first is None:
                file.seek(body)
                first = _first_block(file.read(min(size - body, 64 * 1024)))
            elif element == _CUES and complete:
                cues = True
            if not complete:
                break
            offset = body + length
    to_ms = scale / 1_000_000
    return WebmInfo(
        started_at=started,
        duration_ms=duration * to_ms if duration else None,
        width=width,
        height=height,
        first_frame_ms=first * to_ms if first is not None else None,
        cues=cues,
    )


# ---------------------------------------------------------------- ffmpeg 與修復


def browsers_dir(environ: Mapping[str, str] = os.environ, platform: str = sys.platform) -> Path:
    """Playwright 下載瀏覽器（和 ffmpeg）的位置：``PLAYWRIGHT_BROWSERS_PATH`` 或各系統預設的。"""
    custom = environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if custom == "0":
        return Path(playwright.__file__).parent / "driver" / "package" / ".local-browsers"
    if custom:
        return Path(custom).expanduser()
    home = Path(environ.get("USERPROFILE") or environ.get("HOME") or Path.home())
    if platform == "win32":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "ms-playwright"
    if platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    return Path(environ.get("XDG_CACHE_HOME") or home / ".cache") / "ms-playwright"


def _revision(folder: Path) -> int:
    tail = folder.name.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else -1


def find_ffmpeg(environ: Mapping[str, str] = os.environ) -> Path | None:
    """Playwright 下載的 ffmpeg（下載任何瀏覽器都會一起下載）；找不到時用 PATH 上的 ffmpeg。"""
    root = browsers_dir(environ)
    with contextlib.suppress(OSError):
        for folder in sorted(root.glob("ffmpeg-*"), key=_revision, reverse=True):
            for name in ("ffmpeg-win64.exe", "ffmpeg-mac", "ffmpeg-linux", "ffmpeg.exe", "ffmpeg"):
                candidate = folder / name
                if candidate.is_file():
                    return candidate
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def repair(path: Path, ffmpeg: Path | None = None, *, timeout: float = _REPAIR_TIMEOUT) -> bool:
    """重新封裝（不重新編碼）：補上長度與索引，讓瀏覽器能拖曳。成功時取代原檔並回傳 True。"""
    tool = ffmpeg or find_ffmpeg()
    if tool is None:
        return False
    fixed = path.with_name(path.stem + ".fixed.webm")
    command = [str(tool), "-v", "error", "-y", "-i", str(path), "-c", "copy", str(fixed)]
    try:
        done = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            creationflags=no_window_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        fixed.unlink(missing_ok=True)
        return False
    info = read_webm(fixed) if done.returncode == 0 else None
    if info is None or not info.complete:
        fixed.unlink(missing_ok=True)
        return False
    try:
        fixed.replace(path)
    except OSError:
        fixed.unlink(missing_ok=True)
        return False
    return True


# ---------------------------------------------------------------- 整理


def _settle(path: Path, timeout: float) -> None:
    """等檔案寫完：大小有一陣子沒變（最多等 timeout 秒）。"""
    ends = time.monotonic() + timeout
    last = -1
    since: float | None = None
    while time.monotonic() < ends:
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        if size == last and size > 0:
            since = since if since is not None else time.monotonic()
            if time.monotonic() - since >= _SETTLE_SECONDS:
                return
        else:
            since = None
            last = size
        time.sleep(0.1)


def _move(source: Path, target: Path, *, timeout: float) -> bool:
    """改名；Windows 上剛被結束的程序可能還占著檔案（WinError 32），稍等重試。"""
    ends = time.monotonic() + timeout
    while True:
        try:
            source.replace(target)
        except PermissionError:
            if time.monotonic() >= ends:
                return False
            time.sleep(0.1)
        except OSError:
            return False
        else:
            return True


def _remove_tree(folder: Path, *, timeout: float = 3.0) -> None:
    ends = time.monotonic() + timeout
    while folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists() or time.monotonic() >= ends:
            return
        time.sleep(0.1)


def _iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _chosen(temp: Path, mark: Mapping[str, object]) -> Path | None:
    """主要頁面的影片（page.json 記下的）；沒有記到時用最大的那一個。"""
    name = mark.get("file")
    if isinstance(name, str) and (temp / name).is_file():
        return temp / name
    videos = [path for path in temp.glob("*.webm") if path.is_file()]
    return max(videos, key=lambda path: path.stat().st_size) if videos else None


def finalize(
    folder: Path, *, engine: str | None = None, wait_seconds: float = 10.0
) -> dict[str, object] | None:
    """整理錄影：``.video/`` → ``video.webm`` 與 ``video.json``；沒有錄影時回傳 None。

    回傳 video.json 的內容。影片讀不到或是空的（例如瀏覽器還沒開就被取消）時，
    video.json 只記下 ``error``，沒有 ``file``。
    """
    temp = folder / VIDEO_TMP
    if not temp.is_dir():
        return None
    try:
        raw = read_json_or(temp / _PAGE_MARK, {})
        mark = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
        details: dict[str, object] = {"version": VIDEO_INFO_VERSION, "file": None, "engine": engine}
        stop = read_json_or(temp / VIDEO_STOP, None)
        if isinstance(stop, dict):
            details["stop"] = stop
        source = _chosen(temp, mark)
        if source is None:
            details["error"] = "no_video"
        else:
            info = read_webm(source)
            if info is None or not info.complete:
                _settle(source, wait_seconds)
                info = read_webm(source)
            repaired = False
            if info is None or not info.complete:
                repaired = repair(source)
                if repaired:
                    info = read_webm(source)
            if info is None:
                details["error"] = "unreadable"
                with contextlib.suppress(OSError):
                    details["bytes"] = source.stat().st_size
            elif not _move(source, folder / VIDEO, timeout=wait_seconds):
                details["error"] = "locked"
            else:
                opened = mark.get("openedAt")
                fallback = (
                    datetime.fromtimestamp(opened, UTC)
                    if isinstance(opened, int | float) and not isinstance(opened, bool)
                    else None
                )
                details.update(
                    file=VIDEO,
                    startedAt=_iso(info.started_at or fallback),
                    startedAtSource="file" if info.started_at is not None else "page",
                    durationMs=round(info.duration_ms) if info.duration_ms else None,
                    firstFrameMs=round(info.first_frame_ms)
                    if info.first_frame_ms is not None
                    else None,
                    width=info.width,
                    height=info.height,
                    bytes=(folder / VIDEO).stat().st_size,
                    complete=info.complete,
                    repaired=repaired,
                )
        write_json(folder / VIDEO_INFO, details)
        return details
    finally:
        _remove_tree(temp)


def read_info(folder: Path) -> dict[str, object] | None:
    """執行目錄的 video.json；沒有或內容不對時回傳 None。"""
    raw = read_json_or(folder / VIDEO_INFO, None)
    return cast("dict[str, object]", raw) if isinstance(raw, dict) else None
