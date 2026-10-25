"""桌面 App 的啟動器（ADR 0018），也是 PyInstaller 的入口腳本：選好程式碼層再啟動 App。

- 其他參數：選層（:func:`rpa_update.layers.activate`），再照原樣執行 ``python -m rpa_desktop``；
- ``--install-update 更新檔``：裝成新的一層（下次啟動時使用），以 JSON 印出結果。給排查問題與
  CI 用（要讀輸出時用同資料夾的 ``rpa-child``）；平常由 App 從管理 Portal 下載後自己安裝。

這裡只能匯入標準函式庫與 rpa_update：程式碼層的套件要在選好之後才第一次載入，否則用到的會是
內建的那一份。新裝的一層在 App 正常結束、或執行超過 :data:`rpa_update.layers.CONFIRM_AFTER`
秒時確認，之後就不會再退回。
"""

import json
import os
import runpy
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from rpa_update import layers
from rpa_update.errors import UpdateError
from rpa_update.runtime import load_runtime

__all__ = ["INSTALL_FLAG", "install", "main"]

INSTALL_FLAG: Final = "--install-update"
APP_MODULE: Final = "rpa_desktop"


def _print(data: dict[str, object]) -> None:
    if sys.stdout is not None:  # 視窗程式沒有標準輸出
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def _exit_code(code: object) -> int:
    """SystemExit 的代碼換成結束碼（和 Python 直譯器的規則相同）。"""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    if sys.stderr is not None:
        sys.stderr.write(f"{code}\n")
    return 1


def install(args: Sequence[str]) -> int:
    """``--install-update 更新檔``。"""
    if len(args) != 1:
        if sys.stderr is not None:
            sys.stderr.write(f"usage: {Path(sys.argv[0]).name} {INSTALL_FLAG} FILE\n")
        return 2
    try:
        runtime = load_runtime()
        if runtime is None:
            raise UpdateError("not_packaged")
        result = layers.install_layer(
            layers.layers_dir(runtime),
            Path(args[0]),
            runtime,
            protect=[os.environ.get(layers.LAYER_ENV, "")],
        )
    except UpdateError as error:
        _print({"error": error.code, **{key: str(value) for key, value in error.params.items()}})
        return 1
    _print(
        {
            "version": result.manifest.version,
            "release": result.manifest.release,
            "previous": result.previous,
            "already": result.already,
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == [INSTALL_FLAG]:
        return install(args[1:])
    layer, pending = layers.activate()
    if layer is not None and pending:
        confirm = threading.Timer(
            layers.CONFIRM_AFTER, layers.confirm, args=(layer.path.parent, layer.release)
        )
        confirm.daemon = True
        confirm.start()
    try:
        runpy.run_module(APP_MODULE, run_name="__main__")
        code = 0
    except SystemExit as exit_:
        code = _exit_code(exit_.code)
    if layer is not None and pending and code == 0:
        layers.confirm(layer.path.parent, layer.release)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
