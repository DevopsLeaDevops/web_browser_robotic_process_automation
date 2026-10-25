"""`rpa update`：用更新檔升級裝好的伺服器分發包（ADR 0018）。

    <安裝位置>/bin/rpa update RPA-Update-0.6.0.zip [--now]

驗證簽章與檔案（公鑰在執行環境裡，不會被更新檔換掉），裝成新的版本資料夾、換掉 ``current``，
再請 ``bin/rpa serve`` 啟動的伺服器在沒有進行中的錄製、逐步調試、人工登入時重新啟動
（``--now`` 不等）。程式在 :mod:`rpa_server.updates`；這裡只負責命令與訊息。
"""

from pathlib import Path

import click

from rpa_cli.i18n import t
from rpa_core.i18n import DEFAULT_LOCALE

__all__ = ["build_update_command", "describe_error"]


def describe_error(code: str, params: dict[str, object]) -> str:
    """更新錯誤的說明：``cli.update.error.<代號>``，沒有這個代號時顯示原始的代號。"""
    key = f"cli.update.error.{code}"
    if key in t.messages(DEFAULT_LOCALE):
        return t(key, **params)
    details = ", ".join(f"{name}={value}" for name, value in params.items())
    return t("cli.update.error.other", code=f"{code} {details}".strip())


def build_update_command() -> click.Command:
    """依目前語言建立 `rpa update`。"""

    @click.command(
        name="update",
        help=t("cli.update.help"),
        short_help=t("cli.update.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.argument(
        "file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        metavar=t("cli.update.file_metavar"),
    )
    @click.option("--now", is_flag=True, help=t("cli.update.now_help"))
    def update(file: Path, now: bool) -> None:
        # 只在真的要更新時才載入伺服器的程式
        from rpa_server.updates import Layout, install_update
        from rpa_update.errors import UpdateError

        layout = Layout.detect()
        if layout is None:
            raise click.ClickException(t("cli.update.not_installed"))
        click.echo(t("cli.update.checking", file=file), err=True)
        try:
            result = install_update(layout, file, now=now)
        except UpdateError as error:
            raise click.ClickException(describe_error(error.code, dict(error.params))) from None
        version = result.manifest.version
        if result.already:
            click.echo(t("cli.update.already", version=version, release=result.release))
            return
        click.echo(
            t(
                "cli.update.installed",
                version=version,
                release=result.release,
                previous=result.previous,
            )
        )
        key = "cli.update.restart_now" if now else "cli.update.restart_idle"
        click.echo(t(key, previous=result.previous))

    return update
