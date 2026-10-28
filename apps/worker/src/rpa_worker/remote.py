"""遠端 worker 的任務來源：經由管理 Portal 的 Worker API 領取任務、回報進度與結果（M9a，ADR 0012）。

worker 機器只需要連得到管理 Portal 的 Worker API（HTTP＋權杖），不碰資料庫。流程::

    hello（上線、協定版本）→ claim（長輪詢）→ 寫出場景檔、登入狀態暫存檔
      → 執行中每 5 秒 heartbeat（回應要求取消就取消）
      → 上傳執行目錄（zip）→ 登入狀態有變就傳回 → finish（結果）→ 刪除本機的暫存

- 連不上管理 Portal 時逐步拉長間隔重試（最多 30 秒），恢復後重新上線；只在狀態改變時通知一次。
- 權杖被拒（401／403）或協定版本不同時，呼叫 ``on_fatal``，由命令列停止 worker。
- 回報結果時連不上就一直重試（最多 10 分鐘，心跳照常，租約不會過期）；
  管理 Portal 回 409（例如已經判定 worker 失聯）就放棄這次的回報。
- Secrets 只在記憶體；登入狀態暫存檔只有本人能讀寫，執行完刪除。
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Final, cast

from rpa_runner.run import RunResult, ScenarioInvalidError, StageName
from rpa_worker.environment import WorkerInfo
from rpa_worker.protocol import (
    API_PREFIX,
    CLAIM_WAIT_SECONDS,
    HEARTBEAT_SECONDS,
    InputFile,
    JobPayload,
    is_safe_path,
    pack_directory,
)
from rpa_worker.worker import Job

__all__ = [
    "ConnectionLostError",
    "RemoteJobSource",
    "WorkerApiError",
    "WorkerClient",
]

logger = logging.getLogger("rpa_worker.remote")

MAX_BACKOFF_SECONDS: Final = 30.0
DELIVERY_SECONDS: Final = 600.0
"""回報結果最多重試這麼久。"""

Notify = Callable[[str, Mapping[str, object]], None]
"""通知命令列（顯示給人看）：事件名稱與內容。事件見 :class:`RemoteJobSource`。"""


class WorkerApiError(Exception):
    """管理 Portal 回應錯誤（HTTP 4xx、5xx）。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class ConnectionLostError(Exception):
    """連不上管理 Portal（網路、逾時、伺服器沒有啟動）。"""


