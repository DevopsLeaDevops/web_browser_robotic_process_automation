"""`rpa run`：執行一個場景，產生執行目錄與報告。

入參可以用 ``-i 名稱=值``（依宣告的型別轉換）或 ``--input 檔.json``
（例如上一個場景的 output.json），
兩者都給時 ``-i`` 優先。退出碼：0 通過，1 未通過或場景有誤，2 參數錯誤。
"""

import json
from pathlib import Path
from typing import Literal, cast

import click

from rpa_cli.i18n import t
from rpa_cli.validate import EXIT_INVALID, display_path, issue_line
from rpa_core.dsl import validate_file
from rpa_runner.contract import parse_cli_value
from rpa_runner.i18n import t as runner_t
from rpa_runner.run import ScenarioInvalidError, execute

__all__ = ["build_run_command"]

OutputFormat = Literal["text", "json"]


def _parse_values(
    ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise click.BadParameter(t("cli.run.input_value_invalid", value=item), ctx, param)
        parsed[name] = value
    return parsed


def build_run_command() -> click.Command:
    """依目前語言建立 `rpa run`。"""

    @click.command(
        name="run",
        help=t("cli.run.help"),
        short_help=t("cli.run.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.argument(
        "scenario",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        metavar=t("cli.run.scenario_metavar"),
    )
    @click.option(
        "-i",
        "--input-value",
        "values",
        multiple=True,
        callback=_parse_values,
        metavar=t("cli.run.input_value_metavar"),
        help=t("cli.run.input_value_help"),
    )
    @click.option(
        "--input",
        "input_file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help=t("cli.run.input_file_help"),
    )
    @click.option("--base-url", help=t("cli.run.base_url_help"))
    @click.option(
        "--browser",
        type=click.Choice(["chromium", "firefox", "webkit"]),
        help=t("cli.run.browser_help"),
    )
    @click.option("--headed", is_flag=True, help=t("cli.run.headed_help"))
    @click.option("--deadline", type=click.IntRange(min=1), help=t("cli.run.deadline_help"))
    @click.option(
        "--out",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("runs"),
        show_default=True,
        help=t("cli.run.out_help"),
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["text", "json"]),
        default="text",
        show_default=True,
        help=t("cli.run.format_help"),
    )
    def run(
        scenario: Path,
        values: dict[str, str],
        input_file: Path | None,
        base_url: str | None,
        browser: str | None,
        headed: bool,
        deadline: int | None,
        out: Path,
        output_format: OutputFormat,
    ) -> None:
        ctx = click.get_current_context()
        inputs: dict[str, object] = {}
        if input_file is not None:
            loaded: object = json.loads(input_file.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise click.BadParameter(t("cli.run.input_file_invalid"), ctx, param_hint="--input")
            inputs.update(cast("dict[str, object]", loaded))
        checked = validate_file(scenario)
        specs = checked.scenario.inputs if checked.scenario is not None else {}
        for name, text in values.items():
            spec = specs.get(name)
            inputs[name] = parse_cli_value(spec, text) if spec is not None else text
        try:
            result = execute(
                scenario,
                inputs,
                out_root=out,
                base_url=base_url,
                engine=browser,
                headed=headed,
                deadline_ms=deadline,
            )
        except ScenarioInvalidError as invalid:
            display = display_path(scenario)
            for issue in invalid.issues:
                click.echo(issue_line(display, issue), err=True)
            ctx.exit(EXIT_INVALID)
            return
        if output_format == "json":
            click.echo(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
        else:
            status = runner_t(f"status.{result.status}")
            click.echo(
                t(
                    "cli.run.summary",
                    id=result.scenario_id,
                    name=result.scenario_name,
                    status=status,
                    seconds=result.duration_seconds,
                )
            )
            for problem in result.problems:
                click.echo(f"  - {problem}")
            if result.error:
                click.echo(t("cli.run.error", error=result.error))
            if result.output is not None:
                click.echo(t("cli.run.output", path=display_path(result.directory / "output.json")))
            click.echo(t("cli.run.report", path=display_path(result.directory / "report.html")))
        if result.status != "passed":
            ctx.exit(EXIT_INVALID)

    return run
