"""打包後的 App 唯一的入口（M10，ADR 0014）：依第一個參數決定做什麼。

- ``--rpa-module 模組 …``：以 ``__main__`` 執行一個模組，等同 ``python -m 模組 …``。
  runner、登入檢查、錄製、逐步調試與 ``playwright`` 命令列都經由這裡（:mod:`rpa_runner.commands`）。
- ``--rpa-script 腳本 …``：執行一個 Python 腳本，等同 ``python 腳本 …``（Python 腳本場景）。
- ``--version``：以 JSON 印出建置資訊。
- ``--self-test [--report 檔案]``：自我測試，見 :mod:`rpa_desktop.selftest`。
- ``--worker …``：主控台版的 worker（:mod:`rpa_desktop.worker_app`），排查問題用，開發環境也能用。
- ``--no-window …``：不開視窗的 worker（:mod:`rpa_desktop.headless`），自動化與 CI 用；
  旗標在任何位置都算。
- ``--window …``：視窗版的 worker（:mod:`rpa_desktop.gui`），開發環境試視窗用。
- ``--recorder …``：RPA 錄製端的視窗（:mod:`rpa_desktop.recorder_gui`，M10.2），開發環境試視窗用。
- ``--forget-pairing``：清除這台電腦的配對（認證管理員裡的權杖與配對檔）後結束。解除安裝時
  選擇「也刪除配對、設定與日誌」會先執行這個（安裝檔 apps/desktop/packaging/rpa_worker.iss）。
- 其他：啟動 App。打包的 RPA Worker 開視窗版（M10.1）、打包的 RPA 錄製端開錄製端的視窗
  （M10.2）；沒有參數或其他參數都交給它們。同資料夾的 ``rpa-child`` 只跑子程序，
  不會變成第二個 App。

打包的 RPA Worker 是視窗程式（沒有主控台）：``--version``、``--self-test`` 要讀輸出時用同資料夾的
``rpa-child``（主控台程式，同一份程式碼）。

子程序的命令不經過 click 之類的命令列套件：參數原封不動交給要執行的模組，免得被解析或改寫。
子程序每次都從這裡啟動，所以這個模組只在需要時才匯入其他套件，讓啟動越快越好。
"""

import io
import json
import os
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from rpa_runner.commands import CHILD_EXECUTABLE, FROZEN_MODULE, FROZEN_SCRIPT, is_frozen

if TYPE_CHECKING:  # 子程序也經過這裡：執行時只在需要時才載入
    from rpa_desktop.credentials import TokenStore

__all__ = [
    "FORGET_FLAG",
    "NO_WINDOW_FLAG",
    "RECORDER_FLAG",
    "WINDOW_FLAG",
    "WORKER_FLAG",
    "main",
    "run_module",
    "run_script",
]

WORKER_FLAG = "--worker"
NO_WINDOW_FLAG = "--no-window"
WINDOW_FLAG = "--window"
RECORDER_FLAG = "--recorder"
FORGET_FLAG = "--forget-pairing"
_OWN_FLAGS = (FROZEN_MODULE, FROZEN_SCRIPT, "--self-test", "--version", FORGET_FLAG)

_USAGE = f"""usage:
  {{app}} {FROZEN_MODULE} MODULE [ARGS...]
  {{app}} {FROZEN_SCRIPT} SCRIPT [ARGS...]
  {{app}} --version
  {{app}} --self-test [--report FILE]
  {{app}} --worker [--invite INVITE] [--server URL] ...
  {{app}} --no-window [--invite INVITE] [--log FILE] ...
  {{app}} --window [--background] [--smoke-test --report FILE]
  {{app}} --recorder [--invite INVITE] [--smoke-test --report FILE]
  {{app}} {FORGET_FLAG}
"""


def _exit_code(code: object) -> int:
    """SystemExit 的代碼換成結束碼（和 Python 直譯器的規則相同）。"""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    sys.stderr.write(f"{code}\n")
    return 1


