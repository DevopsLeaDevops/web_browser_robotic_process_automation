"""`rpa record`：在這台電腦錄製瀏覽器操作，存成遮罩過密碼的錄製稿，並可直接轉成 DSL 草稿。

- 錄製用 Playwright codegen：瀏覽器視窗與 Playwright Inspector 開在這台電腦上，
  操作完關掉視窗即結束。
- 錄製中的原始稿（可能含密碼）先寫在暫存檔，轉換後刪除；``--out`` 存的是遮罩過密碼的版本。
- ``--scenario`` 同時寫出 DSL 草稿；草稿還要經過驗證才能發布
  （管理 Portal 的「貼上錄製稿」也能轉換）。
- ``--from`` 不錄製，轉換已經錄好的 codegen 原始稿。
"""

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import click

from rpa_cli.i18n import t
from rpa_cli.validate import EXIT_INVALID, display_path
from rpa_core.recording import ConversionError, convert_recording
from rpa_runner.commands import playwright_command

__all__ = ["build_record_command", "codegen"]


def codegen(command: Sequence[str]) -> int:
    """執行 codegen，等使用者關掉瀏覽器視窗；回傳結束碼。測試會換掉這個函式。"""
    return subprocess.run(list(command), check=False).returncode


def _scene_id(out: Path, given: str | None) -> str:
    if given:
        return given
    slug = re.sub(r"[^a-z0-9_-]+", "-", out.stem.lower()).strip("-_")
    return slug[:64] if slug and slug[0].isalnum() else "recorded"


def build_record_command() -> click.Command:
    """依目前語言建立 `rpa record`。"""

    @click.command(
        name="record",
        help=t("cli.record.help"),
        short_help=t("cli.record.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.argument("url", required=False, metavar=t("cli.record.url_metavar"))
    @click.option(
        "--out",
        type=click.Path(dir_okay=False, path_type=Path),
        default=Path("recording.py"),
        show_default=True,
        help=t("cli.record.out_help"),
    )
    @click.option(
        "--browser",
        type=click.Choice(["chromium", "firefox"]),
        default="chromium",
        show_default=True,
        help=t("cli.record.browser_help"),
    )
    @click.option(
        "--load-storage",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help=t("cli.record.storage_help"),
    )
    @click.option(
        "--scenario",
        "scenario_file",
        type=click.Path(dir_okay=False, path_type=Path),
        help=t("cli.record.scenario_help"),
    )
    @click.option("--id", "scene_id", help=t("cli.record.id_help"))
    @click.option("--name", help=t("cli.record.name_help"))
    @click.option(
        "--from",
        "source_file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help=t("cli.record.from_help"),
    )
    def record(
        url: str | None,
        out: Path,
        browser: str,
        load_storage: Path | None,
        scenario_file: Path | None,
        scene_id: str | None,
        name: str | None,
        source_file: Path | None,
    ) -> None:
        ctx = click.get_current_context()
        if source_file is not None:
            source = source_file.read_text(encoding="utf-8")
        else:
            if not url:
                raise click.UsageError(t("cli.record.url_required"), ctx)
            source = _record(ctx, url, out, browser, load_storage)
        identifier = _scene_id(out, scene_id)
        try:
            conversion = convert_recording(
                source,
                scene_id=identifier,
                name=name or identifier,
                url=url,
                engine=browser,
            )
        except ConversionError as error:
            click.echo(str(error), err=True)
            ctx.exit(EXIT_INVALID)
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(conversion.masked_source, encoding="utf-8")
        click.echo(t("cli.record.saved", path=display_path(out), steps=conversion.steps))
        if conversion.secrets:
            click.echo(t("cli.record.secrets", names=", ".join(conversion.secrets)))
        for warning in conversion.warnings:
            click.echo(t("cli.record.warning", line=warning.line, message=warning.message))
        if scenario_file is not None:
            scenario_file.parent.mkdir(parents=True, exist_ok=True)
            scenario_file.write_text(conversion.scenario, encoding="utf-8")
            click.echo(t("cli.record.scenario", path=display_path(scenario_file)))

    return record


def _record(
    ctx: click.Context, url: str, out: Path, browser: str, load_storage: Path | None
) -> str:
    """錄製到暫存檔，讀回內容後刪除暫存檔（裡面可能有密碼）。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f".{out.name}.recording")
    command = playwright_command(
        [
            "codegen",
            "--target",
            "python",
            "--output",
            str(temporary),
            "--browser",
            browser,
        ]
    )
    if load_storage is not None:
        command += ["--load-storage", str(load_storage)]
    click.echo(t("cli.record.started", browser=browser))
    try:
        code = codegen([*command, url])
        source = temporary.read_text(encoding="utf-8") if temporary.exists() else ""
    finally:
        temporary.unlink(missing_ok=True)
    if code != 0 or not source.strip():
        click.echo(t("cli.record.failed", code=code), err=True)
        ctx.exit(EXIT_INVALID)
    return source
