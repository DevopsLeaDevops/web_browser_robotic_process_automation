"""範例場景與提交的 JSON Schema。

- examples/ 下的每個場景都要通過校驗，文檔與範例才不會跟實作脫節。
- schema/scenario.v1.json 由 `rpa schema` 產生並提交，給編輯器自動補全；模型改了要重新產生。
"""

import json
from pathlib import Path

import pytest

from rpa_core.dsl import format_issue, scenario_json_schema, validate_file

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "examples").glob("*.yaml"))
SCHEMA_FILE = ROOT / "schema" / "scenario.v1.json"


def test_examples_exist() -> None:
    assert EXAMPLES, "examples/ 底下沒有範例場景"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_is_valid(path: Path) -> None:
    result = validate_file(path)
    problems = [f"{i.position}: {format_issue(i)}" for i in result.issues]
    assert result.ok, "\n".join(problems)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_points_to_schema(path: Path) -> None:
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "# yaml-language-server: $schema=../schema/scenario.v1.json"


def test_schema_file_is_up_to_date() -> None:
    committed = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert committed == scenario_json_schema(), (
        "schema/scenario.v1.json 過期了，請執行：uv run rpa schema > schema/scenario.v1.json"
    )
