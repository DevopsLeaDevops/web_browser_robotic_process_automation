"""`rpa serve`：啟動管理 Portal（rpa-server）與背景 worker。

- 預設只聽 127.0.0.1：M3 沒有登入，不要開放給其他電腦（多用戶與認證在 M8）。
- 沒有指定 ``--port`` 時用 8080；被其他程式占用就自動改用下一個空的埠號（到 8089）。
- 占用埠號的如果就是管理 Portal（例如之前啟動、還沒關掉的），直接告訴使用者網址，
  不再開第二個：兩個 Portal 共用同一個 SQLite 與 worker 會互相干擾（ADR 0008）。
- 先自己綁定埠號再交給 uvicorn，失敗時顯示說明，而不是 uvicorn 的原始錯誤。
- 預設一起在 127.0.0.1:8765 啟動本機測試網站（「測試網站自動化」的案例對它執行），
  ``--no-testsite`` 關閉；8765 上已經是測試網站就直接沿用。``--testsite-host 0.0.0.0`` 讓錄製端、
  Worker 等其他電腦也連到這個測試網站（資料與登入共用；沒有任何保護，只在信任的網路使用）。
- 啟動時檢查 Chromium、Firefox 有沒有下載：較早安裝的環境只有 Chromium，
  git pull 之後才執行 Firefox 場景會失敗，先提醒要執行的命令。
- ``--worker-port``（M9a）：另外開一個對外埠給裝置（預設聽 0.0.0.0，所有網路介面）。
  那個埠有 Worker API、Client API 與配對（M10），錄製端也用它的權杖看管理頁面（M10.2）；
  每個請求都要權杖或邀請。這台的管理頁面仍然只在 ``--host`` 上。
  ``--no-local-worker`` 讓這台電腦不執行，全部交給遠端 worker。
"""

import dataclasses
import ipaddress
import json
import os
import socket
import urllib.request
from collections.abc import Sequence
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Final, cast

import click

from rpa_cli.i18n import t
from testsite.server import ADDRESS_IN_USE, start_in_background
from testsite.server import DEFAULT_PORT as TESTSITE_PORT
from testsite.server import LOOPBACK as TESTSITE_HOST

__all__ = [
    "DEFAULT_PORT",
    "PORTAL_TITLE",
    "browser_warning",
    "build_serve_command",
    "open_listener",
    "portal_url",
    "start_testsite",
]

DEFAULT_PORT: Final = 8080
FALLBACK_PORTS: Final = 10
"""沒有指定埠號時依序嘗試 8080～8089。"""

PORTAL_TITLE: Final = "RPA Portal"
"""管理 Portal 的 OpenAPI 標題（rpa_server.app），用來認出已經在執行的 Portal。"""

_IN_USE: Final = ADDRESS_IN_USE


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def portal_url(host: str, port: int) -> str:
    """給人打開的網址：監聽所有位址時用本機位址。"""
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}/"


def _bind(host: str, port: int) -> socket.socket:
    family, _, _, _, address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if os.name != "nt":
            # 與 uvicorn 相同：允許重用剛關閉（TIME_WAIT）的埠號；Windows 上這個選項會搶走別人的埠號
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
    except OSError:
        sock.close()
        raise
    return sock


