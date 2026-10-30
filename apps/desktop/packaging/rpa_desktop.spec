# PyInstaller 設定：RPA 錄製端（macOS）與 RPA Worker（Windows、macOS）（M10，ADR 0014）。
#
# 不直接執行，由 tools/build_desktop.py 寫好建置資訊、設定環境變數後呼叫：
#   RPA_DESKTOP_APP      recorder 或 worker
#   RPA_DESKTOP_INFO     建置資訊 build_info.json 的路徑（放進 App 的 rpa_desktop/）
#   RPA_DESKTOP_VERSION  版本（macOS 的 Info.plist）
#   RPA_DESKTOP_RELEASE  內建的程式是哪一版（版本-提交），寫進 runtime.json
#   RPA_DESKTOP_RUNTIME  寫出 runtime.json 的路徑（放進 App 的 rpa_update/，ADR 0018）
#   RPA_DESKTOP_ICON     執行檔的圖示（.ico，Windows；建置時由 rpa_desktop.icon 畫出，可省略）
#   RPA_DESKTOP_PYTHON_RUNTIME  RPA Worker 附帶的 RPA Python 運行環境壓縮檔（ADR 0020），放進 runtimes/
#
# 分層（ADR 0018）：入口是 rpa_update.boot，先選好使用者資料夾裡的程式碼層（更新檔裝的），
# 排在 import 路徑最前面，再執行 rpa_desktop。App 裡的這份程式是沒有更新、或更新不能用時的
# 內建版本。外殼（Python、標準函式庫、第三方套件、rpa_update）的內容算成環境代號寫進
# runtime.json：代號相同的更新檔才能套用。標準函式庫與常用的第三方套件整個收進來，之後的程式
# 用到新的模組時不必重新安裝。
#
# 資料夾模式（onedir），兩個執行檔共用同一份程式與資料：
#   rpa-worker                RPA Worker（M10.1；macOS 2026-10-22 起）：視窗程式（WebView2 或 WKWebView
#                             的狀態視窗＋通知區／選單列），沒有主控台
#   rpa-recorder              RPA 錄製端（M10.2）：視窗程式（WKWebView 視窗，連本機閘道）
#   rpa-child                 子程序用的主控台程式：runner、登入檢查、錄製、調試、playwright
#                             （rpa_runner.commands 依檔名找它）；也是 --version、--self-test、
#                             --worker（主控台版）要讀輸出時用的入口
# macOS 再包成 .app（ad-hoc 簽章，PyInstaller 自動處理；MVP 不簽 Developer ID、不公證）。

import importlib.util
import json
import os
import sys
from pathlib import Path

import PyInstaller

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

APP = os.environ["RPA_DESKTOP_APP"]
INFO = Path(os.environ["RPA_DESKTOP_INFO"])
VERSION = os.environ.get("RPA_DESKTOP_VERSION", "0.0.0")
RELEASE = os.environ.get("RPA_DESKTOP_RELEASE", VERSION)
RUNTIME = Path(os.environ["RPA_DESKTOP_RUNTIME"])
ICON = os.environ.get("RPA_DESKTOP_ICON") or None
PYTHON_RUNTIME = os.environ.get("RPA_DESKTOP_PYTHON_RUNTIME") or None
ROOT = Path(SPECPATH).resolve().parents[2]  # SPECPATH 由 PyInstaller 提供
DEMO = ROOT / "scenarios" / "demo"
EXAMPLES = ROOT / "scenarios" / "examples"

NAMES = {
    "recorder": {
        "exe": "rpa-recorder",
        "bundle": "RPA Recorder",
        "display": "RPA 錄製端",
        "id": "io.github.devopsleadevops.rpa.recorder",
        "network": (
            "RPA 錄製端要連到區網上的管理 Portal 與內部系統。"
            " RPA Recorder connects to the management portal and internal sites on your network."
        ),
    },
    "worker": {
        "exe": "rpa-worker",
        "bundle": "RPA Worker",
        "display": "RPA Worker",
        "id": "io.github.devopsleadevops.rpa.worker",
        "network": (
            "RPA Worker 要連到區網上的管理 Portal，並在內部系統上執行場景。"
            " RPA Worker connects to the management portal and runs scenarios on internal sites"
            " on your network."
        ),
    },
}[APP]

