"""`rpa validate` 與 `rpa schema`。

validate 的文字輸出採編譯器格式 ``檔案:行:列: 訊息``，編輯器與 CI 可以直接跳到錯誤位置；
``--format json`` 給程式與 AI 自動修正（M5）使用。
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import click

from rpa_cli.i18n import t
from rpa_core.dsl import Issue, ValidationResult, format_issue, scenario_json_schema, validate_file

__all__ = ["EXIT_INVALID", "build_schema_command", "build_validate_command", "collect_files"]

EXIT_INVALID: Final = 1
"""有任何檔案沒有通過校驗時的退出碼。"""

YAML_SUFFIXES: Final = (".yaml", ".yml")

OutputFormat = Literal["text", "json"]


@dataclass(frozen=True, slots=True)
class _Checked:
    path: Path
    result: ValidationResult


def collect_files(paths: Iterable[Path]) -> tuple[list[Path], list[Path]]:
    """展開要檢查的檔案：檔案照原樣，資料夾找出底下所有 .yaml 與 .yml（略過隱藏資料夾）。

    回傳 (檔案, 找不到任何 YAML 的資料夾)。同一個檔案只檢查一次。
    """
    files: dict[Path, None] = {}
    empty_dirs: list[Path] = []
    for path in paths:
        if not path.is_dir():
            files[path] = None
            continue
        found = sorted(
            p
            for p in path.rglob("*")
            if p.suffix in YAML_SUFFIXES
            and p.is_file()
            and not any(part.startswith(".") for part in p.relative_to(path).parts[:-1])
        )
        if not found:
            empty_dirs.append(path)
        files.update(dict.fromkeys(found))
    return list(files), empty_dirs


def _display(path: Path) -> str:
    """輸出用的路徑：在目前目錄底下就用相對路徑，一律用 / 分隔。"""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _issue_line(path: str, issue: Issue) -> str:
    position = issue.position
    location = f"{path}:{position.line}:{position.column}" if position else path
    return f"{click.style(location, bold=True)}: {format_issue(issue)}"


def _issue_json(issue: Issue) -> dict[str, object]:
    position = issue.position
    return {
        "line": position.line if position else None,
        "column": position.column if position else None,
        "step": issue.step,
        "stepId": issue.step_id,
        "field": issue.field or None,
        "path": list(issue.path),
        "code": issue.code,
        "message": issue.message,
    }


def _report_text(checked: Sequence[_Checked], empty_dirs: Sequence[Path]) -> None:
    for directory in empty_dirs:
        click.echo(t("cli.validate.no_files", path=_display(directory)), err=True)
    for item in checked:
        display = _display(item.path)
        for issue in item.result.issues:
            click.echo(_issue_line(display, issue))
    invalid = sum(1 for item in checked if not item.result.ok)
    issues = sum(len(item.result.issues) for item in checked)
    if invalid:
        click.echo(
            t("cli.validate.summary.failed", files=len(checked), invalid=invalid, issues=issues)
        )
    elif checked:
        click.echo(t("cli.validate.summary.ok", files=len(checked)))


def _report_json(checked: Sequence[_Checked], empty_dirs: Sequence[Path]) -> None:
    report = {
        "files": [
            {
                "path": _display(item.path),
                "valid": item.result.ok,
                "issues": [_issue_json(issue) for issue in item.result.issues],
            }
            for item in checked
        ],
        "emptyDirectories": [_display(directory) for directory in empty_dirs],
        "summary": {
            "files": len(checked),
            "invalid": sum(1 for item in checked if not item.result.ok),
            "issues": sum(len(item.result.issues) for item in checked),
        },
    }
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))


def build_validate_command() -> click.Command:
    """依目前語言建立 `rpa validate`。"""

    @click.command(
        name="validate",
        help=t("cli.validate.help"),
        short_help=t("cli.validate.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.argument(
        "paths",
        nargs=-1,
        required=True,
        type=click.Path(exists=True, path_type=Path),
        metavar=t("cli.validate.paths_metavar"),
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["text", "json"]),
        default="text",
        show_default=True,
        help=t("cli.validate.format_help"),
    )
    def validate(paths: tuple[Path, ...], output_format: OutputFormat) -> None:
        files, empty_dirs = collect_files(paths)
        checked = [_Checked(path, validate_file(path)) for path in files]
        if output_format == "json":
            _report_json(checked, empty_dirs)
        else:
            _report_text(checked, empty_dirs)
        if empty_dirs or any(not item.result.ok for item in checked):
            click.get_current_context().exit(EXIT_INVALID)

    return validate


def build_schema_command() -> click.Command:
    """依目前語言建立 `rpa schema`。"""

    @click.command(
        name="schema",
        help=t("cli.schema.help"),
        short_help=t("cli.schema.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    def schema() -> None:
        click.echo(json.dumps(scenario_json_schema(), ensure_ascii=False, indent=2))

    return schema
