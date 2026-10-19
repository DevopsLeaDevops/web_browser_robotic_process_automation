"""Worker API（/worker-api/v1）：遠端 worker 領取任務、回報進度與結果（M9a，ADR 0012）。

- 每個請求都要 ``Authorization: Bearer <權杖>``（管理 Portal 的「Worker」頁產生）。
- 只在 Worker API 的埠提供（``rpa serve --worker-port``）；管理頁面的埠沒有這些路徑，
  Worker API 的埠也沒有管理頁面（:class:`rpa_server.middleware.PortGateMiddleware`）。
- 錯誤一律是 ``{"error": {"code": …, "message": …}}``：401 權杖不對、409 這個執行已經不歸你
  （例如被判定失聯）或協定版本不同、413 上傳太大、422 內容不對。
"""

import uuid
from pathlib import Path
from typing import Annotated, Final

import anyio
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from rpa_server.dispatch import WorkerHub
from rpa_server.errors import ServiceError
from rpa_server.i18n import t
from rpa_worker.protocol import API_PREFIX, CLAIM_WAIT_SECONDS, MAX_ARTIFACT_BYTES

__all__ = ["save_upload", "worker_api_router"]

MAX_STATE_BYTES: Final = 5 * 1024 * 1024


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ClaimBody(_Body):
    waitSeconds: float = Field(default=CLAIM_WAIT_SECONDS, ge=0, le=CLAIM_WAIT_SECONDS)  # noqa: N815


class HeartbeatBody(_Body):
    stage: str | None = Field(default=None, max_length=20)


class FinishBody(_Body):
    result: dict[str, object]


class FailBody(_Body):
    kind: str = Field(max_length=40)
    detail: str = Field(default="", max_length=10_000)


def _too_large() -> ServiceError:
    return ServiceError(413, "upload_too_large", t("error.upload_too_large"))


async def save_upload(request: Request, limit: int, folder: Path) -> Path:
    """把上傳內容一段一段寫到暫存檔（不整個放進記憶體），超過 limit 就拒絕。"""
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > limit:
        raise _too_large()
    directory = anyio.Path(folder)
    await directory.mkdir(parents=True, exist_ok=True)
    path = directory / f".upload-{uuid.uuid4().hex}.zip"
    size = 0
    try:
        async with await anyio.open_file(path, "wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise _too_large()
                await handle.write(chunk)
    except BaseException:
        await path.unlink(missing_ok=True)
        raise
    return Path(path)


def worker_api_router(hub: WorkerHub) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    def current_worker(authorization: Annotated[str | None, Header()] = None) -> str:
        token = None
        if authorization is not None and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        return hub.authenticate(token)

    @router.post("/hello")
    def hello(
        worker: Annotated[str, Depends(current_worker)], body: dict[str, object]
    ) -> dict[str, object]:
        return hub.hello(worker, body)

    @router.post("/claim", response_model=None)
    def claim(
        worker: Annotated[str, Depends(current_worker)], body: ClaimBody | None = None
    ) -> dict[str, object] | Response:
        wait = body.waitSeconds if body is not None else CLAIM_WAIT_SECONDS
        payload = hub.claim(worker, wait)
        return payload if payload is not None else Response(status_code=204)

    @router.post("/runs/{run_id}/heartbeat")
    def heartbeat(
        worker: Annotated[str, Depends(current_worker)],
        run_id: str,
        body: HeartbeatBody | None = None,
    ) -> dict[str, object]:
        return hub.heartbeat(worker, run_id, body.stage if body is not None else None)

    @router.put("/runs/{run_id}/artifacts", status_code=204)
    async def artifacts(
        worker: Annotated[str, Depends(current_worker)], run_id: str, request: Request
    ) -> Response:
        path = await save_upload(request, MAX_ARTIFACT_BYTES, hub.storage.runs)
        try:
            await anyio.to_thread.run_sync(hub.store_artifacts, worker, run_id, path)
        finally:
            await anyio.Path(path).unlink(missing_ok=True)
        return Response(status_code=204)

    @router.put("/runs/{run_id}/role-state", status_code=204)
    async def role_state(
        worker: Annotated[str, Depends(current_worker)], run_id: str, request: Request
    ) -> Response:
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_STATE_BYTES:
                raise _too_large()
        await anyio.to_thread.run_sync(hub.store_role_state, worker, run_id, data)
        return Response(status_code=204)

    @router.post("/runs/{run_id}/finish", status_code=204)
    def finish(
        worker: Annotated[str, Depends(current_worker)], run_id: str, body: FinishBody
    ) -> Response:
        hub.finish(worker, run_id, body.result)
        return Response(status_code=204)

    @router.post("/runs/{run_id}/fail", status_code=204)
    def fail(
        worker: Annotated[str, Depends(current_worker)], run_id: str, body: FailBody
    ) -> Response:
        hub.fail(worker, run_id, body.kind, body.detail)
        return Response(status_code=204)

    return router
