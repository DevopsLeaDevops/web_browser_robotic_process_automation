# PyInstaller 設定：RPA 錄製端（macOS）與 RPA Worker（Windows）（M10，ADR 0014）。
#
# 不直接執行，由 tools/build_desktop.py 寫好建置資訊、設定環境變數後呼叫：
#   RPA_DESKTOP_APP      recorder 或 worker
#   RPA_DESKTOP_INFO     建置資訊 build_info.json 的路徑（放進 App 的 rpa_desktop/）
#   RPA_DESKTOP_VERSION  版本（macOS 的 Info.plist）
#
# 資料夾模式（onedir），兩個執行檔共用同一份程式與資料：
#   rpa-recorder／rpa-worker  App 本身（M10.0 還沒有視窗，是主控台程式；M10.1、M10.2 改成視窗）
#   rpa-child                 子程序用的主控台程式：runner、登入檢查、錄製、調試、playwright
#                             （rpa_runner.commands 依檔名找它）
# macOS 再包成 .app（ad-hoc 簽章，PyInstaller 自動處理；MVP 不簽 Developer ID、不公證）。

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

APP = os.environ["RPA_DESKTOP_APP"]
INFO = Path(os.environ["RPA_DESKTOP_INFO"])
VERSION = os.environ.get("RPA_DESKTOP_VERSION", "0.0.0")
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
# 自我測試用的範例場景（rpa_desktop.selftest）
datas.append((str(DEMO / "ba-001.yaml"), "rpa_desktop/scenarios"))
for name in ("scenario.yaml", "automation.py", "assertion.py"):
    datas.append((str(DEMO / "ba-001-script" / name), "rpa_desktop/scenarios/ba-001-script"))

a = Analysis(
    [str(ROOT / "apps" / "desktop" / "src" / "rpa_desktop" / "__main__.py")],
    pathex=[],
    binaries=[],
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
app_exe = EXE(pyz, a.scripts, [], name=NAMES["exe"], console=True, **common)
child_exe = EXE(pyz, a.scripts, [], name="rpa-child", console=True, **common)
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
