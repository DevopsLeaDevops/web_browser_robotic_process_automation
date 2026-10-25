"""建置桌面 App（M10，ADR 0014）：寫出建置資訊、執行 PyInstaller、打包成可以下載的檔案。

    uv sync --locked --group desktop-build
    uv run python tools/build_desktop.py recorder   # macOS：dist/desktop/RPA Recorder.app 與 DMG
    uv run python tools/build_desktop.py worker     # Windows：rpa-worker/、zip 與安裝檔
                                                    # macOS：dist/desktop/RPA Worker.app 與 DMG

產物都在 dist/desktop/，中間檔在 build/desktop/（兩者都在 .gitignore）。最後印出：
``executable: …``（App 的執行檔）、``child: …``（同資料夾的 rpa-child，主控台程式：
``--version``、``--self-test`` 要讀輸出時用；RPA Worker 是視窗程式，沒有標準輸出）、
``artifact: …``（要上傳的檔案）與 ``runtime: 目標=環境代號``（ADR 0018，更新檔的清單要用）；
在 GitHub Actions 裡同時寫進步驟的輸出。
RPA Worker 的執行檔圖示在建置時由 ``rpa_desktop.icon`` 畫出（倉庫不放二進位圖檔）。

Windows 上另外用 Inno Setup 建安裝檔（M10.1 PR 3，``apps/desktop/packaging/rpa_worker.iss``），
步驟的輸出多一行 ``installer: …``：

- 安裝檔自己的訊息從 rpa_desktop 的訊息目錄（``installer.*``）產生 ``[CustomMessages]``；
- 繁中、簡中的翻譯檔從 Inno Setup 原始碼（固定的提交）下載，核對 SHA-256；
- WebView2 引導程式從 Microsoft 下載，核對數位簽章是 Microsoft 的而且有效；
- 找到 ISCC（GitHub 的 Windows 執行環境已安裝 Inno Setup 6.7.1）後編譯。

"""

import argparse
import hashlib
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

from rpa_desktop.build_info import APPS, App, write
from rpa_update.runtime import Runtime, load_runtime

ROOT: Final = Path(__file__).resolve().parent.parent
SPEC: Final = ROOT / "apps" / "desktop" / "packaging" / "rpa_desktop.spec"
DIST: Final = ROOT / "dist" / "desktop"
WORK: Final = ROOT / "build" / "desktop"

EXECUTABLES: Final = {"recorder": "rpa-recorder", "worker": "rpa-worker"}
BUNDLES: Final = {"recorder": "RPA Recorder", "worker": "RPA Worker"}
"""macOS 的 .app 名稱（也是 DMG 的磁碟名稱）。"""
FILES: Final = {"recorder": "RPA-Recorder", "worker": "RPA-Worker"}
"""下載檔的檔名開頭。"""

INSTALLER_SCRIPT: Final = ROOT / "apps" / "desktop" / "packaging" / "rpa_worker.iss"
INNO_LANGUAGES: Final = {"zh-Hant": "zht", "zh-Hans": "zhs", "en": "en"}
"""訊息目錄的語言 → rpa_worker.iss 的 [Languages] 名稱。"""
INSTALLER_PREFIX: Final = "installer."
ISSRC_COMMIT: Final = "cfdf48923178df4b4f040e038b423aa555a61ffc"
"""Inno Setup 原始碼的 is-6_7_1 標籤（和 GitHub 的 Windows 執行環境上的 Inno Setup 版本相同）。"""
TRANSLATIONS: Final = {
    "ChineseTraditional.isl": "ab22b0ebf82969d1c9a7208e0e9f60e5119c0c95b9dacc00eb8e5582c7d3c604",
    "ChineseSimplified.isl": "7d544b9bb1d142cfa11f2e5d3cc8abe2e55f8e066c5124e3772675aa236e1278",
}
"""Inno Setup 的非官方翻譯（Files/Languages/Unofficial）與它們的 SHA-256。"""
TRANSLATION_URL: Final = (
    "https://raw.githubusercontent.com/jrsoftware/issrc/{commit}/Files/Languages/Unofficial/{name}"
)
WEBVIEW2_URL: Final = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
"""WebView2 Runtime 的 Evergreen 引導程式（Microsoft 允許隨安裝檔散布）。

檔案會更新，所以不釘 SHA-256，改為核對 Microsoft 的數位簽章。"""
WEBVIEW2_FILE: Final = "MicrosoftEdgeWebview2Setup.exe"
_MESSAGE_NAME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


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


