"""運行環境模式的 Python 節點（ADR 0020）：runtime 階段、rpa_script、共用工作資料夾、斷言與失敗。

運行環境用一個假的：標準函式庫的 venv（不裝 pip），site-packages 放一個指到 rpa_script 原始碼的
.pth，再加上 rpa-runtime.json；以 RPA_PYTHON_RUNTIME 指給 Runner。不需要瀏覽器。
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

import rpa_script
from rpa_core.i18n import use_locale
from rpa_runner.files import FACTS, OUTPUT, RESULT, STEPS
from rpa_runner.pyruntime import ENV_RUNTIME, MANIFEST, platform_tag
from rpa_runner.run import RunResult, execute

pytestmark = pytest.mark.skipif(os.name == "nt", reason="假的運行環境用 venv 的 bin/python3")


@pytest.fixture(scope="module")
def fake_runtime(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("runtime")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root)], check=True)
    site = subprocess.run(
        [str(root / "bin" / "python3"), "-c", "import site; print(site.getsitepackages()[0])"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source = Path(rpa_script.__file__).resolve().parent.parent
    Path(site, "rpa_script_src.pth").write_text(f"{source}\n", encoding="utf-8")
    manifest = {"version": "1.0.0", "platform": platform_tag(), "python": sys.version.split()[0]}
    (root / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _runtime(fake_runtime: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(ENV_RUNTIME, str(fake_runtime))
    with use_locale("zh-Hant"):
        yield


def node(
    folder: Path,
    automation: str,
    *,
    extra: str = "",
    files: dict[str, str] | None = None,
    name: str = "node",
    assertion: str | None = None,
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "automation.py").write_text(automation, encoding="utf-8")
    if assertion is not None:
        (folder / "assertion.py").write_text(assertion, encoding="utf-8")
    for relative, content in (files or {}).items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(content, encoding="utf-8")
    path = folder / "scenario.yaml"
    path.write_text(
        f"schemaVersion: 1\nid: {name}\nname: 節點\n"
        + extra
        + "script:\n  runtime: '1'\n  automation: automation.py\n"
        + ("  assertion: assertion.py\n" if assertion is not None else "")
        + ("  files: [" + ", ".join(files) + "]\n" if files else ""),
        encoding="utf-8",
    )
    return path


def read(result: RunResult, name: str) -> object:
    return json.loads((result.directory / name).read_text(encoding="utf-8"))


def steps_of(result: RunResult) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", read(result, STEPS))


MERGE = """\
import os
from rpa_script import Run, StepError, automation
from helpers import total


@automation
def main(run: Run) -> None:
    run.log("token " + os.environ["API_TOKEN"])
    with run.step("write", "寫出"):
        (run.output_dir / "summary.csv").write_text("a,b\\n", encoding="utf-8")
        run.preview("資料", [{"name": n, "value": v} for n, v in run.inputs["rows"]])
    for name, value in run.inputs["rows"]:
        with run.step("check", f"檢查 {name}"):
            if value < 0:
                raise StepError(f"{name} 是負數")
    run.facts.update(
        total=total(run.inputs["rows"]),
        byName={n: v for n, v in run.inputs["rows"]},
        cwd=os.getcwd(),
        path=os.environ.get("PYTHONPATH", ""),
    )
