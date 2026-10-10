"""`rpa validate` 與 `rpa schema`。"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner, Result

from rpa_cli.i18n import install_click_translations, resolve_locale
from rpa_cli.main import build_cli
from rpa_cli.validate import collect_files
from rpa_core.i18n import use_locale

GOOD = """\
schemaVersion: 1
id: good
name: 合法
steps:
  - id: open
    action: goto
    url: https://example.test/
"""

BAD = """\
schemaVersion: 1
id: bad
name: 有錯
steps:
  - id: open
    action: goto
    url: https://example.test/
  - id: shot
    action: screenshot
    fullpage: true
"""


def invoke(args: list[str], environ: Mapping[str, str] | None = None) -> Result:
    with use_locale(resolve_locale(args, environ or {})):
        install_click_translations()
        return CliRunner().invoke(build_cli(), args)


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """在暫存目錄中執行，輸出的路徑是相對路徑。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "good.yaml").write_text(GOOD, encoding="utf-8")
    (tmp_path / "bad.yaml").write_text(BAD, encoding="utf-8")
    return tmp_path


def test_valid_file(workdir: Path) -> None:
    result = invoke(["validate", "good.yaml"])

    assert result.exit_code == 0, result.output
    assert result.output == "檢查 1 個檔案，全部通過。\n"


def test_invalid_file_reports_location_step_and_field(workdir: Path) -> None:
    result = invoke(["validate", "good.yaml", "bad.yaml"])

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "bad.yaml:10:5: 步驟 2（shot） › fullpage：不認得的欄位 fullpage，是不是 fullPage？",
        "檢查 2 個檔案，1 個未通過，共 1 個問題。",
    ]


def test_english(workdir: Path) -> None:
    result = invoke(["--lang", "en", "validate", "bad.yaml"])

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "bad.yaml:10:5: Step 2 (shot) › fullpage: Unknown field fullpage. Did you mean fullPage?",
        "Files checked: 1. Failed: 1. Problems: 1.",
    ]


def test_json_format(workdir: Path) -> None:
    result = invoke(["validate", "--format", "json", "good.yaml", "bad.yaml"])

    assert result.exit_code == 1
    report = cast("dict[str, object]", json.loads(result.output))
    assert report["summary"] == {"files": 2, "invalid": 1, "issues": 1}
    files = cast("list[dict[str, object]]", report["files"])
    assert [(f["path"], f["valid"]) for f in files] == [("good.yaml", True), ("bad.yaml", False)]
    assert files[1]["issues"] == [
        {
            "line": 10,
            "column": 5,
            "step": 2,
            "stepId": "shot",
            "field": "fullpage",
            "path": ["steps", 1, "fullpage"],
            "code": "unknown_field.suggest",
            "message": "不認得的欄位 fullpage，是不是 fullPage？",
        }
    ]


def test_directory_is_searched_recursively(workdir: Path) -> None:
    nested = workdir / "scenarios" / "erp"
    nested.mkdir(parents=True)
    (nested / "a.yml").write_text(GOOD, encoding="utf-8")
    (nested / "notes.txt").write_text("不是場景", encoding="utf-8")
    hidden = workdir / "scenarios" / ".cache"
    hidden.mkdir()
    (hidden / "x.yaml").write_text("壞掉: [", encoding="utf-8")

    result = invoke(["validate", "scenarios"])

    assert result.exit_code == 0, result.output
    assert "1 個檔案" in result.output


def test_empty_directory_fails(workdir: Path) -> None:
    (workdir / "empty").mkdir()
    result = invoke(["validate", "empty"])

    assert result.exit_code == 1
    assert "empty 裡找不到 .yaml 或 .yml 檔。" in result.output


def test_missing_path_is_a_usage_error(workdir: Path) -> None:
    result = invoke(["validate", "nope.yaml"])

    assert result.exit_code == 2
    assert "不存在" in result.output


def test_path_is_required(workdir: Path) -> None:
    result = invoke(["validate"])

    assert result.exit_code == 2
    assert "缺少參數" in result.output


def test_yaml_syntax_error(workdir: Path) -> None:
    (workdir / "broken.yaml").write_text("steps: [\n", encoding="utf-8")
    result = invoke(["validate", "broken.yaml"])

    assert result.exit_code == 1
    assert result.output.startswith("broken.yaml:2:1: YAML 語法錯誤：")


def test_collect_files_deduplicates(workdir: Path) -> None:
    files, empty = collect_files([Path("good.yaml"), workdir, Path("good.yaml")])

    assert empty == []
    names = [p.name for p in files]
    assert names.count("good.yaml") == 2  # 相對與絕對路徑視為不同的寫法，但同一寫法只出現一次
    assert len(files) == len(set(files))


def test_help_lists_new_commands() -> None:
    result = invoke(["-h"])

    assert "validate" in result.output
    assert "校驗場景檔。" in result.output
    assert "schema" in result.output


def test_validate_help_is_translated() -> None:
    result = invoke(["validate", "-h"])

    assert result.exit_code == 0
    assert "路徑..." in result.output
    assert "text 給人看" in result.output


def test_schema_command() -> None:
    result = invoke(["schema"])

    assert result.exit_code == 0
    schema = cast("dict[str, object]", json.loads(result.output))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "Scenario"
