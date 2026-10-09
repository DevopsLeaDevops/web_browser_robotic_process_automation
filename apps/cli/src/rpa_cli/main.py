"""`rpa` 命令入口。

M0 只有 `--version`；之後的里程碑依序加入子命令：
validate（M1）、run（M2）、record（M4）、generate（M5）、push（M7）。
"""

import click

import rpa_cli
import rpa_core


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(
    rpa_cli.__version__,
    "-V",
    "--version",
    message=f"rpa %(version)s（rpa-core {rpa_core.__version__}）",
)
def cli() -> None:
    """瀏覽器自動化場景的生成、管理與執行工具。"""
