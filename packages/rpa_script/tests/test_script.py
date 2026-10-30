"""rpa_script 的單元測試：步驟、事實、預覽、遮罩與啟動器（ADR 0020）。"""

import json
import sys
from pathlib import Path

import pytest

from rpa_script import Run, StepError
from rpa_script.__main__ import main
from rpa_script.core import _preview, describe  # pyright: ignore[reportPrivateUsage]


def make_run(tmp_path: Path) -> Run:
    clock = iter(float(n) for n in range(100))
    return Run(
        inputs={"x": 1},
        facts_path=tmp_path / "facts.json",
        steps_path=tmp_path / "steps.json",
        output_dir=tmp_path / "outputs",
        workspace=tmp_path,
        input_files={},
        secrets={"TOKEN": "abcd1234", "PIN": "123"},
        deadline_seconds=None,
        clock=lambda: next(clock),
    )


def test_steps_record_occurrence_nesting_and_failure(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with run.step("outer", "外層"):
        for _ in range(2):
            with run.step("inner"):
                pass
    with pytest.raises(StepError), run.step("bad", "壞掉 abcd1234"):
        raise StepError("找不到 abcd1234")
    steps = json.loads((tmp_path / "steps.json").read_text(encoding="utf-8"))
    assert [(s["id"], s["occurrence"], s["parent"], s["status"]) for s in steps] == [
        ("outer", 1, None, "passed"),
        ("inner", 1, "outer", "passed"),
        ("inner", 2, "outer", "passed"),
        ("bad", 1, None, "failed"),
    ]
    assert steps[3]["name"] == "壞掉 ***"
    assert steps[3]["error"] == "找不到 ***"
    assert steps[0]["action"] == "python"
    assert steps[0]["startedAt"].endswith("Z")


def test_step_ids_follow_the_dsl_rules(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with pytest.raises(ValueError, match=r"Step|步驟"), run.step("Not OK"):
        pass


def test_facts_merge_with_what_the_script_wrote(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    (tmp_path / "facts.json").write_text('{"a": 1}', encoding="utf-8")
    run.facts["b"] = 2
    run.write_facts()
    assert json.loads((tmp_path / "facts.json").read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_masking_keeps_short_values(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.mask("abcd1234 and 123") == "*** and 123"


def test_preview_shapes(tmp_path: Path) -> None:
    def mask(text: str) -> str:
        return text

    rows = [{"name": f"n{i}", "value": i} for i in range(60)]
    table = _preview(rows, mask)
    assert table["kind"] == "table"
    assert table["rowCount"] == 60
    assert len(table["rows"]) == 50  # type: ignore[arg-type]
    assert table["truncated"] is True
    assert _preview([[1, "a" * 300]], mask)["rows"] == [[1, "a" * 199 + "…"]]
    assert _preview({"a": 1}, mask) == {"kind": "json", "text": '{\n  "a": 1\n}'}
    assert _preview("hi", mask) == {"kind": "text", "text": "hi"}


def test_describe() -> None:
    assert describe(StepError("說明")) == "說明"
    assert describe(KeyError("x")) == "KeyError: 'x'"
    assert describe(RuntimeError()) == "RuntimeError"


def test_launcher_runs_plain_and_decorated_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "automation.py"
    script.write_text(
        "import sys\nfrom rpa_script import automation\n"
        "print('argv', sys.argv[1:3])\n"
        "@automation\ndef main(run):\n"
        "    with run.step('one'):\n        run.facts['x'] = run.inputs['x'] + 1\n",
        encoding="utf-8",
    )
    (tmp_path / "input.json").write_text('{"x": 41}', encoding="utf-8")
    monkeypatch.setenv("RPA_STEPS", str(tmp_path / "steps.json"))
    monkeypatch.setenv("RPA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    import rpa_script.core as core

    monkeypatch.setattr(core, "_ENTRIES", [])
    monkeypatch.setattr(core, "_CURRENT", [])
    args = [
        str(script),
        "--input",
        str(tmp_path / "input.json"),
        "--facts",
        str(tmp_path / "f.json"),
    ]
    stdout, stderr = sys.stdout, sys.stderr
    try:
        code = main(args)
    finally:
        sys.stdout, sys.stderr = stdout, stderr
    assert code == 0
    assert json.loads((tmp_path / "f.json").read_text(encoding="utf-8")) == {"x": 42}
    assert "argv ['--input'" in capsys.readouterr().out