def _get_json(url: str) -> dict[str, object] | None:
    """讀取本機網址的 JSON 物件；連不上或不是 JSON 物件時回傳 None。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本機位址不走代理
    try:
        with opener.open(url, timeout=1) as response:
            data: object = json.load(response)
    except (OSError, ValueError):
        return None
    return cast("dict[str, object]", data) if isinstance(data, dict) else None


def _is_portal(host: str, port: int) -> bool:
    """這個埠號上是不是管理 Portal（讀 /api/openapi.json 的標題）。"""
    data = _get_json(f"{portal_url(host, port)}api/openapi.json")
    info = data.get("info") if data is not None else None
    return isinstance(info, dict) and cast("dict[str, object]", info).get("title") == PORTAL_TITLE


def start_testsite(
    port: int = TESTSITE_PORT, host: str = TESTSITE_HOST
) -> tuple[ThreadingHTTPServer | None, str]:
    """在背景執行緒啟動測試網站，回傳 (伺服器，沒有啟動時為 None；要顯示的訊息)。

    host 不是本機位址（例如 0.0.0.0）時，其他電腦（錄製端、Worker）也連得到：訊息顯示對外的網址
    （綁定所有介面時猜區網位址）並提醒測試網站沒有任何保護。
    """
    exposed = not _is_loopback(host)
    if exposed:
        from rpa_worker.environment import external_url

        url = external_url(host, port) + "/"
    else:
        url = f"http://127.0.0.1:{port}/"
    server, state, detail = start_in_background(port, host)
    if state == "failed":
        return None, t("cli.serve.testsite_failed", url=url, error=detail)
    if state == "busy":
        return None, t("cli.serve.testsite_busy", port=port)
    message = t(f"cli.serve.testsite_{state}", url=url)
    if exposed and state == "started":
        message += "\n" + t("cli.serve.testsite_exposed", url=url)
    return server, message


def browser_warning(missing: Sequence[str]) -> str | None:
    """還沒下載的瀏覽器的提醒；都有下載時回傳 None。"""
    if not missing:
        return None
    # 只有啟動伺服器時才需要 Playwright
    from rpa_runner.installed import browser_names, install_command

    return t(
        "cli.serve.browsers_missing",
        browsers=browser_names(missing),
        command=install_command(missing),
    )


def open_listener(
    host: str,
    port: int | None,
    *,
    first: int = DEFAULT_PORT,
    count: int = FALLBACK_PORTS,
) -> tuple[socket.socket, int, int | None]:
    """綁定要監聽的埠號，回傳 (socket, 埠號, 因為被占用而跳過的第一個埠號)。

    port 為 None 時從 first 開始依序嘗試 count 個埠號。失敗時拋出 click.ClickException。
    """
    candidates = [port] if port is not None else list(range(first, first + count))
    skipped: int | None = None
    for candidate in candidates:
        try:
            return _bind(host, candidate), candidate, skipped
        except OSError as error:
            if error.errno not in _IN_USE:
                detail = error.strerror or str(error)
                message = t("cli.serve.bind_failed", host=host, port=candidate, error=detail)
                raise click.ClickException(message) from None
            if _is_portal(host, candidate):
                url = portal_url(host, candidate)
                raise click.ClickException(t("cli.serve.already_running", url=url)) from None
            if skipped is None:
                skipped = candidate
    if port is not None:
        raise click.ClickException(t("cli.serve.port_busy", port=port, suggestion=port + 10))
    raise click.ClickException(t("cli.serve.no_free_port", first=first, last=first + count - 1))


def build_serve_command() -> click.Command:
    """依目前語言建立 `rpa serve`。"""

    @click.command(
        name="serve",
        help=t("cli.serve.help"),
        short_help=t("cli.serve.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.option("--host", default="127.0.0.1", show_default=True, help=t("cli.serve.host_help"))
    @click.option(
        "--port",
        type=int,
        default=None,
        help=t("cli.serve.port_help", first=DEFAULT_PORT, last=DEFAULT_PORT + FALLBACK_PORTS - 1),
    )
    @click.option(
        "--data",
        "data_dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help=t("cli.serve.data_help"),
    )
    @click.option(
        "--testsite/--no-testsite",
        default=True,
        help=t("cli.serve.testsite_help", port=TESTSITE_PORT),
    )
    @click.option(
        "--testsite-host",
        default=TESTSITE_HOST,
        show_default=True,
        help=t("cli.serve.testsite_host_help", port=TESTSITE_PORT),
    )
    @click.option(
        "--worker-port",
        type=click.IntRange(1, 65535),
        default=None,
        help=t("cli.serve.worker_port_help"),
    )
    @click.option(
        "--worker-host",
        default="0.0.0.0",
        show_default=True,
        help=t("cli.serve.worker_host_help"),
    )
    @click.option(
        "--local-worker/--no-local-worker",
        default=True,
        help=t("cli.serve.local_worker_help"),
    )
    def serve(
        host: str,
        port: int | None,
        data_dir: Path | None,
        testsite: bool,
        testsite_host: str,
        worker_port: int | None,
        worker_host: str,
        local_worker: bool,
    ) -> None:
        sock, chosen, skipped = open_listener(host, port)
        worker_sock: socket.socket | None = None
        site: ThreadingHTTPServer | None = None
        try:
            if worker_port is not None:
                if worker_port == chosen:
                    raise click.ClickException(t("cli.serve.worker_port_same", port=worker_port))
                worker_sock, _, _ = open_listener(worker_host, worker_port)
            # 只有真的啟動伺服器時才載入 FastAPI 與資料庫
            import uvicorn

            from rpa_runner.installed import missing_browsers
            from rpa_server.app import create_app
            from rpa_server.config import Settings

            settings = dataclasses.replace(
                Settings.from_env(data_dir=data_dir),
                worker_port=worker_port,
                worker_host=worker_host,
                local_worker=local_worker,
                portal_port=chosen,
            )
            if skipped is not None:
                click.echo(t("cli.serve.port_switched", busy=skipped, port=chosen), err=True)
            if not _is_loopback(host):
                click.echo(t("cli.serve.exposed", host=host), err=True)
            app = create_app(settings)
            if testsite:
                site, message = start_testsite(host=testsite_host)
                click.echo(message, err=True)
            if local_worker:
                warning = browser_warning(missing_browsers())
                if warning is not None:
                    click.echo(warning, err=True)
            click.echo(
                t(
                    "cli.serve.started",
                    url=portal_url(host, chosen),
                    data=settings.data_dir.resolve(),
                ),
                err=True,
            )
            sockets = [sock]
            if worker_sock is not None and worker_port is not None:
                sockets.append(worker_sock)
                from rpa_worker.environment import external_url

                url = external_url(worker_host, worker_port)
                click.echo(t("cli.serve.worker_api", url=url), err=True)
            if not local_worker:
                click.echo(t("cli.serve.local_worker_off"), err=True)
            # 遠端 worker 的長輪詢最多 25 秒：Ctrl+C 時不必等它們結束
            config = uvicorn.Config(
                app, host=host, port=chosen, log_level="info", timeout_graceful_shutdown=5
            )
            uvicorn.Server(config).run(sockets=sockets)
        finally:
            sock.close()
            if worker_sock is not None:
                worker_sock.close()
            if site is not None:
                site.shutdown()
                site.server_close()

    return serve
