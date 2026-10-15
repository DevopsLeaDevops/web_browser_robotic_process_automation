"""子程序的命令列：開發環境照舊是 python -m，打包後改走 App 自己的入口（M10，ADR 0014）。"""

import subprocess
import sys
from pathlib import Path

import pytest

from rpa_runner.commands import (
    FROZEN_MODULE,
    FROZEN_SCRIPT,
    is_frozen,
    module_command,
    playwright_command,
    script_command,
)


def test_development_commands_are_unchanged(tmp_path: Path) -> None:
    script = tmp_path / "automation.py"
    assert not is_frozen()
    assert module_command("rpa_runner.child", ["--out", "x"]) == [
        sys.executable,
        "-m",
        "rpa_runner.child",
        "--out",
        "x",
    ]
    assert script_command(script, ["--input", "i.json"]) == [
        sys.executable,
        str(script),
        "--input",
        "i.json",
    ]
    assert playwright_command(["codegen", "--target", "python"]) == [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--target",
        "python",
    ]


def test_frozen_commands_use_the_app_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/RPA Recorder.app/Contents/MacOS/rpa")
    script = tmp_path / "assertion.py"
    app = "/Applications/RPA Recorder.app/Contents/MacOS/rpa"
    assert is_frozen()
    assert module_command("rpa_runner.login", ["check"]) == [
        app,
        FROZEN_MODULE,
        "rpa_runner.login",
        "check",
    ]
    assert script_command(script) == [app, FROZEN_SCRIPT, str(script)]
    assert playwright_command(["install", "chromium"]) == [
        app,
        FROZEN_MODULE,
        "playwright",
        "install",
        "chromium",
    ]


def test_module_command_runs_a_real_module() -> None:
    completed = subprocess.run(
        module_command("rpa_runner.commands"), capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
