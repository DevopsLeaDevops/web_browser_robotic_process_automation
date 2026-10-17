"""打包後的 App 唯一的入口（M10，ADR 0014）：依第一個參數決定做什麼。

- ``--rpa-module 模組 …``：以 ``__main__`` 執行一個模組，等同 ``python -m 模組 …``。
  runner、登入檢查、錄製、逐步調試與 ``playwright`` 命令列都經由這裡（:mod:`rpa_runner.commands`）。
- ``--rpa-script 腳本 …``：執行一個 Python 腳本，等同 ``python 腳本 …``（Python 腳本場景）。
- ``--version``：以 JSON 印出建置資訊。
- ``--self-test [--report 檔案]``：自我測試，見 :mod:`rpa_desktop.selftest`。
- 其他：啟動 App。M10.0 還沒有視窗（M10.1 Worker、M10.2 錄製端），先印出建置資訊。

子程序的命令不經過 click 之類的命令列套件：參數原封不動交給要執行的模組，免得被解析或改寫。
子程序每次都從這裡啟動，所以這個模組只在需要時才匯入其他套件，讓啟動越快越好。
"""

import io
import json
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from rpa_runner.commands import FROZEN_MODULE, FROZEN_SCRIPT, is_frozen

__all__ = ["main", "run_module", "run_script"]

_USAGE = f"""usage:
  {{app}} {FROZEN_MODULE} MODULE [ARGS...]
  {{app}} {FROZEN_SCRIPT} SCRIPT [ARGS...]
  {{app}} --version
  {{app}} --self-test [--report FILE]
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


def main(argv: Sequence[str] | None = None) -> int:
    if is_frozen():
        _utf8_streams()
    args = list(sys.argv[1:] if argv is None else argv)
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
