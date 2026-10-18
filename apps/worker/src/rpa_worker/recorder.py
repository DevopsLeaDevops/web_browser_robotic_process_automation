"""錄製端（M10.2，ADR 0014）：在這台執行管理 Portal 交來的互動子程序（錄製、逐步調試、人工登入）。

``rpa recorder`` 與 RPA 錄製端 App 共用。流程見 :mod:`rpa_worker.interactive`::

    hello（上線、這次啟動的代號）→ control 長輪詢 → 收到 start：在暫存資料夾寫出檔案，
      用這台的 Python（或打包後的 App）執行同一個模組 → 每一行輸出前先傳回改過的檔案
      → 結束時同步一次、回報結束碼 → 刪除暫存資料夾（可能有 Secrets 與登入狀態）

- 連不上管理 Portal 時逐步拉長間隔重試（最多 30 秒），恢復後重新上線；子程序照常執行，
  輸出與檔案等連上再送（順序不變）。管理 Portal 回 404（已經判定失聯、或重新啟動過）時結束子程序。
- 權杖被拒（401／403）或協定版本不同時呼叫 ``notify("rejected", …)`` 並停止。
- Secrets 只在記憶體與子程序的環境變數；暫存資料夾只有本人能讀寫，用完刪除（啟動時也清掉上次
  沒刪掉的）。
- 只執行錄製、逐步調試、人工登入的模組（:data:`MODULES`），也不接受會改變直譯器或載入程式庫的
  環境變數：連線是區網裡的 HTTP，不讓偽造的指令在這台執行任意程式。
- 每次輪詢附上正在執行的子程序；上線時管理 Portal 給的通道代號換了（重新啟動過），指令序號從
  0 重新開始。
"""

import contextlib
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, Final, cast

from rpa_runner.commands import module_command, no_window_flags
from rpa_worker.interactive import (
    CONTROL_WAIT_SECONDS,
    WORK,
    b64decode,
    changed_files,
    is_safe_relative,
    pack_files,
    scan,
)
from rpa_worker.pairing import CLIENT_API_PREFIX
from rpa_worker.remote import ConnectionLostError, WorkerApiError, WorkerClient

__all__ = ["RecorderHost", "translate"]

logger = logging.getLogger("rpa_worker.recorder")

MAX_BACKOFF_SECONDS: Final = 30.0
_KILL_GRACE_SECONDS: Final = 5.0
_CLEANUP_SECONDS: Final = 10.0
"""結束時最多等這麼久，讓子程序把最後的檔案與結束碼傳回去，再刪暫存資料夾。"""
MODULES: Final = frozenset({"rpa_runner.record", "rpa_runner.debug", "rpa_runner.login"})
"""管理 Portal 可以要這台執行的模組；另外 ``playwright`` 只接受 ``codegen``（錄製）。"""
_ENV_ALLOWED: Final = frozenset({"PYTHONIOENCODING", "PYTHONUTF8"})
_ENV_DENIED_PREFIXES: Final = ("PYTHON", "NODE_", "DYLD_", "LD_", "PLAYWRIGHT_", "BASH_")
_ENV_DENIED: Final = frozenset({"PATH", "HOME", "SHELL", "ENV", "IFS", "TMPDIR", "PERL5OPT"})
_FATAL_STATUSES: Final = frozenset({400, 413, 422})
"""回報子程序時這些錯誤重試也不會好：結束那個子程序。"""

Notify = Callable[[str, Mapping[str, object]], None]
"""通知顯示給人看的地方：事件名稱與內容（見 :class:`RecorderHost`）。"""
Command = Callable[[str, Sequence[str]], list[str]]
"""模組與參數 → 這台要執行的命令（預設 :func:`rpa_runner.commands.module_command`）。"""


def translate(value: str, folder: Path) -> str:
    """管理 Portal 寫的 :data:`WORK` 換成這台的工作資料夾。"""
    if value == WORK:
        return str(folder)
    if value.startswith(WORK + "/"):
        relative = value[len(WORK) + 1 :]
        if is_safe_relative(relative):
            return str(folder / relative)
    return value


def check_module(module: str, args: Sequence[str]) -> None:
    """只執行錄製、逐步調試、人工登入；其他的拋出 ValueError。"""
    if module in MODULES or (module == "playwright" and list(args[:1]) == ["codegen"]):
        return
    raise ValueError(f"module not allowed: {module!r}")


