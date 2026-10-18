"""RPA Worker App 的日誌（M10.1）：視窗程式沒有主控台，所有訊息寫到資料夾的 ``logs/``。

- ``logs/worker.log``，滿 1 MB 換一個檔案，保留 5 份。
- 寫入前遮掉邀請代碼與權杖（AGENTS.md：不把權杖寫進任何紀錄）。程式本身不記這些值，
  這裡是第二道防線：例如錯誤訊息裡帶到整行邀請。
"""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

__all__ = ["LOG_FILE", "RedactingFormatter", "redact", "setup_logging"]

LOG_FILE: Final = "worker.log"
_MAX_BYTES: Final = 1_000_000
_BACKUPS: Final = 5
_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MASK: Final = "•••"
_PATTERNS: Final = (
    re.compile(r"(?i)(code=)[A-Za-z0-9_-]{6,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r'(?i)("?token"?\s*[:=]\s*"?)[A-Za-z0-9._~+/=-]{6,}'),
)


def redact(text: str) -> str:
    """遮掉邀請代碼與權杖。"""
    for pattern in _PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + _MASK, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(folder: Path, *, file: Path | None = None) -> Path:
    """把 rpa 相關的日誌寫到檔案；回傳日誌檔的路徑。重複呼叫不會重複加處理器。"""
    path = file if file is not None else folder / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path:
            return path
    handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
    handler.setFormatter(RedactingFormatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return path
