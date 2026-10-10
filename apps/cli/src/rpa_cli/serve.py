"""`rpa serve`：啟動管理 Portal（rpa-server）與背景 worker。

預設只聽 127.0.0.1：M3 沒有登入，不要開放給其他電腦（多用戶與認證在 M8）。
"""

import ipaddress
from pathlib import Path

import click

from rpa_cli.i18n import t

__all__ = ["build_serve_command"]


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
        "--port", default=8000, show_default=True, type=int, help=t("cli.serve.port_help")
    )
    @click.option(
        "--data",
        "data_dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help=t("cli.serve.data_help"),
    )
    def serve(host: str, port: int, data_dir: Path | None) -> None:
        # 只有真的啟動伺服器時才載入 FastAPI 與資料庫
        import uvicorn

        from rpa_server.app import create_app
        from rpa_server.config import Settings

        settings = Settings.from_env(data_dir=data_dir)
        if not _is_loopback(host):
            click.echo(t("cli.serve.exposed", host=host), err=True)
        click.echo(
            t(
                "cli.serve.started",
                url=f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/",
                data=settings.data_dir.resolve(),
            ),
            err=True,
        )
        uvicorn.run(create_app(settings), host=host, port=port, log_level="info")

    return serve
