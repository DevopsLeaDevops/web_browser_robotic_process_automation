"""版本檔案的檢查、寫入、雜湊與執行目錄的檔案。不需要資料庫。"""

from pathlib import Path

import pytest

from rpa_core.dsl import validate_file
from rpa_runner.run import scenario_digest
from rpa_server.storage import SCENARIO_FILE, Storage, StorageConflictError, new_scene_template

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.ensure()
    return storage


def script_files() -> dict[str, str]:
    folder = DEMO / "ba-001-script"
    return {
        name: (folder / name).read_text(encoding="utf-8")
        for name in ("scenario.yaml", "automation.py", "assertion.py")
    }


def test_new_scene_template_is_valid(storage: Storage) -> None:
    text = new_scene_template("demo-x", '名稱 "引號" #不是註解', "分類: 有冒號")

    checked = storage.check({SCENARIO_FILE: text}, scene_id="demo-x")

    assert checked.ok, checked.issues
    assert checked.scenario is not None
    assert checked.scenario.name == '名稱 "引號" #不是註解'
    assert checked.scenario.category == "分類: 有冒號"


def test_check_reports_scenario_issues_with_positions(storage: Storage) -> None:
    text = (
        (DEMO / "ba-001.yaml").read_text(encoding="utf-8").replace("action: click", "action: tap")
    )

    checked = storage.check({SCENARIO_FILE: text}, scene_id="ba-001")

    assert not checked.ok
    assert checked.issues[0].position is not None
    assert checked.issues[0].step == 4


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"other.yaml": "x"}, "server.no_scenario"),
        ({SCENARIO_FILE: "x", "../escape.py": ""}, "server.bad_path"),
        ({SCENARIO_FILE: "x", ".hidden": ""}, "server.bad_path"),
        ({SCENARIO_FILE: "x" * 1_000_001}, "server.too_large"),
    ],
)
def test_check_rejects_bad_files(storage: Storage, files: dict[str, str], code: str) -> None:
    checked = storage.check(files)
    assert code in [issue.code for issue in checked.issues]


def test_check_rejects_other_id_and_unused_files(storage: Storage) -> None:
    text = (DEMO / "ba-001.yaml").read_text(encoding="utf-8")

    checked = storage.check({SCENARIO_FILE: text, "notes.txt": "x"}, scene_id="ba-009")

    assert [issue.code for issue in checked.issues] == ["server.id_mismatch", "server.extra_file"]
    assert checked.issues[0].message == "場景檔的 id 必須是 ba-009（場景編號不能修改）"


def test_script_scenario_needs_its_scripts(storage: Storage) -> None:
    files = script_files()
    del files["assertion.py"]

    assert not storage.check(files, scene_id="ba-001-script").ok


def test_save_load_and_digest_match_the_runner(storage: Storage) -> None:
    files = script_files()
    checked = storage.check(files, scene_id="ba-001-script")
    assert checked.ok
    assert checked.scenario is not None

    storage.save("ba-001-script", 1, files)

    path = storage.scenario_path("ba-001-script", 1)
    assert storage.load("ba-001-script", 1) == files
    assert storage.digest("ba-001-script", 1) == checked.digest
    assert scenario_digest(path, checked.scenario) == checked.digest
    scenario = validate_file(DEMO / "ba-001-script" / "scenario.yaml").scenario
    assert scenario is not None
    assert scenario_digest(DEMO / "ba-001-script" / "scenario.yaml", scenario) == checked.digest


def test_revisions_are_never_overwritten(storage: Storage) -> None:
    text = new_scene_template("demo-x", "甲", None)
    storage.save("demo-x", 1, {SCENARIO_FILE: text})

    with pytest.raises(StorageConflictError):
        storage.save("demo-x", 1, {SCENARIO_FILE: text + "# 改過\n"})

    assert storage.load("demo-x", 1) == {SCENARIO_FILE: text}
    assert not [p for p in storage.revision_dir("demo-x", 1).parent.iterdir() if p.name != "1"]


def test_line_endings_are_kept(storage: Storage) -> None:
    text = new_scene_template("demo-x", "甲", None).replace("\n", "\r\n")
    storage.save("demo-x", 1, {SCENARIO_FILE: text})
    assert storage.load("demo-x", 1)[SCENARIO_FILE] == text


def test_run_files_stay_inside_the_run_folder(storage: Storage) -> None:
    folder = storage.run_dir("run-1")
    (folder / "scenario").mkdir(parents=True)
    (folder / "report.html").write_text("<p>ok</p>", encoding="utf-8")
    (folder / "scenario" / "scenario.yaml").write_text("id: x", encoding="utf-8")
    (storage.root / "secret.txt").write_text("不能讀", encoding="utf-8")

    assert storage.run_files("run-1") == ["report.html", "scenario/scenario.yaml"]
    assert storage.run_file("run-1", "report.html") == (folder / "report.html").resolve()
    assert storage.run_file("run-1", "../../secret.txt") is None
    assert storage.run_file("run-1", "missing.png") is None
    assert storage.run_files("no-such-run") == []
