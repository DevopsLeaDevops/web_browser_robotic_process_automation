"""Client API（/client-api/v1）：桌面 App 與管理 Portal 之間的介面（M10，ADR 0014）。

- 只在對外埠提供（``rpa serve --worker-port``），管理頁面的埠沒有這些路徑
  （:class:`rpa_server.middleware.PortGateMiddleware`）。
- ``POST /pair``（M10.1）：用裝置頁產生的邀請代碼換權杖；不需要權杖。
- 錄製端（M10.2）：其他路徑都要 ``Authorization: Bearer <錄製端的權杖>``。``/hello`` 上線、
  ``/control`` 長輪詢取得指令，``/processes/<代號>/files`` 與 ``/output`` 傳回互動子程序的
  檔案與輸出。格式見 :mod:`rpa_worker.interactive`。
- 錯誤一律是 ``{"error": {"code": …, "message": …}}``：401 代碼或權杖不對、已用過或過期；
  404 子程序已經結束（例如判定失聯，錄製端要結束它）；409 邀請的 App 種類不對
  （``invite_wrong_app``，代碼保留）、裝置已停用或協定版本不同；413 上傳太大；422 內容不對。
"""

from typing import Annotated, Final

import anyio
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from rpa_server.context import Via
from rpa_server.devices import RecorderHub
from rpa_server.dispatch import WorkerHub
from rpa_server.storage import Storage
from rpa_server.worker_api import save_upload
from rpa_worker.interactive import CONTROL_WAIT_SECONDS, MAX_SYNC_BYTES
from rpa_worker.pairing import CLIENT_API_PREFIX, App

__all__ = ["client_api_router"]

MAX_LINES: Final = 1000


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PairBody(_Body):
    code: str = Field(min_length=1, max_length=200)
    app: App


class ControlBody(_Body):
    after: int = Field(default=0, ge=0)
    wait: float = Field(default=CONTROL_WAIT_SECONDS, ge=0, le=CONTROL_WAIT_SECONDS)
    running: list[str] | None = Field(default=None, max_length=1000)
    """錄製端正在執行的子程序；給了就和這邊對照（見 :meth:`RecorderHub.poll`）。"""


class OutputBody(_Body):
    lines: list[str] = Field(default_factory=list[str], max_length=MAX_LINES)
    exit: int | None = None
    error: str | None = Field(default=None, max_length=2000)
    """錄製端啟動不了子程序時的原因（寫進這邊的日誌）。"""


def client_api_router(hub: WorkerHub, recorders: RecorderHub, storage: Storage) -> APIRouter:
    router = APIRouter(prefix=CLIENT_API_PREFIX)

    @router.post("/pair")
    def pair(body: PairBody) -> dict[str, object]:
        """用邀請代碼換權杖；權杖只在這個回應裡出現一次。"""
        return hub.pair(body.code, body.app)

    def current_recorder(authorization: Annotated[str | None, Header()] = None) -> Via:
        token = None
        if authorization is not None and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        return recorders.authenticate(token)

    @router.post("/hello")
    def hello(
        recorder: Annotated[Via, Depends(current_recorder)], body: dict[str, object]
    ) -> dict[str, object]:
        return recorders.hello(recorder.id, body)

    @router.post("/control")
    def control(
        recorder: Annotated[Via, Depends(current_recorder)], body: ControlBody | None = None
    ) -> dict[str, object]:
        body = body or ControlBody()
        return recorders.poll(recorder.id, body.after, body.wait, body.running)

    @router.post("/processes/{process_id}/output", status_code=204)
    def output(
        recorder: Annotated[Via, Depends(current_recorder)], process_id: str, body: OutputBody
    ) -> Response:
        recorders.output(recorder.id, process_id, body.lines, body.exit, body.error)
        return Response(status_code=204)

    @router.put("/processes/{process_id}/files", status_code=204)
    async def files(
        recorder: Annotated[Via, Depends(current_recorder)], process_id: str, request: Request
    ) -> Response:
        path = await save_upload(request, MAX_SYNC_BYTES, storage.root / "uploads")
        try:
            await anyio.to_thread.run_sync(recorders.store_files, recorder.id, process_id, path)
        finally:
            await anyio.Path(path).unlink(missing_ok=True)
        return Response(status_code=204)

    return router