def run_module(module: str, args: Sequence[str]) -> int:
    """以 ``__main__`` 執行模組；``sys.argv`` 換成 ``[模組, *參數]``。"""
    sys.argv = [module, *args]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as exit_:
        return _exit_code(exit_.code)
    return 0


def run_script(script: str, args: Sequence[str]) -> int:
    """執行 Python 腳本；和 ``python 腳本`` 一樣，腳本所在的資料夾排在 import 路徑的最前面。"""
    path = Path(script).resolve()
    sys.argv = [str(path), *args]
    sys.path.insert(0, str(path.parent))
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exit_:
        return _exit_code(exit_.code)
    return 0


def _usage() -> int:
    sys.stderr.write(_USAGE.format(app=Path(sys.argv[0]).name or "rpa-desktop"))
    return 2


def _utf8_streams() -> None:
    """標準輸出與錯誤一律 UTF-8（打包時也開了 Python 的 UTF-8 模式，這裡是保險）。"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() != "utf-8":
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _is_child() -> bool:
    """這個程序是不是同資料夾的 rpa-child（只用來跑子程序）。"""
    return Path(sys.executable).stem.lower() == CHILD_EXECUTABLE


def _frozen_app() -> str | None:
    """打包的哪一個 App（``worker``、``recorder``）；開發環境或 rpa-child 是 None。"""
    if not is_frozen() or _is_child():
        return None
    from rpa_desktop.build_info import load

    return load().app


def _missing_streams() -> None:
    """視窗程式（打包的 RPA Worker）沒有標準輸出與錯誤：接到 os.devnull，免得寫入時當掉。

    要讀輸出的命令（``--version``、``--self-test``）請用同資料夾的 ``rpa-child``。
    """
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 - 整個程序都用
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 - 整個程序都用


def forget_pairing(store: "TokenStore | None" = None) -> int:
    """清除這台電腦的配對（解除安裝時用）；認證管理員不能用時只刪配對檔。"""
    from rpa_desktop.credentials import Credentials
    from rpa_desktop.worker_app import data_dir

    Credentials(data_dir(os.environ), store).clear()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if is_frozen():
        _missing_streams()
        _utf8_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == WORKER_FLAG:
        from rpa_desktop.worker_app import main as worker

        return worker(args[1:])
    if args and args[0] == FORGET_FLAG:
        return forget_pairing()
    if NO_WINDOW_FLAG in args and (not args or args[0] not in (FROZEN_MODULE, FROZEN_SCRIPT)):
        from rpa_desktop.headless import main as headless

        return headless([arg for arg in args if arg != NO_WINDOW_FLAG])
    if args and args[0] == WINDOW_FLAG:
        from rpa_desktop.gui import main as window

        return window(args[1:])
    if args and args[0] == RECORDER_FLAG:
        from rpa_desktop.recorder_gui import main as recorder

        return recorder(args[1:])
    if not args or args[0] not in _OWN_FLAGS:
        app = _frozen_app()
        if app == "worker":
            from rpa_desktop.gui import main as window

            return window(args)
        if app == "recorder":
            from rpa_desktop.recorder_gui import main as recorder

            return recorder(args)
    if args and args[0] in (FROZEN_MODULE, FROZEN_SCRIPT):
        if len(args) < 2:
            return _usage()
        if args[0] == FROZEN_MODULE:
            return run_module(args[1], args[2:])
        return run_script(args[1], args[2:])
    if args and args[0] == "--self-test":
        # 只有自我測試才需要 runner 與測試網站，放在這裡匯入，子程序的啟動不必載入它們
        from rpa_desktop.selftest import main as self_test

        return self_test(args[1:])
    if args and args[0] in ("--help", "-h"):
        _usage()
        return 0
    if args and args[0] != "--version":
        return _usage()
    from rpa_desktop.build_info import load

    sys.stdout.write(json.dumps(load().to_json(), ensure_ascii=False) + "\n")
    return 0