class WorkerClient:
    """Worker API 的 HTTP 用戶端（標準函式庫，不加相依）。區網位址不經過系統代理。

    配對（M10.1）也用它：``prefix`` 換成 Client API，配對前沒有權杖（``token`` 為 None）。
    """

    def __init__(
        self,
        server: str,
        token: str | None,
        *,
        prefix: str = API_PREFIX,
        timeout: float = 30.0,
    ) -> None:
        self.server = server.rstrip("/")
        self.base = self.server + prefix
        self.token = token
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(
        self,
        method: str,
        path: str,
        payload: object = None,
        *,
        body: bytes | IO[bytes] | None = None,
        content_type: str | None = None,
        length: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        """送出請求，回傳 JSON 物件（204 回傳空物件）。"""
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data: bytes | IO[bytes] | None = body
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        if content_type is not None:
            headers["Content-Type"] = content_type
        if length is not None:
            headers["Content-Length"] = str(length)
        request = urllib.request.Request(
            self.base + path, data=cast("bytes | None", data), headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raise _api_error(error) from None
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            reason = getattr(error, "reason", None) or error
            raise ConnectionLostError(str(reason)) from None
        if status == 204 or not raw:
            return {}
        data_out: object = json.loads(raw)
        return cast("dict[str, object]", data_out) if isinstance(data_out, dict) else {}

    def download(
        self, path: str, destination: Path, *, limit: int, timeout: float | None = None
    ) -> int:
        """GET 一個檔案，一段一段寫到 ``destination``；超過 ``limit`` 位元組就停。回傳大小。

        寫到一半失敗時刪掉 ``destination``。錯誤和 :meth:`call` 相同。
        """
        headers = {"Accept": "application/octet-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base + path, headers=headers, method="GET")
        size = 0
        try:
            with (
                self._opener.open(request, timeout=timeout or self.timeout) as response,
                destination.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ConnectionLostError(f"larger than {limit} bytes")
                    output.write(chunk)
        except urllib.error.HTTPError as error:
            destination.unlink(missing_ok=True)
            raise _api_error(error) from None
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            destination.unlink(missing_ok=True)
            reason = getattr(error, "reason", None) or error
            raise ConnectionLostError(str(reason)) from None
        except ConnectionLostError:
            destination.unlink(missing_ok=True)
            raise
        return size


def _api_error(error: urllib.error.HTTPError) -> WorkerApiError:
    """HTTP 錯誤換成 :class:`WorkerApiError`（讀出管理 Portal 的錯誤代碼與說明）。"""
    code, message = "http_error", error.reason
    try:
        detail: object = json.loads(error.read() or b"{}")
        info = cast("dict[str, object]", detail).get("error") if isinstance(detail, dict) else None
        if isinstance(info, dict):
            values = cast("dict[str, object]", info)
            code = str(values.get("code") or code)
            message = str(values.get("message") or message)
    except (ValueError, OSError):
        pass
    return WorkerApiError(error.code, code, str(message))


@dataclass(slots=True)
class _Active:
    """執行中的任務。"""

    job: Job
    folder: Path
    state_path: Path | None
    state_digest: str | None
    stage: StageName | None = None
    lost: bool = False
    """管理 Portal 已經不認這個執行（例如判定失聯）；結果不再回報。"""
    stop: threading.Event = field(default_factory=threading.Event)
    poke: threading.Event = field(default_factory=threading.Event)
    """進入新的階段：心跳執行緒馬上回報一次（不讓執行等網路）。"""
    thread: threading.Thread | None = None


def _digest(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_private(path: Path, data: bytes) -> None:
    """寫出只有本人能讀寫的檔案。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


class RemoteJobSource:
    """實作 :class:`rpa_worker.JobSource`：任務來自管理 Portal 的 Worker API。

    通知命令列的事件（``notify``）：``online``（上線，含 server、fingerprint 是否相同）、
    ``offline``（連不上，含原因）、``claimed``（領到任務）、``reported``（回報了結果）、
    ``abandoned``（管理 Portal 不再接受這次的結果）、``report_failed``（重試到上限仍失敗）、
    ``rejected``（權杖或協定版本被拒，worker 會停止）、``paused``（暫停接任務，見 ``paused``）、
    ``done``（這台電腦上的執行結束了，不論結果有沒有送達；含 run）。

    ``paused``（M10.1 的 Worker App）：設定時不再領取新任務，執行中的照常做完並回報；
    不送任何請求，管理 Portal 約一分鐘後顯示離線。清除後重新上線（hello）再領取。
    """

    def __init__(
        self,
        client: WorkerClient,
        info: WorkerInfo,
        work_dir: Path,
        *,
        keep_runs: bool = False,
        notify: Notify | None = None,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
        claim_wait_seconds: float = CLAIM_WAIT_SECONDS,
        delivery_seconds: float = DELIVERY_SECONDS,
        paused: threading.Event | None = None,
        input_folders: Callable[[], Sequence[Path]] | None = None,
    ) -> None:
        self.client = client
        self.info = info
        self.work_dir = work_dir
        self.keep_runs = keep_runs
        self.input_folders = input_folders
        """檔案入參的 path 可以讀的資料夾（M7c D5，Worker App 的設定）；每個任務開始時讀一次。
        沒有設定時 runner 讀環境變數 RPA_INPUT_FOLDERS。"""
        self.notify: Notify = notify or (lambda event, details: None)
        self.heartbeat_seconds = heartbeat_seconds
        self.claim_wait_seconds = claim_wait_seconds
        self.delivery_seconds = delivery_seconds
        self.paused = paused
        self._paused_reported = False
        self.on_cancel: Callable[[str], object] = lambda run_id: None
        """管理 Portal 要求取消（由命令列接到 :meth:`rpa_worker.Worker.cancel`）。"""
        self.on_fatal: Callable[[str], None] = lambda message: None
        """權杖或協定版本被拒：worker 不能再工作。"""
        self._lock = threading.Lock()
        self._active: dict[str, _Active] = {}
        self._online = False
        self._offline_reported = False
        self._backoff = 1.0
        self._closing = threading.Event()

    # ------------------------------------------------------------ 位置

    @property
    def runs_dir(self) -> Path:
        return self.work_dir / "runs"

    @property
    def jobs_dir(self) -> Path:
        return self.work_dir / "jobs"

    def close(self) -> None:
        """停止重試與等待（命令列結束時）。"""
        self._closing.set()

    # ------------------------------------------------------------ 連線

    def hello(self) -> dict[str, object]:
        """上線：告訴管理 Portal 這台 worker 的資訊。被拒時拋出 WorkerApiError。"""
        reply = self.client.call("POST", "/hello", self.info.to_json())
        same = reply.get("fingerprint") in (None, self.info.fingerprint)
        self._online = True
        self._offline_reported = False
        self._backoff = 1.0
        self.notify(
            "online",
            {
                "server": self.client.server,
                "worker": reply.get("worker"),
                "sameVersion": same,
                "serverFingerprint": reply.get("fingerprint"),
                "fingerprint": self.info.fingerprint,
            },
        )
        return reply

    def _offline(self, error: Exception) -> None:
        if not self._offline_reported:
            self.notify("offline", {"server": self.client.server, "reason": str(error)})
            self._offline_reported = True
        self._online = False
        self._closing.wait(self._backoff)
        self._backoff = min(self._backoff * 2, MAX_BACKOFF_SECONDS)

    def _rejected(self, error: WorkerApiError) -> None:
        self.notify(
            "rejected", {"status": error.status, "code": error.code, "message": error.message}
        )
        self._closing.set()
        self.on_fatal(error.message)

    @staticmethod
    def _fatal(error: WorkerApiError) -> bool:
        return error.status in (401, 403) or error.code == "protocol_mismatch"

    # ------------------------------------------------------------ JobSource

    def claim(self) -> Job | None:
        if self._closing.is_set():
            return None
        if self.paused is not None and self.paused.is_set():
            if not self._paused_reported:
                self._paused_reported = True
                self._online = False  # 恢復時重新 hello，管理 Portal 立刻看到上線
                self.notify("paused", {"server": self.client.server})
            self._closing.wait(1.0)
            return None
        self._paused_reported = False
        try:
            if not self._online:
                self.hello()
            reply = self.client.call(
                "POST",
                "/claim",
                {"waitSeconds": self.claim_wait_seconds},
                timeout=self.claim_wait_seconds + 15,
            )
        except ConnectionLostError as error:
            self._offline(error)
            return None
        except WorkerApiError as error:
            if self._fatal(error):
                self._rejected(error)
            else:
                logger.warning("領取任務失敗：%s", error)
                self._offline(error)
            return None
        if not reply:
            return None
        return self._accept(reply)

    def _accept(self, reply: Mapping[str, object]) -> Job | None:
        run_id = str(reply.get("runId") or "")
        safe_id = run_id if is_safe_path(run_id) and "/" not in run_id else "invalid"
        folder = self.jobs_dir / safe_id
        shutil.rmtree(folder, ignore_errors=True)
        try:
            payload = JobPayload.from_json(reply, state_path=folder / "state.json")
        except ValueError as error:
            logger.warning("任務格式不正確：%s", error)
            if safe_id != "invalid":
                self._send_fail(run_id, "crashed", f"invalid job: {error}")
            return None
        scenario_dir = folder / "scenario"
        for name, content in payload.files.items():
            target = scenario_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)  # 照位元組寫出：雜湊要和管理 Portal 的版本一致
        state_path = payload.login.state if payload.login is not None else None
        if state_path is not None and payload.login_state is not None:
            _write_private(state_path, payload.login_state)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.runs_dir / payload.run_id, ignore_errors=True)
        # 上傳檔（M7c）：位置先決定，心跳開始之後才下載（大檔下載時租約不會過期）
        inputs_dir = folder / "inputs"
        folders = tuple(self.input_folders()) if self.input_folders is not None else ()
        job = Job(
            run_id=payload.run_id,
            scenario=scenario_dir / payload.scenario_file,
            inputs=dict(payload.inputs),
            out_root=self.runs_dir,
            engine=payload.engine,
            base_url=payload.base_url,
            deadline_ms=payload.deadline_ms,
            headless=payload.headless,
            login=payload.login,
            secrets=dict(payload.secrets),
            locale=payload.locale,
            record_video=payload.record_video,
            uploads={item.id: inputs_dir / item.id for item in payload.input_files},
            input_folders=folders or None,
            max_file_bytes=payload.max_file_bytes,
            max_run_bytes=payload.max_run_bytes,
        )
        active = _Active(job, folder, state_path, _digest(state_path))
        active.thread = threading.Thread(
            target=self._heartbeat_loop, args=(active,), name=f"heartbeat-{job.run_id}", daemon=True
        )
        with self._lock:
            self._active[job.run_id] = active
        active.thread.start()
        if payload.input_files:
            try:
                self._download_inputs(job.run_id, payload.input_files, inputs_dir)
            except (ConnectionLostError, WorkerApiError, OSError, ValueError) as error:
                logger.warning("下載上傳檔失敗（%s）：%s", job.run_id, error)
                self._send_fail(job.run_id, "input_files", str(error), retry=True)
                self._done(active, keep_run=False)
                return None
        self.notify("claimed", {"run": job.run_id, "headless": job.headless, "engine": job.engine})
        return job

    def _download_inputs(self, run_id: str, files: Sequence[InputFile], folder: Path) -> None:
        """下載任務用到的上傳檔（M7c），比對大小與 sha256；不符就拋出 ValueError。"""
        folder.mkdir(parents=True, exist_ok=True)
        for item in files:
            target = folder / item.id
            size = self.client.download(
                f"/runs/{run_id}/files/{item.id}", target, limit=item.size, timeout=120
            )
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if size != item.size or digest.hexdigest() != item.sha256:
                target.unlink(missing_ok=True)
                raise ValueError(f"file {item.id} does not match its sha256")

    def progress(self, job: Job, stage: StageName) -> None:
        active = self._get(job.run_id)
        if active is None:
            return
        active.stage = stage
        active.poke.set()

    def finish(self, job: Job, result: RunResult) -> None:
        active = self._get(job.run_id)
        if active is None:
            return
        try:
            if active.lost:
                self.notify("abandoned", {"run": job.run_id})
                return
            delivered = self._deliver_result(active, result)
            if delivered:
                self.notify("reported", {"run": job.run_id, "status": result.status})
        finally:
            self._done(active, keep_run=self.keep_runs)

    def fail(self, job: Job, error: Exception) -> None:
        active = self._get(job.run_id)
        try:
            if active is not None and active.lost:
                self.notify("abandoned", {"run": job.run_id})
                return
            if isinstance(error, ScenarioInvalidError):
                ok = self._send_fail(
                    job.run_id, "scenario_invalid", str(len(error.issues)), retry=True
                )
            else:
                ok = self._send_fail(
                    job.run_id, "crashed", f"{type(error).__name__}: {error}", retry=True
                )
            if ok:
                self.notify("reported", {"run": job.run_id, "status": "failed"})
        finally:
            if active is not None:
                self._done(active, keep_run=False)

    # ------------------------------------------------------------ 心跳

    def _get(self, run_id: str) -> _Active | None:
        with self._lock:
            return self._active.get(run_id)

    def _heartbeat_loop(self, active: _Active) -> None:
        while not active.stop.is_set():
            active.poke.wait(self.heartbeat_seconds)
            active.poke.clear()
            if active.stop.is_set():
                return
            self._heartbeat(active)

    def _heartbeat(self, active: _Active) -> None:
        if active.lost:
            return
        run_id = active.job.run_id
        try:
            reply = self.client.call(
                "POST", f"/runs/{run_id}/heartbeat", {"stage": active.stage}, timeout=10
            )
        except ConnectionLostError as error:
            logger.info("心跳失敗（%s）：%s", run_id, error)
            return
        except WorkerApiError as error:
            if error.status in (404, 409):
                # 管理 Portal 已經不認這個執行：停止執行，結果不再回報
                active.lost = True
                self.on_cancel(run_id)
            elif self._fatal(error):
                active.lost = True
                self.on_cancel(run_id)
                self._rejected(error)
            return
        if reply.get("cancel") is True:
            self.on_cancel(run_id)

    # ------------------------------------------------------------ 回報

    def _deliver(self, action: Callable[[], object], *, retry: bool = True) -> bool:
        """執行一次回報；連不上或伺服器錯誤時重試。回傳是否送達。"""
        deadline = time.monotonic() + self.delivery_seconds
        wait = 1.0
        while True:
            try:
                action()
                return True
            except WorkerApiError as error:
                if error.status < 500:
                    logger.warning("管理 Portal 不接受回報：%s", error)
                    if self._fatal(error):
                        self._rejected(error)
                    return False
                failure: Exception = error
            except ConnectionLostError as error:
                failure = error
            if not retry or time.monotonic() + wait > deadline or self._closing.is_set():
                self.notify("report_failed", {"reason": str(failure)})
                return False
            time.sleep(wait)
            wait = min(wait * 2, MAX_BACKOFF_SECONDS)

    def _deliver_result(self, active: _Active, result: RunResult) -> bool:
        run_id = active.job.run_id
        folder = self.runs_dir / run_id
        if folder.is_dir():
            archive = active.folder / "artifacts.zip"
            pack_directory(folder, archive)
            size = archive.stat().st_size

            def upload() -> None:
                with archive.open("rb") as handle:
                    self.client.call(
                        "PUT",
                        f"/runs/{run_id}/artifacts",
                        body=handle,
                        content_type="application/zip",
                        length=size,
                        timeout=300,
                    )

            if not self._deliver(upload):
                return False
        state = active.state_path
        if state is not None and result.role is not None and _digest(state) != active.state_digest:
            data = state.read_bytes()

            def send_state() -> None:
                self.client.call(
                    "PUT",
                    f"/runs/{run_id}/role-state",
                    body=data,
                    content_type="application/json",
                    length=len(data),
                )

            self._deliver(send_state)  # 送不到也不影響結果：下次執行再自動登入
        return self._deliver(
            lambda: self.client.call("POST", f"/runs/{run_id}/finish", {"result": result.to_json()})
        )

    def _send_fail(self, run_id: str, kind: str, detail: str, *, retry: bool = False) -> bool:
        return self._deliver(
            lambda: self.client.call(
                "POST", f"/runs/{run_id}/fail", {"kind": kind, "detail": detail[:2000]}
            ),
            retry=retry,
        )

    def _done(self, active: _Active, *, keep_run: bool) -> None:
        self.notify("done", {"run": active.job.run_id})
        active.stop.set()
        active.poke.set()
        if active.thread is not None and active.thread is not threading.current_thread():
            active.thread.join(timeout=15)
        with self._lock:
            self._active.pop(active.job.run_id, None)
        shutil.rmtree(active.folder, ignore_errors=True)
        if not keep_run:
            shutil.rmtree(self.runs_dir / active.job.run_id, ignore_errors=True)
