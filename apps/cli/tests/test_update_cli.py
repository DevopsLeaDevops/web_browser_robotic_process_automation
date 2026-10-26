"""`rpa update`（ADR 0018）：不是裝好的分發包時說明怎麼做、更新檔的錯誤用自己語言的訊息。

安裝本身在 apps/server/tests/test_updates.py；真正的分發包在 CI（server-package.yml）。
"""

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from rpa_cli.i18n import install_click_translations, t
from rpa_cli.main import build_cli
from rpa_cli.update import describe_error
from rpa_core.i18n import LOCALES, Locale, use_locale


def invoke(args: list[str], env: dict[str, str], locale: Locale = "zh-Hant") -> Result:
    with use_locale(locale):
        install_click_translations()
        return CliRunner().invoke(build_cli(), args, env=env)


def installed(tmp_path: Path) -> dict[str, str]:
    release = tmp_path / "srv" / "releases" / "0.5.0-aaaaaaa"
    release.mkdir(parents=True)
    (tmp_path / "srv" / "current").symlink_to("releases/0.5.0-aaaaaaa")
    return {"RPA_RELEASE_DIR": str(release)}


def test_update_needs_an_installed_bundle(tmp_path: Path) -> None:
    update = tmp_path / "RPA-Update-0.6.0.zip"
    update.write_bytes(b"")
    result = invoke(["update", str(update)], {"RPA_RELEASE_DIR": ""})
    assert result.exit_code == 1
    assert "不是用 install.sh 裝好的伺服器分發包" in result.output


def test_update_explains_a_bad_file(tmp_path: Path) -> None:
    update = tmp_path / "RPA-Update-0.6.0.zip"
    update.write_text("not a zip", encoding="utf-8")
    # 開發環境沒有 runtime.json：先說明這不是分發包的執行環境
    result = invoke(["update", str(update)], installed(tmp_path), "en")
    assert result.exit_code == 1
    assert "not a bundle runtime" in result.output


def test_update_help_in_english() -> None:
    result = invoke(["update", "-h"], {}, "en")
    assert result.exit_code == 0
    assert "--now" in result.output
    assert "update file" in result.output


@pytest.mark.parametrize("locale", LOCALES)
def test_every_error_code_has_a_message(locale: Locale) -> None:
    codes = {
        "not_packaged": {},
        "no_build_for_target": {"target": "server-linux-x64", "version": "0.6.0"},
        "runtime_missing": {"runtime": "0" * 16, "version": "0.6.0"},
        "release_broken": {"detail": "ImportError"},
        "not_an_update": {"error": "x"},
        "signature_invalid": {},
        "signature_untrusted": {"key": "k"},
        "signature_mismatch": {"key": "k"},
        "no_trusted_keys": {},
        "manifest_invalid": {"field": "files"},
        "manifest_format": {"format": 2},
        "unsafe_path": {"path": "../x"},
        "unexpected_file": {"path": "x.so"},
        "file_mismatch": {"path": "x.py"},
        "file_missing": {"path": "x.py"},
        "runtime_invalid": {},
        "runtime_unreadable": {"error": "x"},
    }
    with use_locale(locale):
        for code, params in codes.items():
            message = describe_error(code, dict(params))
            assert message != t("cli.update.error.other", code=code), code
        assert "mystery" in describe_error("mystery", {"a": 1})
