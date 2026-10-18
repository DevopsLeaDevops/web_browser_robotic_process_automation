# PyInstaller 設定：RPA 錄製端（macOS）與 RPA Worker（Windows）（M10，ADR 0014）。
#
# 不直接執行，由 tools/build_desktop.py 寫好建置資訊、設定環境變數後呼叫：
#   RPA_DESKTOP_APP      recorder 或 worker
#   RPA_DESKTOP_INFO     建置資訊 build_info.json 的路徑（放進 App 的 rpa_desktop/）
#   RPA_DESKTOP_VERSION  版本（macOS 的 Info.plist）
#   RPA_DESKTOP_ICON     執行檔的圖示（.ico，Windows；建置時由 rpa_desktop.icon 畫出，可省略）
#
# 資料夾模式（onedir），兩個執行檔共用同一份程式與資料：
#   rpa-worker                RPA Worker（M10.1）：視窗程式（WebView2 狀態視窗＋通知區），沒有主控台
#   rpa-recorder              RPA 錄製端：還是主控台程式（視窗在 M10.2）
#   rpa-child                 子程序用的主控台程式：runner、登入檢查、錄製、調試、playwright
#                             （rpa_runner.commands 依檔名找它）；也是 --version、--self-test、
#                             --worker（主控台版）要讀輸出時用的入口
# macOS 再包成 .app（ad-hoc 簽章，PyInstaller 自動處理；MVP 不簽 Developer ID、不公證）。

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

APP = os.environ["RPA_DESKTOP_APP"]
INFO = Path(os.environ["RPA_DESKTOP_INFO"])
VERSION = os.environ.get("RPA_DESKTOP_VERSION", "0.0.0")
ICON = os.environ.get("RPA_DESKTOP_ICON") or None
ROOT = Path(SPECPATH).resolve().parents[2]  # SPECPATH 由 PyInstaller 提供
DEMO = ROOT / "scenarios" / "demo"

NAMES = {
    "recorder": {
        "exe": "rpa-recorder",
        "bundle": "RPA Recorder",
        "display": "RPA 錄製端",
        "id": "io.github.devopsleadevops.rpa.recorder",
    },
    "worker": {
        "exe": "rpa-worker",
        "bundle": "RPA Worker",
        "display": "RPA Worker",
        "id": "io.github.devopsleadevops.rpa.worker",
    },
}[APP]

# 自己的套件全部收進來：子程序以 runpy 執行模組，靜態分析看不到這些匯入
PACKAGES = ["rpa_core", "rpa_runner", "rpa_worker", "rpa_desktop", "testsite"]
# importlib.metadata.version() 要用到的套件資訊
DISTRIBUTIONS = ["rpa-core", "rpa-runner", "rpa-worker", "rpa-desktop", "rpa-testsite", "playwright"]


def _ours(name: str) -> bool:
    # testsite.browsers 是測試用的輔助（匯入 pytest），不進 App
    return name != "testsite.browsers"


hiddenimports = ["playwright.__main__"]
datas = []
for package in PACKAGES:
    hiddenimports += collect_submodules(package, filter=_ours)
    datas += collect_data_files(package)
for distribution in DISTRIBUTIONS:
    datas += copy_metadata(distribution)
# Playwright 的 driver（Node 與 Playwright 的 JS），codegen 與下載瀏覽器都靠它
datas += collect_data_files("playwright")
datas.append((str(INFO), "rpa_desktop"))
# Windows 上的 RPA Worker 視窗（M10.1）：pywebview（WebView2，經由 pythonnet）、pystray、keyring。
# 這些套件只在 Windows 安裝（apps/desktop/pyproject.toml），而且都在執行時才依名稱載入後端，
# 靜態分析看不到：子模組、資料（WebView2 的 DLL、Python.Runtime.dll）與套件資訊（keyring 用
# entry points 找後端）都明確收進來。
WINDOWS_WORKER = APP == "worker" and sys.platform == "win32"
binaries = []
_OTHER_GUIS = ("webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cocoa",
               "webview.platforms.android", "pystray._xorg", "pystray._gtk", "pystray._appindicator",
               "pystray._darwin", "keyring.backends.macOS", "keyring.backends.SecretService",
               "keyring.backends.kwallet", "keyring.backends.libsecret")


def _windows_only(name):
    return not name.startswith(_OTHER_GUIS)


if WINDOWS_WORKER:
    for package in ("webview", "pystray", "keyring", "win32ctypes", "clr_loader", "pythonnet"):
        hiddenimports += collect_submodules(package, filter=_windows_only)
        datas += collect_data_files(package)
        binaries += collect_dynamic_libs(package)
    hiddenimports += ["clr"]
    for distribution in ("pywebview", "pystray", "keyring", "pythonnet", "clr_loader", "pillow"):
        datas += copy_metadata(distribution)
# 自我測試用的範例場景（rpa_desktop.selftest）
datas.append((str(DEMO / "ba-001.yaml"), "rpa_desktop/scenarios"))
for name in ("scenario.yaml", "automation.py", "assertion.py"):
    datas.append((str(DEMO / "ba-001-script" / name), "rpa_desktop/scenarios/ba-001-script"))

a = Analysis(
    [str(ROOT / "apps" / "desktop" / "src" / "rpa_desktop" / "__main__.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "_pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = {
    "exclude_binaries": True,
    "debug": False,
    "strip": False,
    "upx": False,
    "argv_emulation": False,
    "target_arch": None,
    "codesign_identity": None,
    "entitlements_file": None,
}
# Python 的 UTF-8 模式：打包後的 App 不讀 PYTHONIOENCODING 等環境變數，Windows 上標準輸出
# 與 open() 的預設編碼會是 cp1252 之類，子程序印出中文、寫檔案就會出錯。
options = [("X utf8_mode=1", None, "OPTION")]
# RPA Worker 是視窗程式：雙擊不跳主控台。子程序與要讀輸出的命令用同資料夾的 rpa-child（主控台程式）。
app_exe = EXE(
    pyz, a.scripts, options, name=NAMES["exe"], console=APP != "worker", icon=ICON, **common
)
child_exe = EXE(pyz, a.scripts, options, name="rpa-child", console=True, icon=ICON, **common)
coll = COLLECT(app_exe, child_exe, a.binaries, a.datas, strip=False, upx=False, name=NAMES["exe"])

if sys.platform == "darwin":
    BUNDLE(
        coll,
        name=f"{NAMES['bundle']}.app",
        bundle_identifier=NAMES["id"],
        version=VERSION,
        info_plist={
            "CFBundleName": NAMES["bundle"],
            "CFBundleDisplayName": NAMES["display"],
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            "NSHighResolutionCapable": True,
            # macOS 15 起連區網要使用者允許：管理 Portal 與內部網站都在區網上
            "NSLocalNetworkUsageDescription": (
                "RPA 錄製端要連到區網上的管理 Portal 與內部系統。"
                " RPA Recorder connects to the management portal and internal sites on your network."
            ),
        },
    )
