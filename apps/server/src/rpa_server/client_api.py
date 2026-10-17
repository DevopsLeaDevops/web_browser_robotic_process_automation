"""Client API（/client-api/v1）：桌面 App 與管理 Portal 之間的介面（M10，ADR 0014）。

- 只在對外埠提供（``rpa serve --worker-port``），管理頁面的埠沒有這些路徑
  （:class:`rpa_server.middleware.PortGateMiddleware`）。
- M10.1 只有 ``POST /pair``：用裝置頁產生的邀請代碼換權杖；不需要權杖。
  M10.2 的錄製端再加上 ``/hello``、``/control`` 與子程序的輸出、檔案（見桌面端分發的設計）。
- 錯誤一律是 ``{"error": {"code": …, "message": …}}``：401 代碼不對、已用過或過期；
  409 邀請的 App 種類不對（``invite_wrong_app``，代碼保留）或裝置已停用；422 內容不對。
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from rpa_server.dispatch import WorkerHub
from rpa_worker.pairing import CLIENT_API_PREFIX, App

__all__ = ["client_api_router"]


class PairBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(min_length=1, max_length=200)
    app: App


def client_api_router(hub: WorkerHub) -> APIRouter:
    router = APIRouter(prefix=CLIENT_API_PREFIX)

    @router.post("/pair")
    def pair(body: PairBody) -> dict[str, object]:
        """用邀請代碼換權杖；權杖只在這個回應裡出現一次。"""
        return hub.pair(body.code, body.app)

    return router
