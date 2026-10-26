"""建置資訊：哪個 App、版本、程式指紋、協定版本、提交、建置時間（M10，ADR 0014）。

打包後的 App 沒有原始碼檔案，算不出程式指紋（:func:`rpa_worker.environment.code_fingerprint`
讀的是套件裡的檔案），所以建置時先在開發環境算好，寫成 ``build_info.json`` 放進 App；
執行時讀它。開發環境沒有這個檔案，當場計算。

用更新檔裝的程式碼層時（ADR 0018），App 種類照舊來自 App 裡的檔案，版本、提交、程式指紋、
協定版本與建置時間改用那一層的清單。
"""

import json
import sys
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal, cast

from rpa_worker.environment import PROTOCOL, code_fingerprint

__all__ = ["APPS", "BUILD_INFO_FILE", "App", "BuildInfo", "current", "load", "shell_file", "write"]

type App = Literal["recorder", "worker", "development"]

APPS: Final = ("recorder", "worker")
"""可以打包的 App：RPA 錄製端、RPA Worker。"""
BUILD_INFO_FILE: Final = "build_info.json"
"""建置資訊在 App 裡的位置：rpa_desktop 套件資料夾內的這個檔案。"""


@dataclass(frozen=True, slots=True)
class BuildInfo:
    app: App
    version: str
    fingerprint: str
    protocol: int
    commit: str = ""
    built_at: str = ""

    def to_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "BuildInfo":
        app = str(data.get("app", "development"))
        return cls(
            app=app if app in (*APPS, "development") else "development",
            version=str(data.get("version", "")),
            fingerprint=str(data.get("fingerprint", "")),
            protocol=int(cast("int", data.get("protocol", 0))),
            commit=str(data.get("commit", "")),
            built_at=str(data.get("built_at", "")),
        )


def shell_file(name: str) -> Path:
    """建置時放進 App 的 rpa_desktop 資料夾裡的檔案（建置資訊、自我測試的範例場景）。

    打包後的 rpa_desktop 可能是從程式碼層載入的（ADR 0018），``__file__`` 不在 App 裡，
    所以用 App 自己的資料夾（``sys._MEIPASS``）；開發環境就是套件的資料夾。
    """
    base = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and isinstance(base, str):
        return Path(base) / "rpa_desktop" / name
    return Path(__file__).with_name(name)


def _with_layer(info: BuildInfo) -> BuildInfo:
    """用程式碼層時，版本與程式指紋改用那一層的清單。"""
    from rpa_update.layers import current_layer

    layer = current_layer()
    if layer is None:
        return info
    manifest = layer.manifest
    return replace(
        info,
        version=manifest.version,
        fingerprint=manifest.fingerprint,
        protocol=manifest.protocol,
        commit=manifest.commit,
        built_at=manifest.built_at,
    )


def current(app: App = "development", commit: str = "") -> BuildInfo:
    """以目前的原始碼計算建置資訊。"""
    return BuildInfo(
        app=app,
        version=version("rpa-desktop"),
        fingerprint=code_fingerprint(),
        protocol=PROTOCOL,
        commit=commit,
        built_at=datetime.now(UTC).isoformat(timespec="seconds") if app != "development" else "",
    )


def load() -> BuildInfo:
    """打包後讀 App 裡的 build_info.json；開發環境（或檔案不見時）當場計算。"""
    path = shell_file(BUILD_INFO_FILE)
    if getattr(sys, "frozen", False) and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _with_layer(BuildInfo.from_json(cast("dict[str, object]", data)))
    return current()


def write(path: Path, app: App, commit: str = "") -> BuildInfo:
    """建置時寫出 build_info.json（tools/build_desktop.py 呼叫）。"""
    info = current(app, commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(info.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return info