"""
MERGE_EXTRA = (
    "inputs:\n  rows: { type: array, default: [[A, 3], [B, 4]] }\n"
    "outputs:\n"
    "  total: { type: number, from: '{{ facts.total }}' }\n"
    "  byName: { type: object, from: '{{ facts.byName }}' }\n"
    "secrets: [API_TOKEN]\n"
    "verify:\n  - { value: '{{ facts.total }}', matches: '^[1-9]' }\n"
)


def test_runtime_node_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_TOKEN", "secret-value-123")
    monkeypatch.setenv("PYTHONPATH", "/should/not/leak")
    path = node(
        tmp_path / "scene",
        MERGE,
        extra=MERGE_EXTRA,
        files={"helpers.py": "def total(rows):\n    return sum(v for _, v in rows)\n"},
    )
    result = execute(path, {}, out_root=tmp_path / "runs")

    assert result.status == "passed", (result.error, result.problems)
    assert result.output == {"total": 7, "byName": {"A": 3, "B": 4}}
    assert [stage.name for stage in result.stages] == [
        "input",
        "runtime",
        "automation",
        "verify",
        "output",
    ]
    assert result.python is not None
    assert result.python["mode"] == "runtime"
    assert result.python["runtime"] == "1.0.0"
    facts = cast("dict[str, object]", read(result, FACTS))
    assert facts["path"] == ""  # 運行環境的子程序拿不到電腦上的 PYTHONPATH
    workspace = Path(str(facts["cwd"]))
    assert workspace.name.startswith(".work-")
    assert not workspace.exists()  # 單獨執行：結束就刪
    steps = steps_of(result)
    assert [(s["id"], s["occurrence"], s["status"]) for s in steps] == [
        ("write", 1, "passed"),
        ("check", 1, "passed"),
        ("check", 2, "passed"),
    ]
    assert steps[0]["source"] == "automation.py:9"
    assert steps[0]["previews"] == ["previews/001.json"]
    preview = json.loads((result.directory / "previews" / "001.json").read_text("utf-8"))
    assert preview["columns"] == ["name", "value"]
    assert preview["rows"] == [["A", 3], ["B", 4]]
    assert (result.directory / "outputs" / "summary.csv").is_file()
    log = (result.directory / "automation.log").read_text(encoding="utf-8")
    assert "token ***" in log
    assert "secret-value-123" not in log
    assert not list((result.directory / "scenario").rglob("__pycache__"))
    saved = read(result, RESULT)
    assert isinstance(saved, dict)
    assert saved["python"] == result.python
    assert saved["kind"] == "script"


def test_nodes_of_one_composite_share_a_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    first = node(
        tmp_path / "first",
        "from pathlib import Path\nfrom rpa_script import automation\n"
        "@automation\ndef main(run):\n"
        "    (run.workspace / 'downloads').mkdir()\n"
        "    (run.workspace / 'downloads' / 'a.txt').write_text('甲', encoding='utf-8')\n",
        name="first",
    )
    second = node(
        tmp_path / "second",
        "from pathlib import Path\nfrom rpa_script import automation\n"
        "@automation\ndef main(run):\n"
        "    run.facts['seen'] = Path('downloads/a.txt').read_text(encoding='utf-8')\n",
        name="second",
    )
    one = execute(first, {}, out_root=tmp_path / "runs", workspace=workspace)
    two = execute(second, {}, out_root=tmp_path / "runs", workspace=workspace)
    assert one.status == two.status == "passed", (one.error, two.error)
    assert read(two, FACTS) == {"seen": "甲"}
    assert (workspace / "downloads" / "a.txt").is_file()  # 組合運行結束前不刪


def test_step_error_shows_only_the_message(tmp_path: Path) -> None:
    path = node(
        tmp_path / "scene",
        "from rpa_script import StepError, automation\n"
        "@automation\ndef main(run):\n"
        "    with run.step('find', '找報表'):\n"
        "        raise StepError('沒有 2026-10 的報表')\n",
    )
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "failed"
    assert result.error is not None
    assert "找報表：沒有 2026-10 的報表" in result.error
    log = (result.directory / "automation.log").read_text(encoding="utf-8")
    assert "Traceback" not in log
    assert not (result.directory / OUTPUT).exists()


def test_error_outside_steps_is_recorded_with_its_line(tmp_path: Path) -> None:
    path = node(tmp_path / "scene", "import json\n\nvalue = 1 / 0\n")
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "failed"
    steps = steps_of(result)
    assert steps[-1]["id"] == "script"
    assert steps[-1]["source"] == "automation.py:3"
    assert "ZeroDivisionError" in str(steps[-1]["error"])
    log = (result.directory / "automation.log").read_text(encoding="utf-8")
    assert "automation.py" in log
    assert "rpa_script" not in log  # 呼叫堆疊只留場景自己的檔案


def test_plain_scripts_keep_the_file_contract(tmp_path: Path) -> None:
    path = node(
        tmp_path / "scene",
        "import argparse, json\nfrom pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "for name in ('input', 'facts', 'screenshot', 'target-url'):\n"
        "    parser.add_argument(f'--{name}', required=True)\n"
        "args = parser.parse_args()\n"
        "params = json.loads(Path(args.input).read_text(encoding='utf-8'))\n"
        "Path(args.facts).write_text(json.dumps({'echo': params['x'], 'url': args.target_url}),"
        " encoding='utf-8')\n",
        extra="inputs:\n  x: { type: object }\n",
    )
    result = execute(path, {"x": {"a": [1, 2]}}, out_root=tmp_path / "runs")
    assert result.status == "passed", result.error
    assert read(result, FACTS) == {"echo": {"a": [1, 2]}, "url": ""}


def test_assertion_runs_in_the_runtime(tmp_path: Path) -> None:
    path = node(
        tmp_path / "scene",
        "from rpa_script import automation\n@automation\ndef main(run):\n    run.facts['n'] = 3\n",
        extra="outputs:\n  n: { type: integer }\n  exe: { type: string }\n",
        assertion=(
            "import argparse, json, sys\nfrom pathlib import Path\n"
            "p = argparse.ArgumentParser()\n"
            "for n in ('input', 'facts', 'output'):\n    p.add_argument(f'--{n}', required=True)\n"
            "a = p.parse_args()\n"
            "facts = json.loads(Path(a.facts).read_text(encoding='utf-8'))\n"
            "Path(a.output).write_text(json.dumps({'n': facts['n'], 'exe': sys.executable}),"
            " encoding='utf-8')\n"
        ),
    )
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "passed", (result.error, result.problems)
    assert result.output is not None
    assert result.output["n"] == 3
    assert "runtime" in str(result.output["exe"])  # 斷言也用運行環境的 Python


def test_missing_runtime_stops_before_the_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_RUNTIME)
    monkeypatch.setenv("RPA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("RPA_PYTHON_ARCHIVES", str(tmp_path / "none"))
    path = node(tmp_path / "scene", "raise SystemExit('should not run')\n")
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "failed"
    assert result.stage("runtime").status == "failed"
    assert "RPA Python 運行環境 1 準備失敗" in str(result.error)
    assert result.stage("automation").status == "skipped"


def test_platforms_other_than_this_computer(tmp_path: Path) -> None:
    other = {"windows": "linux", "macos": "linux", "linux": "windows"}[platform_tag().split("-")[0]]
    path = node(tmp_path / "scene", "print('no')\n")
    path.write_text(
        path.read_text(encoding="utf-8") + f"  platforms: [{other}]\n", encoding="utf-8"
    )
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "failed"
    assert f"只在 {other} 執行" in str(result.error)


def test_deadline_stops_the_script_and_its_children(tmp_path: Path) -> None:
    path = node(
        tmp_path / "scene",
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "time.sleep(60)\n",
        extra="deadline: 1500\n",
    )
    started = time.monotonic()
    result = execute(path, {}, out_root=tmp_path / "runs")
    assert result.status == "timed_out"
    assert time.monotonic() - started < 15


def test_file_inputs_reach_the_script(tmp_path: Path) -> None:
    source = tmp_path / "報表.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    path = node(
        tmp_path / "scene",
        "from pathlib import Path\nfrom rpa_script import automation\n"
        "@automation\ndef main(run):\n"
        "    files = run.input_files['report']\n"
        "    run.facts['lines'] = len(Path(files[0]).read_text(encoding='utf-8').splitlines())\n",
        extra="inputs:\n  report: { type: file }\n",
    )
    result = execute(
        path, {"report": {"path": str(source)}}, out_root=tmp_path / "runs", any_path=True
    )
    assert result.status == "passed", (result.error, result.problems)
    assert read(result, FACTS) == {"lines": 2}
