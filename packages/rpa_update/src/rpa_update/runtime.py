"""執行環境（ADR 0018）：哪一種 App、哪個平台、環境代號、信任的公鑰。

完整的安裝包（伺服器分發包、桌面 App）建置時寫出 ``rpa_update/runtime.json``；開發環境
（``uv run``）沒有這個檔案，不能套用更新檔。

環境代號是程式碼層能不能在這個執行環境上跑的判斷：Python 的主、次版本、執行時需要的第三方
套件與版本、外殼（PyInstaller）的版本與收進去的模組、rpa_update 自己的原始碼。建置工具把
這些放進 ``components``，代號是它們的雜湊；更新檔的清單寫出每個平台需要的代號，相同才套用。
"""

import base64
import binascii
import hashlib
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Final, cast

from rpa_update.errors import UpdateError

__all__ = [
    "FORMAT",
    "KINDS",
    "PLATFORMS",
    "RUNTIME_FILE",
    "Runtime",
    "load_runtime",
    "platform_tag",
    "runtime_id",
    "source_digest",
    "target_name",
]

RUNTIME_FILE: Final = "runtime.json"
FORMAT: Final = 1
KINDS: Final = ("server", "worker", "recorder")
PLATFORMS: Final = ("linux-x64", "linux-arm64", "windows-x64", "macos-arm64")
_MACHINES: Final = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
_SYSTEMS: Final = {"linux": "linux", "win32": "windows", "darwin": "macos"}


def platform_tag(system: str | None = None, machine: str | None = None) -> str:
    """這台電腦的平台：``linux-x64``、``windows-x64``、``macos-arm64`` 之類。"""
    name = _SYSTEMS.get(sys.platform if system is None else system, system or sys.platform)
    arch = (platform.machine() if machine is None else machine).lower()
    return f"{name}-{_MACHINES.get(arch, arch)}"


def target_name(kind: str, platform_name: str | None = None) -> str:
    """清單裡的目標：App 的種類加平台，例如 ``server-linux-x64``、``worker-windows-x64``。"""
    return f"{kind}-{platform_tag() if platform_name is None else platform_name}"


def runtime_id(components: Mapping[str, object]) -> str:
    """環境代號：``components`` 排序後的 JSON 的 SHA-256 前 16 個十六進位字元。"""
    canonical = json.dumps(components, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:16]


def source_digest(root: Path | None = None) -> str:
    """rpa_update 原始碼的雜湊（不含 runtime.json 與 .pyc）；換行統一成 LF。

    rpa_update 跟著執行環境走：它一改，環境代號就跟著改，要發完整的安裝包。
    """
    base = Path(__file__).resolve().parent if root is None else root
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(base).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Runtime:
    """一個完整安裝包的執行環境。"""

    target: str
    """``server-linux-x64`` 之類（:func:`target_name`）。"""
    id: str
    """環境代號（:func:`runtime_id`）。"""
    keys: tuple[bytes, ...]
    """信任的 Ed25519 公鑰（每把 32 位元組）。"""
    components: Mapping[str, object] = field(default_factory=dict[str, object])
    """算出代號的內容，只用來排查問題。"""

    def to_json(self) -> dict[str, object]:
        return {
            "format": FORMAT,
            "target": self.target,
            "id": self.id,
            "keys": [base64.b64encode(key).decode("ascii") for key in self.keys],
            "components": dict(self.components),
        }

    @classmethod
    def from_json(cls, data: object) -> "Runtime":
        if not isinstance(data, dict):
            raise UpdateError("runtime_invalid")
        values = cast("dict[str, object]", data)
        target, ident, keys = values.get("target"), values.get("id"), values.get("keys")
        components = values.get("components", {})
        if (
            values.get("format") != FORMAT
            or not isinstance(target, str)
            or not isinstance(ident, str)
            or not isinstance(keys, list)
            or not isinstance(components, dict)
        ):
            raise UpdateError("runtime_invalid")
        return cls(
            target=target,
            id=ident,
            keys=_decode_keys(cast("list[object]", keys)),
            components=cast("dict[str, object]", components),
        )


def _decode_keys(values: Sequence[object]) -> tuple[bytes, ...]:
    keys: list[bytes] = []
    for value in values:
        if not isinstance(value, str):
            raise UpdateError("runtime_invalid")
        try:
            key = base64.b64decode(value, validate=True)
        except binascii.Error:
            raise UpdateError("runtime_invalid") from None
        if len(key) != 32:
            raise UpdateError("runtime_invalid")
        keys.append(key)
    return tuple(keys)


def load_runtime(path: Path | None = None) -> Runtime | None:
    """讀取這個安裝包的 runtime.json；開發環境沒有這個檔案時回傳 None。"""
    try:
        text = (
            files("rpa_update").joinpath(RUNTIME_FILE).read_text(encoding="utf-8")
            if path is None
            else path.read_text(encoding="utf-8")
        )
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise UpdateError("runtime_unreadable", error=error) from None
    try:
        data = json.loads(text)
    except ValueError:
        raise UpdateError("runtime_invalid") from None
    return Runtime.from_json(data)