# 自己的套件全部收進來：子程序以 runpy 執行模組，靜態分析看不到這些匯入
CODE_PACKAGES = ["rpa_core", "rpa_script", "rpa_runner", "rpa_worker", "rpa_desktop", "testsite"]
"""程式碼層：更新檔會換掉的部分。"""
CODE_DISTRIBUTIONS = ["rpa-core", "rpa-script", "rpa-runner", "rpa-worker", "rpa-desktop", "rpa-testsite"]
PACKAGES = [*CODE_PACKAGES, "rpa_update"]
# importlib.metadata.version() 要用到的套件資訊
DISTRIBUTIONS = [*CODE_DISTRIBUTIONS, "rpa-update", "playwright"]
# 整個收進來的第三方套件：程式碼層執行時要用的（rpa_core、rpa_runner 的依賴）
FULL_PACKAGES = ["pydantic", "pydantic_core", "yaml", "jinja2", "markupsafe", "playwright", "pyee",
                 "greenlet"]
# 標準函式庫裡不收的：圖形介面、測試、安裝工具，以及會把系統函式庫帶進來的 readline、curses
# （pdb、rlcompleter 之類用到它們的地方都有沒有時的處理，Analysis 也排除）
SYSTEM_LIBRARIES = ["readline", "curses", "_curses", "_curses_panel"]
NOT_STDLIB = {"tkinter", "_tkinter", "turtle", "turtledemo", "idlelib", "test", "ensurepip", "venv",
              "lib2to3", "__hello__", "__phello__", "antigravity", "this", *SYSTEM_LIBRARIES}


def _ours(name: str) -> bool:
    # testsite.browsers 是測試用的輔助（匯入 pytest），不進 App
    return name != "testsite.browsers"


def _not_test(name):
    return not any(part in ("test", "tests", "idle_test") for part in name.split("."))


hiddenimports = ["playwright.__main__", "rpa_desktop.__main__"]
datas = []
for package in PACKAGES:
    hiddenimports += collect_submodules(package, filter=_ours)
    datas += collect_data_files(package)
for package in FULL_PACKAGES:
    hiddenimports += collect_submodules(package, filter=_not_test)
for name in sorted(sys.stdlib_module_names - NOT_STDLIB):
    spec = importlib.util.find_spec(name)
    if spec is None:  # 這個平台沒有
        continue
    hiddenimports.append(name)
    if spec.submodule_search_locations is not None:
        hiddenimports += collect_submodules(name, filter=_not_test)
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
# 其他系統的介面後端不收（它們匯入 gi、PyQt、AppKit 之類 Windows 沒有的套件）。
# keyring 的後端全部收進來：它依 entry points 逐一載入，少了模組會在日誌留下錯誤（後端自己會判斷能不能用）。
_OTHER_GUIS = ("webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cocoa",
               "webview.platforms.android", "pystray._xorg", "pystray._gtk", "pystray._appindicator",
               "pystray._darwin")
# macOS 的兩個 App（錄製端 M10.2、Worker 2026-10-22 起）：pywebview 只要 cocoa 後端（WKWebView，
# 經由 PyObjC）；keyring 用鑰匙圈。Worker 的選單列圖示也直接用 PyObjC（rpa_desktop.macos）。
MAC_APP = sys.platform == "darwin"
_NOT_COCOA = ("webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.android",
              "webview.platforms.winforms", "webview.platforms.edgechromium",
              "webview.platforms.mshtml", "webview.platforms.cef", "webview.platforms.win32")


def _windows_only(name):
    return not name.startswith(_OTHER_GUIS)


def _cocoa_only(name):
    return not name.startswith(_NOT_COCOA)


if WINDOWS_WORKER:
    for package in ("webview", "pystray", "keyring", "win32ctypes", "clr_loader", "pythonnet"):
        hiddenimports += collect_submodules(package, filter=_windows_only)
        datas += collect_data_files(package)
        binaries += collect_dynamic_libs(package)
    hiddenimports += ["clr"]
    for distribution in ("pywebview", "pystray", "keyring", "pythonnet", "clr_loader", "pillow"):
        datas += copy_metadata(distribution)
if MAC_APP:
    for package in ("webview", "keyring"):
        hiddenimports += collect_submodules(package, filter=_cocoa_only)
        datas += collect_data_files(package)
    # PyObjC 的框架在執行時才依名稱載入（pywebview 的 cocoa 後端）；pyinstaller-hooks-contrib 有它們的 hook
    hiddenimports += ["objc", "AppKit", "Foundation", "WebKit", "Quartz", "Security",
                      "UniformTypeIdentifiers", "PyObjCTools", "PyObjCTools.AppHelper"]
    for distribution in ("pywebview", "keyring"):
        datas += copy_metadata(distribution)
