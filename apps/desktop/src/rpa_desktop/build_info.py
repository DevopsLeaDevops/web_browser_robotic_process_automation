"""建置資訊：哪個 App、版本、程式指紋、協定版本、提交、建置時間（M10，ADR 0014）。

打包後的 App 沒有原始碼檔案，算不出程式指紋（:func:`rpa_worker.environment.code_fingerprint`
讀的是套件裡的檔案），所以建置時先在開發環境算好，寫成 ``build_info.json`` 放進 App；
執行時讀它。開發環境沒有這個檔案，當場計算。
"""

import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Final, Literal, cast

from rpa_worker.environment import PROTOCOL, code_fingerprint

__all__ = ["APPS", "BUILD_INFO_FILE", "App", "BuildInfo", "current", "load", "write"]

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


def _bundled() -> Path:
    return Path(__file__).with_name(BUILD_INFO_FILE)


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
    path = _bundled()
    if getattr(sys, "frozen", False) and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return BuildInfo.from_json(cast("dict[str, object]", data))
    return current()


def write(path: Path, app: App, commit: str = "") -> BuildInfo:
    """建置時寫出 build_info.json（tools/build_desktop.py 呼叫）。"""
    info = current(app, commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(info.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return info
