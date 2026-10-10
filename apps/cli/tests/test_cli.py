import gettext
import os
import subprocess
import sys
from collections.abc import Mapping

import pytest
from click.testing import CliRunner, Result

import rpa_cli
import rpa_core
from rpa_cli.i18n import install_click_translations, resolve_locale
from rpa_cli.main import build_cli
from rpa_core.i18n import use_locale


def invoke(args: list[str], environ: Mapping[str, str] | None = None) -> Result:
    """跟 main() 一樣：先決定語言，再建立命令並執行。"""
    with use_locale(resolve_locale(args, environ or {})):
        install_click_translations()
        return CliRunner().invoke(build_cli(), args)


def run_module(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    """以子程序執行 python -m rpa_cli，測試真正的進入點。"""
    environ = {k: v for k, v in os.environ.items() if k != "RPA_LANG"} | env
    return subprocess.run(
        [sys.executable, "-m", "rpa_cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environ | {"PYTHONIOENCODING": "utf-8"},
        check=False,
    )


def test_version_shows_cli_and_core_versions() -> None:
    result = invoke(["--version"])

    assert result.exit_code == 0
    assert result.output == f"rpa {rpa_cli.__version__}（rpa-core {rpa_core.__version__}）\n"


def test_default_language_is_traditional_chinese() -> None:
    result = invoke(["-h"])

    assert result.exit_code == 0
    assert "瀏覽器自動化" in result.output
    # click 內建的文字也要翻譯，不能留下英文
    assert "用法:" in result.output
    assert "顯示這段說明後結束。" in result.output
    assert "Usage" not in result.output
    assert "Show this message" not in result.output


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("zh-Hant", ["瀏覽器自動化", "用法:", "選項:"]),
        ("zh-Hans", ["浏览器自动化", "用法:", "选项:"]),
        ("en", ["browser automation", "Usage:", "Options:", "Show this message and exit."]),
    ],
)
def test_help_in_each_language(lang: str, expected: list[str]) -> None:
    result = invoke(["--lang", lang, "-h"])

    assert result.exit_code == 0
    for text in expected:
        assert text in result.output


def test_version_in_english() -> None:
    result = invoke(["--lang", "en", "--version"])

    assert result.output == f"rpa {rpa_cli.__version__} (rpa-core {rpa_core.__version__})\n"


def test_env_var_sets_language() -> None:
    assert "browser automation" in invoke(["-h"], {"RPA_LANG": "en"}).output


def test_lang_option_wins_over_env_var() -> None:
    assert "浏览器自动化" in invoke(["--lang=zh-Hans", "-h"], {"RPA_LANG": "en"}).output


@pytest.mark.parametrize(
    ("args", "environ", "expected"),
    [
        ([], {}, "zh-Hant"),
        (["--lang", "zh_TW"], {}, "zh-Hant"),
        (["--lang=zh-CN"], {}, "zh-Hans"),
        (["--lang", "EN"], {}, "en"),
        ([], {"RPA_LANG": "en_US.UTF-8"}, "en"),
        # 無效的值略過，交給 click 回報錯誤
        (["--lang", "fr"], {"RPA_LANG": "zh-Hans"}, "zh-Hans"),
        # -- 之後是給子命令的參數，不屬於 rpa
        (["--", "--lang", "en"], {}, "zh-Hant"),
    ],
)
def test_resolve_locale(args: list[str], environ: dict[str, str], expected: str) -> None:
    assert resolve_locale(args, environ) == expected


def test_invalid_lang_is_reported_in_current_language() -> None:
    result = invoke(["--lang", "fr"])

    assert result.exit_code == 2
    assert "錯誤：" in result.output
    assert "不支援 fr" in result.output


def test_unknown_option_error_is_translated() -> None:
    result = invoke(["--lang", "en", "--bogus"])
    assert "No such option" in result.output

    result = invoke(["--bogus"])
    assert "沒有 '--bogus' 這個選項" in result.output


def test_every_click_module_uses_translations() -> None:
    install_click_translations()

    untranslated = [
        name
        for name, module in sys.modules.items()
        if (name == "click" or name.startswith("click."))
        and (
            getattr(module, "_", None) is gettext.gettext
            or getattr(module, "ngettext", None) is gettext.ngettext
        )
    ]
    assert not untranslated, f"這些 click 模組沒有套用翻譯：{untranslated}"


def test_entry_point_uses_lang_option() -> None:
    result = run_module("--lang", "en", "--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"rpa {rpa_cli.__version__} (rpa-core {rpa_core.__version__})\n"


def test_entry_point_uses_env_var() -> None:
    result = run_module("-h", RPA_LANG="zh-Hans")

    assert result.returncode == 0, result.stderr
    assert "浏览器自动化" in result.stdout
