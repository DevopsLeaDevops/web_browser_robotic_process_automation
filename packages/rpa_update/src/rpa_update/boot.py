"""桌面 App 的啟動器（ADR 0018），也是 PyInstaller 的入口腳本：選好程式碼層再啟動 App。

- 其他參數：選層（:func:`rpa_update.layers.activate`），再照原樣執行 ``python -m rpa_desktop``；
- ``--install-update 更新檔``：裝成新的一層（下次啟動時使用），以 JSON 印出結果。給排查問題與
  CI 用（要讀輸出時用同資料夾的 ``rpa-child``）；平常由 App 從管理 Portal 下載後自己安裝。

這裡只能匯入標準函式庫與 rpa_update：程式碼層的套件要在選好之後才第一次載入，否則用到的會是
內建的那一份。新裝的一層在 App 正常結束、或執行超過 :data:`rpa_update.layers.CONFIRM_AFTER`
秒時確認，之後就不會再退回。

重新啟動套用更新（:func:`relaunch`，Worker 閒置時用）：新的程序帶著 :data:`RESTART_AFTER_ENV`
（舊程序的 pid），先等舊的結束、放開單一執行的鎖，才選層。新的一層還沒確認就以非 0 結束時，
再重新啟動一次：沒有人在電腦前也會在 :data:`rpa_update.layers.MAX_ATTEMPTS` 次後退回上一層，
而不是停在那裡。
"""

import json
import os
import runpy
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Final

from rpa_update import layers
from rpa_update.errors import UpdateError
from rpa_update.runtime import load_runtime

__all__ = [
    "INSTALL_FLAG",
    "RESTART_AFTER_ENV",
    "RESTART_WAIT",
    "install",
    "main",
    "relaunch",
    "wait_for_exit",
]

INSTALL_FLAG: Final = "--install-update"
APP_MODULE: Final = "rpa_desktop"
RESTART_AFTER_ENV: Final = "RPA_RESTART_AFTER"
"""重新啟動時舊程序的 pid：新的程序等它結束後才選層、啟動。"""
RESTART_WAIT: Final = 300.0
"""最多等舊程序這麼久（它要先停下接任務的迴圈）；超過就照樣啟動。"""
_RESET_ENV: Final = "PYINSTALLER_RESET_ENVIRONMENT"
"""PyInstaller：新的程序是另一份獨立的 App，不是這個程序的子程序。"""


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


# ---------------------------------------------------------------- 重新啟動


def relaunch(
    args: Sequence[str], environ: Mapping[str, str] | None = None
) -> "subprocess.Popen[bytes]":
    """重新啟動這個 App（``args`` 是給新程序的參數）：新的程序等這個程序結束後才選層。

    不帶 :data:`rpa_update.layers.LAYER_ENV`：新的程序重新選，用的就是剛裝好的那一層。
    """
    env = dict(os.environ if environ is None else environ)
    env.pop(layers.LAYER_ENV, None)
    env[RESTART_AFTER_ENV] = str(os.getpid())
    env[_RESET_ENV] = "1"
    command = [sys.executable, *args]
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        return subprocess.Popen(
            command,
            env=env,
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return subprocess.Popen(
        command,
        env=env,
        start_new_session=True,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_exit(pid: int, timeout: float) -> bool:
    """等 ``pid`` 這個程序結束；回傳它是否已經結束（逾時是 False）。"""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return True  # 已經結束（或不是這個使用者的程序：不等）
        try:
            return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0  # WAIT_OBJECT_0
        finally:
            kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # 還在，只是不是這個使用者的
        if _zombie(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def _zombie(pid: int) -> bool:
    """Linux：已經結束、只是還沒被父程序收掉（os.kill 仍然找得到）。其他系統一律 False。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return False
    return stat.rpartition(")")[2].split()[:1] == ["Z"]


def _after_restart(environ: MutableMapping[str, str], timeout: float) -> bool:
    """這次啟動是不是重新啟動（:func:`relaunch`）；是的話先等舊程序結束。"""
    value = environ.pop(RESTART_AFTER_ENV, "")
    if not value:
        return False
    try:
        pid = int(value)
    except ValueError:
        return False
    if pid != os.getpid():
        wait_for_exit(pid, timeout)
    return True


def _finish(layer: layers.Layer, code: int, restart: Sequence[str] | None) -> None:
    """新裝的一層跑完了：正常結束就確認；重新啟動後還沒確認就失敗時，再重新啟動一次。"""
    root = layer.path.parent
    if code == 0:
        layers.confirm(root, layer.release)
        return
    active = layers.read_active(root)
    if restart is None or not active.pending or active.release != layer.release:
        return
    layers.log(root, f"{layer.release} 還沒確認就結束了（{code}）：重新啟動再試")
    try:
        relaunch(restart)
    except OSError as error:
        layers.log(root, f"重新啟動失敗：{error}")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == [INSTALL_FLAG]:
        return install(args[1:])
    restarted = _after_restart(os.environ, RESTART_WAIT)
    layer, pending = layers.activate()
    if layer is not None and pending:
        confirm = threading.Timer(
            layers.CONFIRM_AFTER, layers.confirm, args=(layer.path.parent, layer.release)
        )
        confirm.daemon = True
        confirm.start()
    code = 1
    try:
        runpy.run_module(APP_MODULE, run_name="__main__")
        code = 0
    except SystemExit as exit_:
        code = _exit_code(exit_.code)
    finally:
        if layer is not None and pending:
            _finish(layer, code, args if restarted else None)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
