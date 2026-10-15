"""自我測試在開發環境也能跑：同一套邏輯，CI 再用打包後的 App 跑一次（M10.0）。"""

import json
from pathlib import Path

import pytest

from rpa_desktop.selftest import SCENARIOS, main, scenario_root
from testsite.browsers import require_engine


def test_scenarios_exist_in_the_repository() -> None:
    root = scenario_root()
    for relative in SCENARIOS:
        assert (root / relative).is_file(), relative


@pytest.mark.browser
def test_self_test_runs_the_examples(tmp_path: Path) -> None:
    require_engine("chromium")
    report = tmp_path / "self-test.json"
    assert main(["--skip-install", "--report", str(report)]) == 0
    summary = json.loads(report.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["frozen"] is False
    assert [step["scenario"] for step in summary["steps"]] == ["ba-001", "ba-001-script"]
