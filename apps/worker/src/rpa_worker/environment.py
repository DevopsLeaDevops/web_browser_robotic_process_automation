"""這台電腦能做什麼：能不能顯示瀏覽器視窗、下載了哪些瀏覽器、程式版本的指紋（M9a）。
M10.1 加上 App 版本，管理 Portal 的裝置頁顯示。

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
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final

__all__ = [
    "FINGERPRINT_PACKAGES",
    "PROTOCOL",
    "WorkerInfo",
    "code_fingerprint",
    "external_url",
    "has_display",
    "installed_browsers",
    "lan_address",
    "package_version",
]

PROTOCOL: Final = 1
"""Worker API 的協定版本；管理 Portal 與 worker 不同時拒絕連線。"""

FINGERPRINT_PACKAGES: Final = ("rpa_core", "rpa_runner", "rpa_worker")
"""執行結果取決於這些套件的程式；指紋不同代表兩邊的程式不是同一版。"""

_ENGINES: Final = ("chromium", "firefox")


def package_version(distribution: str = "rpa-worker") -> str:
    """套件的版本（打包後的 App 也保留套件資訊）；查不到時回傳空字串。"""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return ""


def has_display(environ: Mapping[str, str] | None = None, platform_name: str | None = None) -> bool:
    """這台電腦能不能顯示瀏覽器視窗（有頭模式）。

    Windows 與 macOS 視為有桌面；其他系統要有 X11（DISPLAY）或 Wayland（WAYLAND_DISPLAY）。
    """
    env = os.environ if environ is None else environ
    system = sys.platform if platform_name is None else platform_name
    if system in ("win32", "darwin"):
        return True
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def lan_address() -> str | None:
    """這台電腦在區網上的位址（猜測，給遠端 worker 的 --server 用）。不會真的送出封包。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))  # 文件用的保留位址：只用來選出對外的網路介面
            address = str(probe.getsockname()[0])
    except OSError:
        return None
    return None if address.startswith("127.") or address == "0.0.0.0" else address


def external_url(host: str, port: int) -> str:
    """對外埠在區網上的網址（給 worker 與裝置邀請用）。

    綁定所有介面（0.0.0.0、::）時猜這台電腦的區網位址；綁定特定位址時就用那個位址。
    """
    if host in ("0.0.0.0", "::", ""):
        host = lan_address() or socket.gethostname()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # IPv6 位址在網址裡要加方括號
    return f"http://{host}:{port}"


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
    version: str = ""
    """App 的版本（M10.1）：命令列是 rpa-worker 套件的版本，桌面 App 是建置資訊裡的版本。"""

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
            version=package_version(),
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
            "version": self.version,
        }
