"""自我測試在開發環境也能跑：同一套邏輯，CI 再用打包後的 App 跑一次（M10.0）。"""

import json
from pathlib import Path

import pytest

from rpa_desktop.selftest import (
    PYTHON_NODES,
    SCENARIOS,
    main,
    python_node_root,
    python_nodes,
    scenario_root,
)
from testsite.browsers import require_engine


def test_scenarios_exist_in_the_repository() -> None:
    root = scenario_root()
    for relative in SCENARIOS:
        assert (root / relative).is_file(), relative
    for relative in PYTHON_NODES:
        assert (python_node_root() / relative).is_file(), relative


def test_python_nodes_run_where_the_runtime_is(tmp_path: Path) -> None:
    """RPA Worker 一定執行範例 Python 節點；錄製端不執行；開發環境有運行環境才執行。"""
    empty = {"RPA_CACHE_DIR": str(tmp_path / "cache"), "RPA_PYTHON_ARCHIVES": str(tmp_path)}
    assert python_nodes("worker", empty) == PYTHON_NODES
    assert python_nodes("recorder", empty) == ()
    assert python_nodes("development", empty) == ()
    with_runtime = {**empty, "RPA_PYTHON_RUNTIME": str(tmp_path / "runtime")}
    assert python_nodes("development", with_runtime) == PYTHON_NODES


@pytest.mark.browser
def test_self_test_runs_the_examples(tmp_path: Path) -> None:
    require_engine("chromium")
    report = tmp_path / "self-test.json"
    assert main(["--skip-install", "--report", str(report)]) == 0
    summary = json.loads(report.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["frozen"] is False
    assert [step["scenario"] for step in summary["steps"]] == ["ba-001", "ba-001-script"]
