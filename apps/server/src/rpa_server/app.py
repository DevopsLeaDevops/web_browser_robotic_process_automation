"""組裝管理 Portal：資料庫、服務層、背景 worker、API 與頁面。

``create_app(settings)`` 回傳 FastAPI 應用；``rpa serve`` 用 uvicorn 啟動它。
啟動時：遷移資料庫 → 把上次中斷的執行標為失敗 → 啟動 worker；關閉時先停 worker。
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from rpa_server import __version__
from rpa_server.api import api_router
from rpa_server.config import Settings
from rpa_server.db import create_db_engine, upgrade
from rpa_server.i18n import t
from rpa_server.jobs import RunQueue
from rpa_server.middleware import LocaleMiddleware, SameOriginMiddleware
from rpa_server.pages import page_router
from rpa_server.render import render
from rpa_server.services import ServiceError, Services
from rpa_server.storage import Storage
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
    services = Services(sessions, storage, examples_dir=settings.examples_dir)
    worker = Worker(RunQueue(sessions, storage), locale=settings.locale)
    services.on_queued = worker.wake
    services.on_cancel = worker.cancel

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if settings.uses_sqlite:
            logger.warning(t("server.sqlite_notice"))
        interrupted = services.recover()
        if interrupted:
            logger.warning(t("server.recovered", count=interrupted))
        if settings.start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()
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
        if request.url.path.startswith("/api/"):
            return JSONResponse(error.to_json(), status_code=error.status)
        page = render(
            "error.html",
            page="scenes",
            title=t("error_page.title"),
            status=error.status,
            message=error.message,
        )
        return HTMLResponse(page, status_code=error.status)

    app.include_router(api_router(services), prefix="/api")
    app.include_router(page_router(services))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(LocaleMiddleware, default=settings.locale)
    return app