def installer_messages(catalogs: Mapping[str, Mapping[str, str]]) -> str:
    """安裝檔的 [CustomMessages]：每種語言、每個 ``installer.*`` 訊息一行。

    ``catalogs`` 是 {語言: 訊息目錄}；訊息裡 Inno Setup 的 ``%1``、``%n`` 照原樣保留。
    """
    lines = [
        "; 由 tools/build_desktop.py 從 rpa_desktop 的訊息目錄（installer.*）產生，不要手改",
        "[CustomMessages]",
    ]
    for locale, language in INNO_LANGUAGES.items():
        for key, value in sorted(catalogs[locale].items()):
            if not key.startswith(INSTALLER_PREFIX):
                continue
            name = key.removeprefix(INSTALLER_PREFIX)
            if not _MESSAGE_NAME.fullmatch(name):
                raise ValueError(f"安裝檔的訊息名稱只能有英數字與底線：{key}")
            if "\n" in value or "\r" in value:
                raise ValueError(f"安裝檔的訊息不能換行（用 %n）：{key}")
            lines.append(f"{language}.{name}={value}")
    return "\n".join(lines) + "\n"


def _download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:  # 固定的 https 網址
        target.write_bytes(response.read())
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_translations(folder: Path) -> Path:
    """下載繁中、簡中的翻譯檔並核對 SHA-256（不對就停下來，不用來路不明的檔案）。"""
    for name, expected in TRANSLATIONS.items():
        target = folder / name
        if not target.is_file() or _sha256(target) != expected:
            _download(TRANSLATION_URL.format(commit=ISSRC_COMMIT, name=name), target)
        actual = _sha256(target)
        if actual != expected:
            raise RuntimeError(f"{name} 的 SHA-256 是 {actual}，應該是 {expected}")
    return folder


def _verify_microsoft_signature(path: Path) -> None:
    """Windows 的 Authenticode：簽章有效，而且簽署者是 Microsoft。"""
    script = (
        f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; "
        "if ($s.Status -ne 'Valid') { Write-Output ('status: ' + $s.Status); exit 1 }; "
        "if ($s.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') "
        "{ Write-Output ('signer: ' + $s.SignerCertificate.Subject); exit 1 }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{path.name} 的數位簽章不對：{completed.stdout.strip()}")


def fetch_webview2(folder: Path) -> Path:
    target = _download(WEBVIEW2_URL, folder / WEBVIEW2_FILE)
    _verify_microsoft_signature(target)
    return target


