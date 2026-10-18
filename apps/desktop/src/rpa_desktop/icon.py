"""RPA Worker 的圖示（M10.1）：用 Pillow 畫，倉庫裡不放二進位圖檔。

- 執行檔的圖示（``.ico``）：建置時 ``tools/build_desktop.py`` 呼叫 :func:`save_ico`。
- 通知區的圖示：執行時 :func:`draw` 畫，右下角的圓點表示狀態（綠：線上；黃：暫停；紅：離線或出錯）。

顏色取自設計系統（``docs/design-system/tokens.json``）：底色 ``--blue-strong``，狀態色
``--success``、``--warn``、``--danger``、``--muted``。
"""

from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

__all__ = ["ICO_SIZES", "STATUS_COLORS", "draw", "save_ico", "status_color"]

BACKGROUND: Final = "#0b69c4"
STATUS_COLORS: Final = {
    "online": "#248569",
    "paused": "#966516",
    "offline": "#b74643",
    "error": "#b74643",
    "idle": "#64758b",
}
ICO_SIZES: Final = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))
_CANVAS: Final = 256


def status_color(phase: str) -> str:
    """App 的狀態（controller 的 phase）→ 圓點的顏色。"""
    if phase == "online":
        return STATUS_COLORS["online"]
    if phase == "paused":
        return STATUS_COLORS["paused"]
    if phase in ("offline", "error", "unpaired"):
        return STATUS_COLORS["error"]
    return STATUS_COLORS["idle"]


def draw(size: int = 64, status: str | None = None) -> Image.Image:
    """畫出圖示：藍底圓角方塊裡一個瀏覽器視窗與播放鍵；``status`` 是圓點的顏色。"""
    image = Image.new("RGBA", (_CANVAS, _CANVAS), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((8, 8, 248, 248), radius=56, fill=BACKGROUND)
    line = 16
    pen.rounded_rectangle((52, 68, 204, 188), radius=16, outline="white", width=line)
    pen.line((52, 104, 204, 104), fill="white", width=line)
    pen.polygon(((112, 124), (112, 172), (152, 148)), fill="white")
    if status is not None:
        pen.ellipse((164, 164, 252, 252), fill="white")
        pen.ellipse((176, 176, 240, 240), fill=status)
    if size == _CANVAS:
        return image
    return image.resize((size, size), Image.Resampling.LANCZOS)


def save_ico(path: Path) -> Path:
    """寫出執行檔用的 ``.ico``（含 16～256 px 各尺寸）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    draw(_CANVAS).save(path, format="ICO", sizes=list(ICO_SIZES))
    return path
