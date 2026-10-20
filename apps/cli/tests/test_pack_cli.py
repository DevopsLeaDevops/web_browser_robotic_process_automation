"""`rpa pack check`：校驗領域資料夾（M11）。"""

import json
import shutil
from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner, Result

from rpa_cli.i18n import install_click_translations
from rpa_cli.pack import build_pack_command
from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_core.i18n import Locale, use_locale
from rpa_core.pack import PackManifest, RevisionInfo, SceneManifest, ServerRef, write_model

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"


def invoke(args: list[str], locale: Locale = "zh-Hant") -> Result:
    with use_locale(locale):
        install_click_translations()
        return CliRunner().invoke(build_pack_command(), args)


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """在暫存目錄中執行：一個只有 ba-001 第 1 版的 testsite 資料夾。"""
    monkeypatch.chdir(tmp_path)
    pack = tmp_path / "testsite"
    write_model(pack / "pack.yaml", PackManifest(spec_version=1, id="testsite", name="測試網站"))
    write_model(pack / "scenes" / "ba-001" / "scene.yaml", SceneManifest(id="ba-001"))
    revision = pack / "scenes" / "ba-001" / "revisions" / "1"
    revision.mkdir(parents=True)
    shutil.copyfile(DEMO / "ba-001.yaml", revision / "scenario.yaml")
    scenario = validate_file(revision / "scenario.yaml").scenario
    assert scenario is not None
    info = RevisionInfo(
        number=1,
        hash=scenario_digest(revision / "scenario.yaml", scenario),
        created_at="2026-10-19T05:10:00-07:00",
        by="甲",
        server=ServerRef(id="3a9d", name="jia-mac"),
    )
    write_model(revision.with_name("1.yaml"), info)
    return pack


def test_valid_folder(folder: Path) -> None:
    result = invoke(["check", "testsite"])

    assert result.exit_code == 0, result.output
    assert result.output == "testsite（testsite）：1 個場景、0 個角色，沒有錯誤（0 個警告）。\n"


def test_errors_and_warnings_with_positions(folder: Path) -> None:
    scenario = folder / "scenes" / "ba-001" / "revisions" / "1" / "scenario.yaml"
    scenario.write_text(scenario.read_text(encoding="utf-8") + "# 改過\n", encoding="utf-8")
    (scenario.parent / "notes.txt").write_text("x", encoding="utf-8")
    (folder / "pack.yaml").write_text(
        "specVersion: 1\nid: testsite\nname: 測試網站\nrequirse: []\n", encoding="utf-8"
    )

    result = invoke(["check", "testsite", "--id", "testsite"])

    assert result.exit_code == 1
    lines = result.output.splitlines()
    assert lines[0].startswith("testsite/pack.yaml:4:1: ")
    assert "requires" in lines[0]
    assert any(
        line.startswith("testsite/scenes/ba-001/revisions/1/notes.txt: 警告：") for line in lines
    )
    assert any("雜湊不同" in line for line in lines)
    assert lines[-1] == "testsite（?）：1 個場景、0 個角色，2 個錯誤、1 個警告。"


def test_json_report(folder: Path) -> None:
    result = invoke(["check", "testsite", "--format", "json"], "en")

    assert result.exit_code == 0, result.output
    report = cast("list[dict[str, object]]", json.loads(result.output))
    assert report[0]["id"] == "testsite"
    assert report[0]["valid"] is True
    scenes = cast("dict[str, dict[str, object]]", report[0]["scenes"])
    assert scenes["ba-001"]["latest"] == 1
    assert scenes["ba-001"]["published"] is None


def test_wrong_id(folder: Path) -> None:
    result = invoke(["check", "testsite", "--id", "scm_purchase"], "en")

    assert result.exit_code == 1
    assert "The id in pack.yaml is testsite; it should be scm_purchase" in result.output
