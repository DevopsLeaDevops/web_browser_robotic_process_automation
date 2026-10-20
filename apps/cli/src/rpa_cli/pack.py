"""`rpa pack check`：不開管理 Portal，校驗一個或多個領域資料夾（M11）。

和管理 Portal 載入資料夾用同一套規則（:func:`rpa_core.pack.read_pack`）：說明檔的格式、
版本內容和版本說明檔的雜湊、驗證紀錄、發布門檻、角色定義，以及不能放進資料夾的機密檔案。
可以放在資料倉庫的 CI，推送前先擋下壞掉的資料夾。一次給多個資料夾時，也檢查它們之間
組合場景的依賴（M11 PR 2）。輸出格式和 ``rpa validate`` 一樣是
``檔案:行:列: 訊息``；``--format json`` 給程式使用。
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import click

from rpa_cli.i18n import t
from rpa_cli.validate import EXIT_INVALID, display_path
from rpa_core.pack import Pack, PackIssue, check_requirements, read_pack

__all__ = ["build_pack_command"]

OutputFormat = Literal["text", "json"]


def _location(pack: Pack, issue: PackIssue) -> str:
    path = pack.folder / issue.path if issue.path else pack.folder
    location = display_path(path)
    if issue.line is not None:
        location += f":{issue.line}:{issue.column or 1}"
    return location


def _report_text(packs: Sequence[Pack]) -> None:
    for pack in packs:
        for issue in pack.issues:
            message = issue.message
            if issue.severity == "warning":
                message = t("cli.pack.check.warning", message=message)
            click.echo(f"{click.style(_location(pack, issue), bold=True)}: {message}")
        errors = len(pack.errors)
        warnings = len(pack.issues) - errors
        key = "ok" if pack.ok else "failed"
        click.echo(
            t(
                f"cli.pack.check.summary.{key}",
                folder=display_path(pack.folder),
                id=pack.manifest.id if pack.manifest is not None else "?",
                scenes=len(pack.scenes),
                composites=len(pack.composites),
                roles=len(pack.roles),
                errors=errors,
                warnings=warnings,
            )
        )


def _report_json(packs: Sequence[Pack]) -> None:
    report = [
        {
            "folder": display_path(pack.folder),
            "id": pack.manifest.id if pack.manifest is not None else None,
            "valid": pack.ok,
            "scenes": {
                scene.id: {
                    "latest": scene.latest,
                    "published": scene.published,
                    "revisions": {
                        str(number): {
                            "usable": revision.usable,
                            "status": revision.status,
                            "problem": revision.problem,
                            "verifications": len(revision.verifications),
                        }
                        for number, revision in sorted(scene.revisions.items())
                    },
                }
                for scene in pack.scenes.values()
            },
            "roles": sorted(pack.roles),
            "composites": {
                composite.id: {"latest": composite.latest, "published": composite.published}
                for composite in pack.composites.values()
            },
            "issues": [issue.to_json() for issue in pack.issues],
        }
        for pack in packs
    ]
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))


def build_pack_command() -> click.Group:
    """依目前語言建立 `rpa pack`。"""

    @click.group(
        name="pack",
        help=t("cli.pack.help"),
        short_help=t("cli.pack.short_help"),
        options_metavar=t("cli.options_metavar"),
        subcommand_metavar=t("cli.subcommand_metavar"),
    )
    def pack() -> None:
        pass

    @pack.command(
        name="check",
        help=t("cli.pack.check.help"),
        short_help=t("cli.pack.check.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.argument(
        "folders",
        nargs=-1,
        required=True,
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        metavar=t("cli.pack.check.folders_metavar"),
    )
    @click.option(
        "--id",
        "expected_id",
        default=None,
        metavar=t("cli.pack.check.id_metavar"),
        help=t("cli.pack.check.id_help"),
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["text", "json"]),
        default="text",
        show_default=True,
        help=t("cli.validate.format_help"),
    )
    def check(
        folders: tuple[Path, ...], expected_id: str | None, output_format: OutputFormat
    ) -> None:
        packs = [read_pack(folder, expected_id=expected_id) for folder in folders]
        check_requirements(packs)  # 一起檢查的資料夾之間，組合場景的依賴
        if output_format == "json":
            _report_json(packs)
        else:
            _report_text(packs)
        if not all(pack.ok for pack in packs):
            click.get_current_context().exit(EXIT_INVALID)

    return pack
