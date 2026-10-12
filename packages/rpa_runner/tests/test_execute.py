"""execute 的控制參數：指定執行編號、階段回呼、事先取消。不需要瀏覽器。"""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import validate_file
from rpa_core.i18n import ENV_VAR, Locale, use_locale
from rpa_runner import child
from rpa_runner.files import OUTPUT, REPORT, RESULT, read_json, read_json_or, write_json
from rpa_runner.run import execute, new_run_id, scenario_digest, scenario_sources

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"
BA_001_SCRIPT = ROOT / "scenarios" / "demo" / "ba-001-script" / "scenario.yaml"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def test_run_id_stage_callback_and_digest(tmp_path: Path) -> None:
    stages: list[str] = []
    # 入參錯誤：只會進入第一個階段，不會啟動瀏覽器
    result = execute(
        BA_001, {"quantity": 100}, out_root=tmp_path, run_id="ba-001-指定", on_stage=stages.append
    )
    scenario = validate_file(BA_001).scenario
    assert scenario is not None

    assert result.run_id == "ba-001-指定"
    assert result.directory == tmp_path / "ba-001-指定"
    assert (result.directory / RESULT).is_file()
    assert stages == ["input"]
    assert result.scenario_hash == scenario_digest(BA_001, scenario)


def test_cancel_before_start(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()

    result = execute(BA_001, {"title": "甲", "quantity": 1}, out_root=tmp_path, cancel=cancel)

    assert result.status == "cancelled"
    assert result.stage("input").status == "cancelled"
    assert result.error == "使用者中止；已停止子程序"
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / REPORT).is_file()


def test_script_scenario_digest_covers_scripts(tmp_path: Path) -> None:
    scenario = validate_file(BA_001_SCRIPT).scenario
    assert scenario is not None
    assert scenario_sources(BA_001_SCRIPT, scenario) == [
        "scenario.yaml",
        "automation.py",
        "assertion.py",
    ]

    copy = tmp_path / "copy"
    copy.mkdir()
    for name in scenario_sources(BA_001_SCRIPT, scenario):
        (copy / name).write_bytes((BA_001_SCRIPT.parent / name).read_bytes())
    same = scenario_digest(copy / "scenario.yaml", scenario)
    (copy / "assertion.py").write_text("# 改過\n", encoding="utf-8")

    assert same == scenario_digest(BA_001_SCRIPT, scenario)
    assert scenario_digest(copy / "scenario.yaml", scenario) != same


def test_new_run_id_format() -> None:
    run_id = new_run_id("ba-001")
    prefix, date, time, suffix = run_id.rsplit("-", 3)
    assert prefix == "ba-001"
    assert (len(date), len(time), len(suffix)) == (8, 6, 6)


def test_json_files_are_written_atomically(tmp_path: Path) -> None:
    path = tmp_path / "steps.json"
    write_json(path, [{"id": "甲"}])

    assert read_json(path) == [{"id": "甲"}]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["steps.json"]
    path.write_text("[{", encoding="utf-8")  # 舊版被終止時可能留下的半個檔案
    assert read_json_or(path, []) == []
    assert read_json_or(tmp_path / "missing.json", None) is None


LANGUAGE_PROBE = """\
schemaVersion: 1
id: lang-probe
name: Language probe
outputs:
  lang: {type: string}
script: {automation: automation.py, assertion: assertion.py}
"""
PROBE_AUTOMATION = """\
import argparse, json, os
from pathlib import Path
parser = argparse.ArgumentParser()
for name in ("input", "facts", "screenshot", "target-url"):
    parser.add_argument("--" + name)
args = parser.parse_args()
Path(args.facts).write_text(json.dumps({"lang": os.environ["RPA_LANG"]}), encoding="utf-8")
"""
PROBE_ASSERTION = """\
import argparse
from pathlib import Path
parser = argparse.ArgumentParser()
for name in ("input", "facts", "output"):
    parser.add_argument("--" + name)
args = parser.parse_args()
Path(args.output).write_text(Path(args.facts).read_text(encoding="utf-8"), encoding="utf-8")
"""


@pytest.mark.parametrize("locale", ["en", "zh-Hans"])
def test_child_processes_get_the_current_language(tmp_path: Path, locale: Locale) -> None:
    """子程序（場景步驟、automation.py、assertion.py）用 RPA_LANG 拿到目前的語言。不開瀏覽器。"""
    folder = tmp_path / "probe"
    folder.mkdir()
    (folder / "scenario.yaml").write_text(LANGUAGE_PROBE, encoding="utf-8")
    (folder / "automation.py").write_text(PROBE_AUTOMATION, encoding="utf-8")
    (folder / "assertion.py").write_text(PROBE_ASSERTION, encoding="utf-8")

    with use_locale(locale):
        result = execute(folder / "scenario.yaml", {}, out_root=tmp_path / "runs")

    assert result.status == "passed", result.error
    assert result.output == {"lang": locale}


@pytest.mark.parametrize(
    ("lang", "caller", "message"),
    [
        ("en", "zh-Hant", "The scenario did not pass validation"),
        ("zh-Hant", "en", "場景校驗失敗"),
    ],
)
def test_child_writes_its_log_in_the_given_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    lang: str,
    caller: Locale,
    message: str,
) -> None:
    """子程序看 RPA_LANG，不是呼叫端程序目前的語言。"""
    broken = tmp_path / "broken.yaml"
    broken.write_text("schemaVersion: 1\n", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, lang)

    with use_locale(caller):
        code = child.main(
            ["--scenario", str(broken), "--input", "x", "--out", str(tmp_path), "--deadline", "5"]
        )

    assert code == child.EXIT_FAILED
    assert message in capsys.readouterr().err
