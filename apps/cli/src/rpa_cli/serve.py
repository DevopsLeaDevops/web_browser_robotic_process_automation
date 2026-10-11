"""`rpa serve`：啟動管理 Portal（rpa-server）與背景 worker。

- 預設只聽 127.0.0.1：M3 沒有登入，不要開放給其他電腦（多用戶與認證在 M8）。
- 沒有指定 ``--port`` 時用 8080；被其他程式占用就自動改用下一個空的埠號（到 8089）。
- 占用埠號的如果就是管理 Portal（例如之前啟動、還沒關掉的），直接告訴使用者網址，
  不再開第二個：兩個 Portal 共用同一個 SQLite 與 worker 會互相干擾（ADR 0008）。
- 先自己綁定埠號再交給 uvicorn，失敗時顯示說明，而不是 uvicorn 的原始錯誤。
"""

import errno
import ipaddress
import json
import os
import socket
import urllib.request
from pathlib import Path
from typing import Final, cast

import click

from rpa_cli.i18n import t

__all__ = ["DEFAULT_PORT", "PORTAL_TITLE", "build_serve_command", "open_listener", "portal_url"]

DEFAULT_PORT: Final = 8080
FALLBACK_PORTS: Final = 10
"""沒有指定埠號時依序嘗試 8080～8089。"""

PORTAL_TITLE: Final = "RPA Portal"
"""管理 Portal 的 OpenAPI 標題（rpa_server.app），用來認出已經在執行的 Portal。"""

_IN_USE: Final = frozenset(
    code
    for code in (
        errno.EADDRINUSE,
        getattr(errno, "WSAEADDRINUSE", None),
        # Windows 保留給其他服務的埠號（例如 Hyper-V）綁定時回報存取被拒
        getattr(errno, "WSAEACCES", None),
    )
    if code is not None
)


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


def _is_portal(host: str, port: int) -> bool:
    """這個埠號上是不是管理 Portal（讀 /api/openapi.json 的標題）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本機位址不走代理
    try:
        with opener.open(f"{portal_url(host, port)}api/openapi.json", timeout=1) as response:
            data: object = json.load(response)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    info = cast("dict[str, object]", data).get("info")
    return isinstance(info, dict) and cast("dict[str, object]", info).get("title") == PORTAL_TITLE


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
    def serve(host: str, port: int | None, data_dir: Path | None) -> None:
        sock, chosen, skipped = open_listener(host, port)
        try:
            # 只有真的啟動伺服器時才載入 FastAPI 與資料庫
            import uvicorn

            from rpa_server.app import create_app
            from rpa_server.config import Settings

            settings = Settings.from_env(data_dir=data_dir)
            if skipped is not None:
                click.echo(t("cli.serve.port_switched", busy=skipped, port=chosen), err=True)
            if not _is_loopback(host):
                click.echo(t("cli.serve.exposed", host=host), err=True)
            app = create_app(settings)
            click.echo(
                t(
                    "cli.serve.started",
                    url=portal_url(host, chosen),
                    data=settings.data_dir.resolve(),
                ),
                err=True,
            )
            config = uvicorn.Config(app, host=host, port=chosen, log_level="info")
            uvicorn.Server(config).run(sockets=[sock])
        finally:
            sock.close()

    return serve
