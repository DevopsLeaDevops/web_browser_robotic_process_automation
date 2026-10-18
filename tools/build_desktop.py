"""建置桌面 App（M10，ADR 0014）：寫出建置資訊、執行 PyInstaller、打包成可以下載的檔案。

    uv sync --locked --group desktop-build
    uv run python tools/build_desktop.py recorder   # macOS：dist/desktop/RPA Recorder.app 與 DMG
    uv run python tools/build_desktop.py worker     # Windows：dist/desktop/rpa-worker/ 與 zip

產物都在 dist/desktop/，中間檔在 build/desktop/（兩者都在 .gitignore）。最後印出三行：
``executable: …``（App 的執行檔）、``child: …``（同資料夾的 rpa-child，主控台程式：
``--version``、``--self-test`` 要讀輸出時用；RPA Worker 是視窗程式，沒有標準輸出）與
``artifact: …``（要上傳的檔案）；在 GitHub Actions 裡同時寫進步驟的輸出。
RPA Worker 的執行檔圖示在建置時由 ``rpa_desktop.icon`` 畫出（倉庫不放二進位圖檔）。

M10.0 的 Windows 產物是 zip，M10.1 改成 Inno Setup 的安裝檔；設定見 apps/desktop/packaging/。
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final, cast

from rpa_desktop.build_info import APPS, App, write

ROOT: Final = Path(__file__).resolve().parent.parent
SPEC: Final = ROOT / "apps" / "desktop" / "packaging" / "rpa_desktop.spec"
DIST: Final = ROOT / "dist" / "desktop"
WORK: Final = ROOT / "build" / "desktop"

EXECUTABLES: Final = {"recorder": "rpa-recorder", "worker": "rpa-worker"}
BUNDLES: Final = {"recorder": "RPA Recorder", "worker": "RPA Worker"}
"""macOS 的 .app 名稱（也是 DMG 的磁碟名稱）。"""
FILES: Final = {"recorder": "RPA-Recorder", "worker": "RPA-Worker"}
"""下載檔的檔名開頭。"""


def _commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _platform_tag() -> str:
    system = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), platform.system())
    machine = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64")
    return f"{system.lower()}-{machine}"


def executable(app: App) -> Path:
    """建好之後 App 執行檔的位置。"""
    name = EXECUTABLES[app]
    if sys.platform == "darwin":
        return DIST / f"{BUNDLES[app]}.app" / "Contents" / "MacOS" / name
    return DIST / name / (name + (".exe" if os.name == "nt" else ""))


def child(app: App) -> Path:
    """建好之後同資料夾的 rpa-child（子程序與要讀輸出的命令用的主控台程式）。"""
    return executable(app).with_name("rpa-child" + (".exe" if os.name == "nt" else ""))


def _icon(app: App) -> Path | None:
    """Windows 的執行檔圖示（.ico）。"""
    if os.name != "nt" or app != "worker":
        return None
    from rpa_desktop.icon import save_ico

    return save_ico(WORK / app / f"{EXECUTABLES[app]}.ico")


def _dmg(app: App, version: str) -> Path:
    """把 .app 和指向「應用程式」的捷徑放進 DMG，打開後拖過去就安裝好。"""
    bundle = DIST / f"{BUNDLES[app]}.app"
    staging = WORK / app / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    shutil.copytree(bundle, staging / bundle.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    image = DIST / f"{FILES[app]}-{version}-{_platform_tag()}.dmg"
    image.unlink(missing_ok=True)
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            BUNDLES[app],
            "-srcfolder",
            str(staging),
            "-format",
            "UDZO",
            str(image),
        ],
        check=True,
    )
    return image


def _zip(app: App, version: str) -> Path:
    base = DIST / f"{FILES[app]}-{version}-{_platform_tag()}"
    return Path(shutil.make_archive(str(base), "zip", root_dir=DIST, base_dir=EXECUTABLES[app]))


def build(app: App) -> tuple[Path, Path]:
    """建置一個 App，回傳 (執行檔, 要上傳的檔案)。"""
    info_path = WORK / app / "build_info.json"
    info = write(info_path, app, _commit())
    env = {
        **os.environ,
        "RPA_DESKTOP_APP": app,
        "RPA_DESKTOP_INFO": str(info_path),
        "RPA_DESKTOP_VERSION": info.version,
    }
    icon = _icon(app)
    if icon is not None:
        env["RPA_DESKTOP_ICON"] = str(icon)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(WORK / app / "pyinstaller"),
            str(SPEC),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    artifact = _dmg(app, info.version) if sys.platform == "darwin" else _zip(app, info.version)
    return executable(app), artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建置 RPA 錄製端或 RPA Worker")
    parser.add_argument("app", choices=APPS)
    args = parser.parse_args(argv)
    built, artifact = build(cast("App", args.app))
    # 用正斜線：Windows 上的 bash 與 PowerShell 都看得懂
    lines = {
        "executable": built.as_posix(),
        "child": child(cast("App", args.app)).as_posix(),
        "artifact": artifact.as_posix(),
    }
    for key, value in lines.items():
        print(f"{key}: {value}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in lines.items())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
