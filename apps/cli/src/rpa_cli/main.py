"""`rpa` 命令入口。

M0 只有 `--version` 與 `--lang`；之後的里程碑依序加入子命令：
validate（M1）、run（M2）、record（M4）、generate（M5）、push（M7）。

說明文字要依語言顯示，所以命令在決定語言之後才由 build_cli() 建立，
不在模組載入時就用裝飾器定義好。
"""

import os
import sys
from collections.abc import Sequence

import click

import rpa_cli
import rpa_core
from rpa_cli.i18n import LANG_OPTION, install_click_translations, resolve_locale, t
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, LOCALES, Locale, parse_locale, set_locale


class LocaleType(click.ParamType):
    """`--lang` 的值：接受 zh-Hant、zh-Hans、en，以及 zh-TW、zh_CN 這類別名。"""

    name = "locale"

    def convert(
        self, value: object, param: click.Parameter | None, ctx: click.Context | None
    ) -> Locale:
        locale = parse_locale(str(value))
        if locale is None:
            self.fail(t("cli.lang.invalid", value=value, choices="|".join(LOCALES)), param, ctx)
        return locale


def build_cli() -> click.Group:
    """依目前語言建立 `rpa` 命令。"""

    @click.group(
        name="rpa",
        help=t("cli.help"),
        options_metavar=t("cli.options_metavar"),
        subcommand_metavar=t("cli.subcommand_metavar"),
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    @click.version_option(
        rpa_cli.__version__,
        "-V",
        "--version",
        message=t("cli.version", version=rpa_cli.__version__, core_version=rpa_core.__version__),
    )
    @click.option(
        LANG_OPTION,
        type=LocaleType(),
        metavar="|".join(LOCALES),
        is_eager=True,
        expose_value=False,
        help=t("cli.lang.help", default=DEFAULT_LOCALE, env=ENV_VAR),
    )
    def cli() -> None:
        pass

    return cli


def main(args: Sequence[str] | None = None) -> None:
    """`rpa` 命令的進入點（pyproject.toml 的 project.scripts）。"""
    argv = list(sys.argv[1:] if args is None else args)
    set_locale(resolve_locale(argv, os.environ))
    install_click_translations()
    build_cli().main(args=argv, prog_name="rpa")
