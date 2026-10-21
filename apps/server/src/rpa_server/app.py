"""組裝管理 Portal：資料庫、服務層、背景 worker、API 與頁面。

``create_app(settings)`` 回傳 FastAPI 應用；``rpa serve`` 用 uvicorn 啟動它。
啟動時：遷移資料庫 → 載入領域資料夾（M11；第一次啟動時先把舊的 scenes/ 搬進領域資料夾）→
把上次中斷的執行標為失敗 → 啟動 worker；關閉時先停 worker。

M9a：同一個應用也提供 Worker API（/worker-api/v1），只在 ``settings.worker_port`` 的埠上；
遠端 worker 的租約由背景執行緒檢查。``settings.local_worker`` 為 False 時這台電腦不執行。
M10.1：對外埠也提供桌面 App 的 Client API（/client-api/v1，目前只有配對）。
M10.2：對外埠上的 Portal 頁面與 API 給帶著錄製端權杖的請求（錄製端的本機閘道）；
錄製端的指令通道與互動子程序也在 Client API。
"""

import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from rpa_core.i18n import use_locale
from rpa_server import __version__
from rpa_server.api import api_router
from rpa_server.client_api import client_api_router
from rpa_server.config import Settings
from rpa_server.db import create_db_engine, upgrade
from rpa_server.errors import ServiceError
from rpa_server.i18n import t
from rpa_server.middleware import (
    CLIENT_API,
    WORKER_API,
    LocaleMiddleware,
    PortGateMiddleware,
    SameOriginMiddleware,
)
from rpa_server.pages import page_router
from rpa_server.render import render
from rpa_server.services import Services
from rpa_server.storage import Storage
from rpa_server.worker_api import worker_api_router
from rpa_worker import Worker

__all__ = ["STATIC", "create_app"]

STATIC: Final = Path(__file__).with_name("static")

logger = logging.getLogger("rpa_server")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    storage = Storage(settings.data_dir)
    storage.ensure()
    engine = create_db_engine(settings.database_url)
    upgrade(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    services = Services(
        sessions,
        storage,
        examples_dir=settings.examples_dir,
        display=settings.display,
        locale=settings.locale,
        local_worker=settings.local_worker,
        worker_port=settings.worker_port,
        worker_host=settings.worker_host,
        portal_port=settings.portal_port,
    )
    worker = Worker(services.queue, locale=settings.locale)
    hub = services.workers

    def queued() -> None:
        worker.wake()
        hub.notify()

    services.on_queued = queued
    services.on_cancel = worker.cancel  # 遠端 worker 在下一次心跳得知要取消
    with use_locale(settings.locale):
        # 領域資料夾（M11）：伺服器代號、舊資料遷移（先備份）、載入全部領域
        for report in services.startup():
            errors = [issue for issue in report.issues if issue.severity == "error"]
            if errors or not report.applied:
                logger.warning(
                    "%s", t("server.pack_problems", domain=report.domain_id, count=len(errors))
                )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if settings.uses_sqlite:
            logger.warning(t("server.sqlite_notice"))
        interrupted = services.recover()
        if interrupted:
            logger.warning(t("server.recovered", count=interrupted))
        if settings.seed_examples:
            with use_locale(settings.locale):
                services.seed_examples_domain()
        if settings.start_worker:
            if settings.local_worker:
                worker.start()
            hub.start_reaper()
            services.videos.start()  # 錄影的保留規則：啟動時與每小時清理（M12）
            services.recorders.start_reaper()
            services.debug.start_reaper()

            def pull() -> None:
                with use_locale(settings.locale):
                    services.git.pull_on_startup()

            # 啟動時自動拉取（M11 PR 3）：在背景做，連不上時用本機上一次的資料照常啟動
            threading.Thread(target=pull, name="git-startup-pull", daemon=True).start()
        try:
            yield
        finally:
            hub.close()
            services.videos.close()
            services.recorders.close()
            worker.stop()
            services.debug.close_all()
            services.recordings.close()
            services.roles.close()
            engine.dispose()

    app = FastAPI(
        title="RPA Portal",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.services = services
    app.state.worker = worker

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError) -> Response:  # pyright: ignore[reportUnusedFunction]
        if request.url.path.startswith(("/api/", WORKER_API, CLIENT_API)):
            return JSONResponse(error.to_json(), status_code=error.status)
        page = render(
            "error.html",
            page="scenes",
            title=t("error_page.title"),
            domains=services.list_domains(),
            status=error.status,
            message=error.message,
        )
        return HTMLResponse(page, status_code=error.status)

    app.include_router(api_router(services), prefix="/api")
    app.include_router(worker_api_router(hub))
    app.include_router(client_api_router(hub, services.recorders, storage))
    app.include_router(page_router(services))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(
        PortGateMiddleware,
        worker_port=settings.worker_port,
        authenticate=services.recorders.authenticate,
    )
    app.add_middleware(LocaleMiddleware, default=settings.locale)
    return app
