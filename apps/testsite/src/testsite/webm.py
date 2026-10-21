"""測試用的最小 WebM（M12）：只有 rpa_runner.video 讀的那幾個標頭，沒有真正的畫面。

給錄影的單元測試與伺服器的測試用，不需要瀏覽器與 ffmpeg。
"""

import struct
from datetime import UTC, datetime

__all__ = ["tiny_webm"]

_MATROSKA_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
_UNKNOWN_SIZE = b"\x01\xff\xff\xff\xff\xff\xff\xff"


def _id(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def _element(element: int, payload: bytes, *, unknown_size: bool = False) -> bytes:
    size = _UNKNOWN_SIZE if unknown_size else b"\x01" + len(payload).to_bytes(7, "big")
    return _id(element) + size + payload


def _uint(element: int, value: int) -> bytes:
    return _element(element, value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big"))


def tiny_webm(
    *,
    duration_ms: float | None = 1500.0,
    started_at: datetime | None = None,
    width: int = 320,
    height: int = 180,
    first_frame_ms: int = 40,
    cues: bool = True,
    finished: bool = True,
) -> bytes:
    """``finished=False`` 模擬寫到一半被終止：Segment 長度未知、沒有長度也沒有索引。"""
    info = _uint(0x2AD7B1, 1_000_000)
    if duration_ms is not None and finished:
        info += _element(0x4489, struct.pack(">d", duration_ms))
    if started_at is not None:
        nanoseconds = int((started_at - _MATROSKA_EPOCH).total_seconds() * 1_000_000) * 1000
        info += _element(0x4461, struct.pack(">q", nanoseconds))
    video = _uint(0xB0, width) + _uint(0xBA, height)
    tracks = _element(0xAE, _uint(0xD7, 1) + _element(0xE0, video))
    block = b"\x81" + struct.pack(">h", first_frame_ms) + b"\x80" + bytes(16)
    cluster = _element(0x1F43B675, _uint(0xE7, 0) + _element(0xA3, block))
    body = _element(0x1549A966, info) + _element(0x1654AE6B, tracks) + cluster
    if cues and finished:
        body += _element(0x1C53BB6B, _element(0xBB, _uint(0xB3, 0)))
    header = _element(0x1A45DFA3, _element(0x4282, b"webm"))
    return header + _element(0x18538067, body, unknown_size=not finished)
