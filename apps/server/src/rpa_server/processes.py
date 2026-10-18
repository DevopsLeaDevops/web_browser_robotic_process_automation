"""管理 Portal 啟動的長時間子程序：人工登入、錄製、調試工作階段（M4）。

- 每個子程序自成一個程序群組，結束時連同它開的瀏覽器一起終止。
- 子程序的語言跟伺服器設定相同（RPA_LANG），輸出一律 UTF-8。
- :class:`Lines`：在背景執行緒讀取子程序的標準輸出，一行一個，讓呼叫端可以設逾時等待。
- M10.2：子程序也可以在錄製端那台執行（:class:`rpa_server.devices.RemoteProcess`）。這裡的函式
  只用到 :class:`ChildProcess` 的部分，兩種都適用；:func:`child_env` 另外記下要給子程序的變數，
  交給錄製端時只送這些（不送伺服器自己的環境變數）。
"""

import contextlib
import os
import queue
import signal
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final, Protocol

from rpa_core.i18n import ENV_VAR, Locale

__all__ = ["ChildEnv", "ChildProcess", "Launch", "Lines", "child_env", "launch", "send", "stop"]

_CLOSED: Final = object()


class _Writer(Protocol):
    def write(self, s: str, /) -> int: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class _Reader(Protocol):
    def __iter__(self) -> Iterator[str]: ...


class ChildProcess(Protocol):
    """子程序：:class:`subprocess.Popen` 用到的部分（錄製端的 RemoteProcess 也實作這些）。"""

    @property
    def stdin(self) -> _Writer | None: ...

    @property
    def stdout(self) -> _Reader | None: ...

    @property
    def pid(self) -> int: ...

    @property
    def returncode(self) -> int | None: ...

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...


type Launch = Callable[..., ChildProcess]
"""啟動子程序：``launch(command, *, env, log, cwd=None, pipes=True)``（見 :func:`launch`）。"""


class ChildEnv(dict[str, str]):
    """子程序的環境變數；``extra`` 是在伺服器的環境之外另外給的（語言、Secrets、登入設定）。"""

    def __init__(self, values: Mapping[str, str], extra: Mapping[str, str]) -> None:
        super().__init__(values)
        self.extra: dict[str, str] = dict(extra)


def child_env(locale: Locale, extra: Mapping[str, str] | None = None) -> ChildEnv:
    own = {"PYTHONIOENCODING": "utf-8", ENV_VAR: locale, **(extra or {})}
    return ChildEnv({**os.environ, **own}, own)


def launch(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    log: Path,
    cwd: Path | None = None,
    pipes: bool = True,
) -> subprocess.Popen[str]:
    """啟動子程序；標準錯誤寫進 log。pipes 為 True 時可以從標準輸入送命令、讀標準輸出。"""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as error:
        return subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE if pipes else subprocess.DEVNULL,
            stdout=subprocess.PIPE if pipes else error,
            stderr=error,
            env=dict(env),
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=os.name != "nt",
        )


def stop(process: ChildProcess, *, grace: float = 5.0) -> None:
    """結束子程序與它開的瀏覽器：先關標準輸入讓它自己結束，等不到就終止整個程序群組。

    錄製端的子程序（有 ``kill_tree``）由錄製端結束整個程序樹。
    """
    if process.poll() is None and process.stdin is not None:
        with contextlib.suppress(OSError, ValueError):
            process.stdin.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=grace)
    if process.poll() is None:
        kill_tree: Callable[[], object] | None = getattr(process, "kill_tree", None)
        if kill_tree is not None:
            kill_tree()
        elif os.name == "nt":  # pragma: no cover - Windows 在一鍵安裝腳本的 CI 涵蓋
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)


def send(process: ChildProcess, line: str) -> bool:
    """送一行命令；子程序已經結束時回傳 False。"""
    stdin = process.stdin
    if stdin is None or process.poll() is not None:
        return False
    try:
        stdin.write(line.rstrip("\n") + "\n")
        stdin.flush()
    except (OSError, ValueError):
        return False
    return True


class Lines:
    """在背景讀取子程序標準輸出的每一行。"""

    def __init__(self, process: ChildProcess) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread = threading.Thread(target=self._read, args=(process,), daemon=True)
        self._thread.start()

    def _read(self, process: ChildProcess) -> None:
        stream = process.stdout
        if stream is not None:
            with contextlib.suppress(OSError, ValueError):
                for line in stream:
                    self._queue.put(line.rstrip("\n"))
        self._queue.put(_CLOSED)

    def get(self, timeout: float | None) -> str | None:
        """下一行；逾時拋出 TimeoutError，子程序已經關閉輸出時回傳 None。"""
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None
        if item is _CLOSED:
            self._queue.put(_CLOSED)  # 之後再讀也一樣得到 None
            return None
        return str(item)