def find_iscc() -> Path:
    """Inno Setup 的命令列編譯器。"""
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return Path(found)
    bases = [os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")]
    local = os.environ.get("LOCALAPPDATA")
    candidates = [Path(base) / "Inno Setup 6" / "ISCC.exe" for base in bases if base]
    if local:
        candidates.append(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("找不到 Inno Setup 的 ISCC（https://jrsoftware.org/isdl.php）")


def iscc_defines(
    *,
    version: str,
    source: Path,
    output: Path,
    icon: Path,
    languages: Path,
    webview2: Path,
    messages: Path,
) -> list[str]:
    """傳給 ISCC 的定義（rpa_worker.iss 開頭列的那些）。"""
    values: dict[str, object] = {
        "AppVersion": version,
        "SourceDir": source,
        "OutputDir": output,
        "IconFile": icon,
        "LangDir": languages,
        "WebView2Setup": webview2,
        "MessagesFile": messages,
    }
    return [f"/D{key}={value}" for key, value in values.items()]


def installer_path(version: str) -> Path:
    """建好的安裝檔（和 zip 放在一起）。"""
    return DIST / f"{FILES['worker']}-Setup-{version}-{_platform_tag()}.exe"


def _installer(version: str) -> Path:
    """Windows：用 Inno Setup 建 RPA Worker 的安裝檔。"""
    from rpa_core.i18n import LOCALES
    from rpa_desktop.i18n import t

    work = WORK / "worker" / "installer"
    work.mkdir(parents=True, exist_ok=True)
    messages = work / "messages.iss"
    text = installer_messages({locale: t.messages(locale) for locale in LOCALES})
    messages.write_text(text, encoding="utf-8")
    icon = _icon("worker")
    assert icon is not None
    defines = iscc_defines(
        version=version,
        source=DIST / EXECUTABLES["worker"],
        output=DIST,
        icon=icon,
        languages=fetch_translations(work / "languages"),
        webview2=fetch_webview2(work),
        messages=messages,
    )
    subprocess.run([str(find_iscc()), "/Q", *defines, str(INSTALLER_SCRIPT)], cwd=ROOT, check=True)
    built = installer_path(version)
    if not built.is_file():
        raise RuntimeError(f"ISCC 沒有產生 {built}")
    return built


def check_bundle(bundle: Path, app: App) -> None:
    """macOS：確認雙擊 App 時啟動的是 App 本身，不是 rpa-child（Info.plist 的 CFBundleExecutable）。

    也確認不是 LSBackgroundOnly（PyInstaller 從主控台的 rpa-child 繼承時會加上）。
    """
    with (bundle / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    expected = EXECUTABLES[app]
    actual = info.get("CFBundleExecutable")
    if actual != expected:
        raise RuntimeError(
            f"{bundle.name} 的 CFBundleExecutable 是 {actual!r}，應該是 {expected!r}"
        )
    if info.get("LSBackgroundOnly"):
        raise RuntimeError(f"{bundle.name} 是 LSBackgroundOnly：沒有 Dock 圖示與選單列")


def _dmg(app: App, version: str) -> Path:
    """把 .app 和指向「應用程式」的捷徑放進 DMG，打開後拖過去就安裝好。"""
    bundle = DIST / f"{BUNDLES[app]}.app"
    check_bundle(bundle, app)
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


def runtime_path(app: App) -> Path:
    """spec 寫出的 runtime.json（ADR 0018），也放進 App 的 rpa_update/。"""
    return WORK / app / "runtime.json"


def runtime_copy(runtime: Runtime) -> Path:
    """runtime.json 的副本，和 App 一起上傳：發布流程用它產生更新檔（build_update.py）。"""
    return DIST / f"runtime-{runtime.target}.json"


def build(app: App) -> tuple[Path, Path, Path | None, Runtime]:
    """建置一個 App，回傳 (執行檔, 要上傳的檔案, Windows 的安裝檔, 執行環境)。"""
    info_path = WORK / app / "build_info.json"
    info = write(info_path, app, _commit())
    runtime_file = runtime_path(app)
    runtime_file.unlink(missing_ok=True)
    env = {
        **os.environ,
        "RPA_DESKTOP_APP": app,
        "RPA_DESKTOP_INFO": str(info_path),
        "RPA_DESKTOP_VERSION": info.version,
        "RPA_DESKTOP_RELEASE": f"{info.version}-{info.commit}" if info.commit else info.version,
        "RPA_DESKTOP_RUNTIME": str(runtime_file),
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
    runtime = load_runtime(runtime_file)
    if runtime is None:
        raise RuntimeError(f"PyInstaller 沒有寫出 {runtime_file}")
    shutil.copy2(runtime_file, runtime_copy(runtime))
    artifact = _dmg(app, info.version) if sys.platform == "darwin" else _zip(app, info.version)
    setup = _installer(info.version) if os.name == "nt" and app == "worker" else None
    return executable(app), artifact, setup, runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建置 RPA 錄製端或 RPA Worker")
    parser.add_argument("app", choices=APPS)
    args = parser.parse_args(argv)
    built, artifact, setup, runtime = build(cast("App", args.app))
    # 用正斜線：Windows 上的 bash 與 PowerShell 都看得懂
    lines = {
        "executable": built.as_posix(),
        "child": child(cast("App", args.app)).as_posix(),
        "artifact": artifact.as_posix(),
        "installer": setup.as_posix() if setup is not None else "",
        # 發布流程收集各平台的環境代號，寫進更新檔的清單（tools/build_update.py --runtime）
        "runtime": f"{runtime.target}={runtime.id}",
        "runtime_file": runtime_copy(runtime).as_posix(),
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