def check_env(name: str) -> None:
    """會改變直譯器、Node 或動態載入的環境變數不接受（Secrets、語言、登入設定可以）。"""
    upper = name.upper()
    if upper in _ENV_ALLOWED:
        return
    if not name or "=" in name or upper in _ENV_DENIED or upper.startswith(_ENV_DENIED_PREFIXES):
        raise ValueError(f"environment variable not allowed: {name!r}")


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":  # pragma: no cover - Windows 版錄製端在保留方案
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
            creationflags=no_window_flags(),
        )
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=10)


class _Child:
    """一個互動子程序：寫出檔案、執行、把輸出與檔案送回管理 Portal。"""

    def __init__(
        self,
        host: "RecorderHost",
        process_id: str,
        spec: Mapping[str, object],
    ) -> None:
        self.host = host
        self.id = process_id
        self.module = str(spec.get("module") or "")
        self.folder = Path(tempfile.mkdtemp(prefix=f"rpa-{process_id}-", dir=host.work_dir))
        self.pipes = spec.get("pipes") is not False
        log = str(spec.get("log") or "child.log")
        if not is_safe_relative(log):
            raise ValueError(f"unsafe log name: {log!r}")
        self.log = self.folder / log
        self.lock = threading.Lock()
        """同步與回報輸出依序進行。"""
        self.lost = False
        """管理 Portal 已經不認這個子程序（404）：不再回報。"""
        try:
            self.process = self._start(spec)
        except BaseException:
            shutil.rmtree(self.folder, ignore_errors=True)
            raise
        self.thread = threading.Thread(
            target=self._follow, name=f"recorder-{process_id}", daemon=True
        )

    def follow(self) -> None:
        """開始讀輸出（先登記到 RecorderHost 再呼叫：很快結束的子程序才不會先被忘掉）。"""
        self.thread.start()

    def _start(self, spec: Mapping[str, object]) -> subprocess.Popen[bytes]:
        files = cast("dict[object, object]", spec.get("files") or {})
        for name, content in files.items():
            if not isinstance(name, str) or not is_safe_relative(name):
                raise ValueError(f"unsafe file name: {name!r}")
            target = self.folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b64decode(content))
        self.snapshot = scan(self.folder)
        """已經在管理 Portal 那邊的檔案（送來的輸入檔）：沒有改就不傳回。"""
        module = self.module
        raw_args = cast("list[object]", spec.get("args") or [])
        args = [translate(str(item), self.folder) for item in raw_args]
        check_module(module, args)
        extra = cast("dict[object, object]", spec.get("env") or {})
        env = {**os.environ}
        for key, value in extra.items():
            check_env(str(key))
            env[str(key)] = translate(str(value), self.folder)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("ab") as error:
            return subprocess.Popen(
                self.host.command(module, args),
                stdin=subprocess.PIPE if self.pipes else subprocess.DEVNULL,
                stdout=subprocess.PIPE if self.pipes else error,
                stderr=error,
                env=env,
                cwd=self.folder,
                start_new_session=os.name != "nt",
                creationflags=no_window_flags(),
            )

    # ------------------------------------------------------------ 輸入

    def write(self, line: str) -> None:
        stdin = self.process.stdin
        if stdin is None or self.process.poll() is not None:
            return
        try:
            stdin.write((line.rstrip("\n") + "\n").encode("utf-8"))
            stdin.flush()
        except (OSError, ValueError):
            pass

    def close_input(self) -> None:
        stdin = self.process.stdin
        if stdin is not None:
            with contextlib.suppress(OSError, ValueError):
                stdin.close()

    def kill(self) -> None:
        _kill_tree(self.process)

    # ------------------------------------------------------------ 輸出

    def _follow(self) -> None:
        stream: IO[bytes] | None = self.process.stdout
        if stream is not None:
            with contextlib.suppress(OSError, ValueError):
                for raw in stream:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    self._report([line])
        code = self.process.wait()
        self._report([], exit_code=code)
        self.host.forget(self)

    def _sync(self) -> None:
        """傳回新增或改過的檔案（失敗時下次再傳）。"""
        now = scan(self.folder)
        names = changed_files(self.snapshot, now)
        if not names:
            return
        handle, name = tempfile.mkstemp(
            prefix=f".rpa-{self.id}-", suffix=".zip", dir=self.folder.parent
        )
        os.close(handle)  # mkstemp 建的檔案只有本人能讀寫
        archive = Path(name)
        try:
            pack_files(self.folder, names, archive)
            with archive.open("rb") as body:
                self.host.call(
                    "PUT",
                    f"/processes/{self.id}/files",
                    body=body,
                    content_type="application/zip",
                    length=archive.stat().st_size,
                )
        finally:
            archive.unlink(missing_ok=True)
        self.snapshot.update({name: now[name] for name in names})

    def _report(self, lines: Sequence[str], exit_code: int | None = None) -> None:
        """先同步檔案再送輸出；連不上時一直重試（子程序照常執行），404 時結束子程序。"""
        with self.lock:
            delay = 1.0
            while not self.lost:
                try:
                    self._sync()
                    payload: dict[str, object] = {"lines": list(lines)}
                    if exit_code is not None:
                        payload["exit"] = exit_code
                    self.host.call("POST", f"/processes/{self.id}/output", payload)
                    return
                except WorkerApiError as error:
                    if error.status in (404, 409) or error.status in _FATAL_STATUSES:
                        logger.info("管理 Portal 不再接受子程序 %s：%s", self.id, error.message)
                        self.lost = True
                        self.kill()
                        return
                    if error.status in (401, 403):
                        self.lost = True
                        self.kill()
                        self.host.reject(error.message)
                        return
                    logger.warning("回報子程序 %s 失敗：%s", self.id, error)
                except (ConnectionLostError, OSError) as error:
                    logger.info("回報子程序 %s 時連不上：%s", self.id, error)
                if self.host.stopping.wait(delay):
                    return
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)

    def cleanup(self) -> None:
        if not self.host.keep:
            shutil.rmtree(self.folder, ignore_errors=True)


