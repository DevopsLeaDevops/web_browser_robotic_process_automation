"""這台電腦能做什麼：能不能顯示瀏覽器視窗、下載了哪些瀏覽器、程式版本的指紋（M9a）。

遠端 worker 上線時把這些告訴管理 Portal，Portal 只把它能跑的任務交給它；
管理 Portal 自己（本機 worker）也用同一套判斷。
"""

import hashlib
import os
import platform
import socket
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Final

__all__ = [
    "FINGERPRINT_PACKAGES",
    "PROTOCOL",
    "WorkerInfo",
    "code_fingerprint",
    "has_display",
    "installed_browsers",
]

PROTOCOL: Final = 1
"""Worker API 的協定版本；管理 Portal 與 worker 不同時拒絕連線。"""

FINGERPRINT_PACKAGES: Final = ("rpa_core", "rpa_runner", "rpa_worker")
"""執行結果取決於這些套件的程式；指紋不同代表兩邊的程式不是同一版。"""

_ENGINES: Final = ("chromium", "firefox")


def has_display(environ: Mapping[str, str] | None = None, platform_name: str | None = None) -> bool:
    """這台電腦能不能顯示瀏覽器視窗（有頭模式）。

    Windows 與 macOS 視為有桌面；其他系統要有 X11（DISPLAY）或 Wayland（WAYLAND_DISPLAY）。
    """
    env = os.environ if environ is None else environ
    system = sys.platform if platform_name is None else platform_name
    if system in ("win32", "darwin"):
        return True
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def installed_browsers(engines: Sequence[str] = _ENGINES) -> list[str]:
    """已經下載的瀏覽器（不啟動瀏覽器；判斷不了時當作都有）。"""
    from rpa_runner.installed import missing_browsers

    missing = set(missing_browsers(engines))
    return [engine for engine in engines if engine not in missing]


def _package_files(name: str) -> list[tuple[str, Path]]:
    module = import_module(name)
    root = Path(module.__file__ or "").parent
    files = [
        (f"{name}/{path.relative_to(root).as_posix()}", path)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    return sorted(files)


def code_fingerprint(packages: Sequence[str] = FINGERPRINT_PACKAGES) -> str:
    """程式版本的指紋：套件裡所有檔案的雜湊（換行統一成 LF，Windows 的 git 轉成 CRLF 也一樣）。"""
    digest = hashlib.sha256()
    for package in packages:
        for relative, path in _package_files(package):
            digest.update(relative.encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class WorkerInfo:
    """worker 上線時告訴管理 Portal 的資訊。"""

    name: str
    protocol: int = PROTOCOL
    fingerprint: str = ""
    os: str = ""
    python: str = ""
    host: str = ""
    browsers: tuple[str, ...] = ()
    display: bool = False

    @classmethod
    def detect(cls, name: str | None = None) -> "WorkerInfo":
        host = socket.gethostname()
        return cls(
            name=name or host,
            fingerprint=code_fingerprint(),
            os=f"{platform.system()} {platform.release()}".strip(),
            python=platform.python_version(),
            host=host,
            browsers=tuple(installed_browsers()),
            display=has_display(),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "fingerprint": self.fingerprint,
            "os": self.os,
            "python": self.python,
            "host": self.host,
            "browsers": list(self.browsers),
            "display": self.display,
        }