# 自我測試用的範例場景（rpa_desktop.selftest）
datas.append((str(DEMO / "ba-001.yaml"), "rpa_desktop/scenarios"))
for name in ("scenario.yaml", "automation.py", "assertion.py"):
    datas.append((str(DEMO / "ba-001-script" / name), "rpa_desktop/scenarios/ba-001-script"))
# Python 節點（ADR 0020）：Runner 把 rpa_script 的原始碼交給 RPA Python 運行環境，所以 .py 也收進來
# （程式碼層，不算環境代號）。RPA Worker 另外附帶運行環境的壓縮檔（環境代號只算檔名）與
# 自我測試用的範例 Python 節點。
datas += collect_data_files("rpa_script", include_py_files=True)
if APP == "worker":
    if PYTHON_RUNTIME is None:
        raise SystemExit("RPA Worker 要附帶 RPA Python 運行環境：設定 RPA_DESKTOP_PYTHON_RUNTIME")
    datas.append((PYTHON_RUNTIME, "runtimes"))
    for name in ("scenario.yaml", "automation.py", "report.py"):
        datas.append((str(EXAMPLES / "python-node" / name), "rpa_desktop/scenarios/python-node"))

a = Analysis(
    [str(ROOT / "packages" / "rpa_update" / "src" / "rpa_update" / "boot.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "_pytest", "IPython", *SYSTEM_LIBRARIES],
    noarchive=False,
)

# 執行環境（ADR 0018）：外殼收進去的一切（程式碼層以外）算成環境代號。
# 工作區套件的 *.dist-info 不算（tools/build_desktop.py 的 shell_files，2026-10-26）：
# 帶著版本號與 uv 留下的時間，每次建置都不同
from rpa_update.build import make_runtime, shell_components  # noqa: E402
from rpa_update.runtime import target_name  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.build_desktop import shell_files  # noqa: E402

components = shell_components(
    [(name, path) for name, path, _ in a.pure],
    shell_files((name, path) for name, path, _ in [*a.binaries, *a.datas]),
    ours=[*CODE_PACKAGES, *CODE_DISTRIBUTIONS],
    shell=f"pyinstaller {PyInstaller.__version__}",
)
runtime = make_runtime(
    target_name(APP),
    distributions=components.pop("distributions"),
    extra=components,
    release=RELEASE,
)
RUNTIME.parent.mkdir(parents=True, exist_ok=True)
RUNTIME.write_text(json.dumps(runtime.to_json(), indent=1) + "\n", encoding="utf-8")
a.datas.append(("rpa_update/runtime.json", str(RUNTIME), "DATA"))

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
# 兩個 App 都是視窗程式：雙擊不跳主控台。子程序與要讀輸出的命令用同資料夾的 rpa-child（主控台程式）。
app_exe = EXE(pyz, a.scripts, options, name=NAMES["exe"], console=False, icon=ICON, **common)
child_exe = EXE(pyz, a.scripts, options, name="rpa-child", console=True, icon=ICON, **common)
coll = COLLECT(app_exe, child_exe, a.binaries, a.datas, strip=False, upx=False, name=NAMES["exe"])

if sys.platform == "darwin":
    BUNDLE(
        coll,
        name=f"{NAMES['bundle']}.app",
        bundle_identifier=NAMES["id"],
        version=VERSION,
        info_plist={
            # PyInstaller 取 COLLECT 裡第一個執行檔當 CFBundleExecutable，而 COLLECT 依名稱排序：
            # rpa-child 排在 rpa-recorder 前面，雙擊 App 會跑主控台的 rpa-child（印出版本就結束）
            "CFBundleExecutable": NAMES["exe"],
            "CFBundleName": NAMES["bundle"],
            "CFBundleDisplayName": NAMES["display"],
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            "NSHighResolutionCapable": True,
            # COLLECT 從最後一個 EXE（主控台的 rpa-child）取 console，BUNDLE 會因此加上
            # LSBackgroundOnly：明確關掉，App 才有 Dock 圖示與選單列
            "LSBackgroundOnly": False,
            # 視窗只載入 127.0.0.1 上的本機閘道（HTTP）；轉送到管理 Portal 的是 Python，不受 ATS 管
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
            # macOS 15 起連區網要使用者允許：管理 Portal 與內部網站都在區網上
            "NSLocalNetworkUsageDescription": NAMES["network"],
        },
    )