class RecorderHost:
    """實作錄製端：上線、輪詢指令、執行互動子程序。

    通知的事件（``notify``）：``online``（上線，含 sameVersion、fingerprint）、``offline``
    （連不上，含原因）、``started``／``finished``（子程序開始、結束，含 module、process）、
    ``rejected``（權杖或協定版本被拒，停止）。
    """

    def __init__(
        self,
        client: WorkerClient,
        info: Mapping[str, object],
        work_dir: Path,
        *,
        notify: Notify | None = None,
        command: Command = module_command,
        keep: bool = False,
        wait_seconds: float = CONTROL_WAIT_SECONDS,
    ) -> None:
        if client.base != client.server + CLIENT_API_PREFIX:
            raise ValueError("the recorder uses the Client API")
        self.client = client
        self.info = dict(info)
        self.boot = uuid.uuid4().hex
        """這次啟動的代號：管理 Portal 看到不同的代號時，結束上一次留下的子程序。"""
        self.work_dir = work_dir
        self.notify: Notify = notify or (lambda event, details: None)
        self.command = command
        self.keep = keep
        self.wait_seconds = wait_seconds
        self.stopping = threading.Event()
        self.rejected: str | None = None
        self._children: dict[str, _Child] = {}
        self._lock = threading.Lock()
        self._after = 0
        self._channel: object = None
        """管理 Portal 這次的通道代號（上線時拿到）。"""
        self._online = False

    # ------------------------------------------------------------ 連線

    def call(
        self,
        method: str,
        path: str,
        payload: object = None,
        *,
        body: IO[bytes] | None = None,
        content_type: str | None = None,
        length: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        return self.client.call(
            method,
            path,
            payload,
            body=body,
            content_type=content_type,
            length=length,
            timeout=timeout,
        )

    def reject(self, message: str) -> None:
        if self.rejected is None:
            self.rejected = message
            self.notify("rejected", {"message": message})
        self.stopping.set()

    def _hello(self) -> None:
        reply = self.call("POST", "/hello", {**self.info, "boot": self.boot})
        channel, seq = reply.get("channel"), reply.get("seq")
        if channel != self._channel:
            # 管理 Portal 重新啟動過（或通道重建）：那邊的序號從 0 開始
            self._channel = channel
            self._after = 0
        elif isinstance(seq, int) and seq < self._after:
            self._after = seq
        self._online = True
        self.notify(
            "online",
            {
                "device": reply.get("device"),
                "sameVersion": reply.get("sameVersion"),
                "fingerprint": self.info.get("fingerprint"),
                "serverFingerprint": reply.get("fingerprint"),
            },
        )

    def run(self, stop: threading.Event | None = None) -> str | None:
        """一直執行到 ``stop``（或權杖被拒）；結束時結束所有子程序。回傳被拒的原因。"""
        stop = stop or threading.Event()
        threading.Thread(target=lambda: (stop.wait(), self.stopping.set()), daemon=True).start()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._sweep()
        delay = 1.0
        try:
            while not self.stopping.is_set():
                try:
                    if not self._online:
                        self._hello()
                    with self._lock:
                        running = sorted(self._children)
                    reply = self.call(
                        "POST",
                        "/control",
                        {"after": self._after, "wait": self.wait_seconds, "running": running},
                        timeout=self.wait_seconds + 30,
                    )
                    delay = 1.0
                    commands = cast("list[object]", reply.get("commands") or [])
                    for item in commands:
                        if isinstance(item, dict):
                            command = cast("dict[str, object]", item)
                            try:
                                self._handle(command)
                            except Exception:
                                logger.exception("處理指令失敗：%s", command.get("type"))
                except WorkerApiError as error:
                    if error.status in (401, 403) or error.code == "protocol_mismatch":
                        self.reject(error.message)
                        break
                    if error.code == "recorder_hello_first":
                        self._online = False
                        continue
                    self._offline(str(error))
                    if self.stopping.wait(delay):
                        break
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                except ConnectionLostError as error:
                    self._offline(str(error))
                    if self.stopping.wait(delay):
                        break
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                except Exception as error:
                    # 預期外的回應（例如中間的代理回了不是 JSON 的內容）：當作離線，稍後重試
                    logger.exception("和管理 Portal 通訊時出錯")
                    self._offline(f"{type(error).__name__}: {error}")
                    if self.stopping.wait(delay):
                        break
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
        finally:
            self.stop_all()
        return self.rejected

    def _offline(self, reason: str) -> None:
        if self._online:
            self.notify("offline", {"server": self.client.server, "reason": reason})
        self._online = False

    # ------------------------------------------------------------ 指令

    def _handle(self, command: Mapping[str, object]) -> None:
        seq = command.get("seq")
        if not isinstance(seq, int) or seq <= self._after:
            return
        self._after = seq
        kind = command.get("type")
        process_id = str(command.get("process") or "")
        with self._lock:
            child = self._children.get(process_id)
        if kind == "start":
            if child is not None or not process_id.isalnum():
                return
            try:
                child = _Child(self, process_id, command)
            except (OSError, ValueError) as error:
                logger.warning("啟動子程序 %s 失敗：%s", process_id, error)
                self._fail(process_id, f"{type(error).__name__}: {error}")
                return
            with self._lock:
                self._children[process_id] = child
            child.follow()
            self.notify("started", {"module": command.get("module"), "process": process_id})
        elif child is None:
            return
        elif kind == "input":
            child.write(str(command.get("line") or ""))
        elif kind == "close":
            child.close_input()
        elif kind == "kill":
            threading.Thread(target=child.kill, daemon=True).start()

    def _fail(self, process_id: str, message: str) -> None:
        """在這台啟動不了：告訴管理 Portal 這個子程序結束了（原因寫進那邊的日誌）。"""
        with contextlib.suppress(WorkerApiError, ConnectionLostError):
            payload: dict[str, object] = {"lines": [], "exit": 1, "error": message}
            self.call("POST", f"/processes/{process_id}/output", payload)
        logger.warning("子程序 %s 無法啟動：%s", process_id, message)

    def forget(self, child: _Child) -> None:
        with self._lock:
            self._children.pop(child.id, None)
        child.cleanup()
        self.notify(
            "finished",
            {"process": child.id, "module": child.module, "exit": child.process.returncode},
        )

    def active(self) -> int:
        """這台正在執行的互動子程序數量。"""
        with self._lock:
            return len(self._children)

    def stop_all(self) -> None:
        """結束時：先關標準輸入讓子程序自己結束（調試會關掉瀏覽器），等不到就結束整個程序樹；
        再等一下讓結果傳回去，最後一定刪掉暫存資料夾（可能有登入狀態與沒遮罩的錄製稿）。"""
        self.stopping.set()
        with self._lock:
            children = list(self._children.values())
        for child in children:
            child.close_input()
        deadline = time.monotonic() + _KILL_GRACE_SECONDS
        for child in children:
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.process.wait(timeout=max(0.1, deadline - time.monotonic()))
            child.kill()
        deadline = time.monotonic() + _CLEANUP_SECONDS
        for child in children:
            if child.thread.is_alive():
                child.thread.join(timeout=max(0.1, deadline - time.monotonic()))
            child.cleanup()

    def _sweep(self) -> None:
        """刪掉上次沒刪掉的暫存資料夾與上傳檔（例如上次被強制結束）。"""
        if self.keep:
            return
        for item in self.work_dir.glob("rpa-*"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        for item in self.work_dir.glob(".rpa-*.zip"):
            item.unlink(missing_ok=True)
