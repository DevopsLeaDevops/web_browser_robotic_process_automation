"""`rpa record`：錄製（codegen 換成假的）與轉換已經錄好的原始稿。"""

from collections.abc import Sequence
from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner, Result

import rpa_cli.record
from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_core.dsl import validate_file
from rpa_core.i18n import use_locale

SOURCE = dedent(
    """\
    def run(playwright):
        page = context.new_page()
        page.goto("https://erp.example.com/login")
        page.get_by_label("帳號").fill("clerk01")
        page.get_by_label("密碼").fill("p@ssw0rd!")
        page.get_by_role("button", name="登入").click()
        page.get_by_text("選單").hover()
    """
)


def invoke(args: list[str]) -> Result:
    with use_locale("zh-Hant"):
        install_click_translations()
        return CliRunner().invoke(build_cli(), args)


def test_convert_an_existing_recording(tmp_path: Path) -> None:
    source = tmp_path / "raw.py"
    source.write_text(SOURCE, encoding="utf-8")
    out = tmp_path / "erp-login.py"
    scenario = tmp_path / "erp-login.yaml"

    result = invoke(
        ["record", "--from", str(source), "--out", str(out), "--scenario", str(scenario)]
    )

    assert result.exit_code == 0, result.output
    assert "p@ssw0rd!" not in out.read_text(encoding="utf-8")
    assert 'fill("***")' in out.read_text(encoding="utf-8")
    assert "ERP_LOGIN_PASSWORD" in result.output
    assert "第 7 行轉不了" in result.output
    checked = validate_file(scenario)
    assert checked.scenario is not None, checked.issues
    assert checked.scenario.id == "erp-login"
    assert checked.scenario.secrets == ["ERP_LOGIN_PASSWORD"]
    assert "p@ssw0rd!" not in scenario.read_text(encoding="utf-8")


def test_record_with_codegen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_codegen(command: Sequence[str]) -> int:
        seen.append(list(command))
        output = Path(command[command.index("--output") + 1])
        output.write_text(SOURCE, encoding="utf-8")
        return 0

    monkeypatch.setattr(rpa_cli.record, "codegen", fake_codegen)
    out = tmp_path / "rec" / "demo.py"
    result = invoke(
        [
            "record",
            "https://erp.example.com/login",
            "--out",
            str(out),
            "--browser",
            "firefox",
            "--id",
            "demo-001",
            "--name",
            "示範",
        ]
    )

    assert result.exit_code == 0, result.output
    command = seen[0]
    assert command[1:4] == ["-m", "playwright", "codegen"]
    assert command[command.index("--browser") + 1] == "firefox"
    assert command[-1] == "https://erp.example.com/login"
    # 含密碼的暫存原始稿已刪除，只留下遮罩過的版本
    assert sorted(path.name for path in out.parent.iterdir()) == ["demo.py"]
    assert "p@ssw0rd!" not in out.read_text(encoding="utf-8")


def test_record_without_url_or_with_failed_codegen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert invoke(["record"]).exit_code == 2

    def failing(command: Sequence[str]) -> int:
        return 1

    monkeypatch.setattr(rpa_cli.record, "codegen", failing)
    result = invoke(["record", "https://example.com", "--out", str(tmp_path / "x.py")])
    assert result.exit_code == 1
    assert "結束碼 1" in result.output
    assert not (tmp_path / "x.py").exists()
