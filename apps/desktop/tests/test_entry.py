"""打包後的入口：--rpa-module、--rpa-script、--version 與錯誤的用法（M10.0）。

打包後的 App 跑子程序就是靠這幾條路；這裡在開發環境直接呼叫 main 與以 python -m rpa_desktop
啟動，確認參數原封不動交給模組或腳本、結束碼照 Python 的規則。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rpa_desktop.entry import main, run_module, run_script
from rpa_runner.commands import FROZEN_MODULE, FROZEN_SCRIPT


def _desktop(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "rpa_desktop", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_script_receives_its_arguments_and_exit_code(tmp_path: Path) -> None:
    (tmp_path / "helper.py").write_text("VALUE = 'from-helper'\n", encoding="utf-8")
    script = tmp_path / "automation.py"
    script.write_text(
        "import json, sys\n"
        "import helper\n"
        "print(json.dumps({'argv': sys.argv[1:], 'helper': helper.VALUE, 'name': __name__}))\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    completed = _desktop(FROZEN_SCRIPT, str(script), "--input", "中文 參數.json")
    assert completed.returncode == 3, completed.stderr
    data = json.loads(completed.stdout)
    assert data == {
        "argv": ["--input", "中文 參數.json"],
        "helper": "from-helper",
        "name": "__main__",
    }


def test_module_runs_as_main_with_its_arguments() -> None:
    completed = _desktop(FROZEN_MODULE, "json.tool", "--help")
    assert completed.returncode == 0, completed.stderr
    assert "json.tool" in completed.stdout


def test_module_exit_codes_follow_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "rpa_exit_probe"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import sys\nraise SystemExit(sys.argv[1] if sys.argv[1] != 'int' else 7)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    assert run_module("rpa_exit_probe", ["int"]) == 7
    assert run_module("rpa_exit_probe", ["message"]) == 1


def test_script_without_exit_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "quiet.py"
    script.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert run_script(str(script), []) == 0


def test_version_prints_build_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["app"] == "development"
    assert data["protocol"] >= 1
    assert len(data["fingerprint"]) == 16


def test_bad_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([FROZEN_MODULE]) == 2
    assert main(["--unknown"]) == 2
    assert main(["--help"]) == 0
    assert FROZEN_SCRIPT in capsys.readouterr().err
