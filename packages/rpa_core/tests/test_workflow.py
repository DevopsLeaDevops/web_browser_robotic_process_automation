"""自由試驗場的序列（M6）：定義的格式、執行前的靜態檢查、執行時取值。"""

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from rpa_core.dsl import Scenario, validate_file
from rpa_core.i18n import use_locale
from rpa_core.workflow import (
    InputSource,
    OutputBinding,
    ValueBinding,
    Workflow,
    check_workflow,
    compatible,
    input_sources,
    parse_workflow,
    resolve_inputs,
    sequence,
)

DEMO = Path(__file__).resolve().parents[3] / "scenarios" / "demo"


def load(name: str) -> Scenario:
    scenario = validate_file(DEMO / f"{name}.yaml").scenario
    assert scenario is not None
    return scenario


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def chain(**second: object) -> dict[str, object]:
    """BA-001 → BA-002：BA-002 的 recordId 取自 BA-001 的出參。"""
    inputs = second or {"recordId": {"node": "n1", "output": "recordId"}}
    return {
        "nodes": [
            {
                "id": "n1",
                "sceneId": "ba-001",
                "revision": 1,
                "inputs": {"title": {"value": "試驗"}},
            },
            {"id": "n2", "sceneId": "ba-002", "revision": 1, "inputs": inputs},
        ]
    }


def parsed(data: object) -> Workflow:
    workflow, problems = parse_workflow(data)
    assert problems == []
    assert workflow is not None
    return workflow


def codes(
    workflow: Workflow, scenarios: Mapping[str, Scenario | None]
) -> list[tuple[str, str | None]]:
    return [(problem.code, problem.input) for problem in check_workflow(workflow, scenarios)]


SCENES = {"n1": load("ba-001"), "n2": load("ba-002")}


# ---------------------------------------------------------------- 格式


def test_definition_round_trip_with_defaults() -> None:
    workflow = parsed(chain())
    assert workflow.to_json() == {"version": 1, "mode": "serial", "onFailure": "stop", **chain()}
    first, second = workflow.nodes
    assert isinstance(first.inputs["title"], ValueBinding)
    assert second.inputs["recordId"] == OutputBinding(node="n1", output="recordId")
    assert workflow.index("n2") == 1
    assert workflow.index("n9") == -1
    assert workflow.node("n1") is first
    assert sequence(workflow.nodes) == "ba-001 → ba-002"
    assert parsed({}).nodes == []


def test_format_problems_point_to_the_field() -> None:
    workflow, problems = parse_workflow(
        {
            "nodes": [
                {"id": "n1", "sceneId": "ba-001", "revision": 0},
                {"id": "N2", "sceneId": "ba-002", "revision": 1, "inputs": {"x": {"value": None}}},
            ]
        }
    )
    assert workflow is None
    messages = [problem.message for problem in problems]
    assert any(message.startswith("nodes[0].revision") for message in messages)
    assert any(message.startswith("nodes[1].id：N2 格式不符") for message in messages)
    assert "nodes[1].inputs.x.value：固定值不能是 null" in messages[-1]
    assert {problem.code for problem in problems} == {"workflow.invalid"}


def test_duplicate_node_ids_and_unknown_fields() -> None:
    node = {"id": "n1", "sceneId": "ba-001", "revision": 1}
    _, problems = parse_workflow({"nodes": [node, node]})
    assert [problem.message for problem in problems] == ["nodes[1].id：節點代號 n1 重複"]
    _, problems = parse_workflow({"nodes": [{**node, "inputs": {"t": {"node": "n0"}}}]})
    assert problems  # 出參名稱沒寫
    _, problems = parse_workflow({"version": 2})
    assert problems


# ---------------------------------------------------------------- 靜態檢查


def test_upstream_output_feeds_downstream_input() -> None:
    assert codes(parsed(chain()), SCENES) == []


def test_required_input_without_source() -> None:
    workflow = parsed({"nodes": [{"id": "n1", "sceneId": "ba-002", "revision": 1}]})
    problems = check_workflow(workflow, {"n1": load("ba-002")})
    assert [(p.code, p.node, p.input) for p in problems] == [
        ("workflow.input_missing", "n1", "recordId")
    ]
    assert problems[0].message == "節點 n1：入參 recordId 沒有預設值，請指定固定值或前面節點的出參"


def test_sources_must_be_earlier_nodes() -> None:
    later = parsed(
        {
            "nodes": [
                {
                    "id": "n1",
                    "sceneId": "ba-002",
                    "revision": 1,
                    "inputs": {"recordId": {"node": "n2", "output": "recordId"}},
                },
                {"id": "n2", "sceneId": "ba-001", "revision": 1},
            ]
        }
    )
    assert codes(later, {"n1": load("ba-002"), "n2": load("ba-001")}) == [
        ("workflow.source_order", "recordId")
    ]
    itself = parsed(chain(recordId={"node": "n2", "output": "recordId"}))
    assert codes(itself, SCENES) == [("workflow.source_order", "recordId")]
    missing = parsed(chain(recordId={"node": "n7", "output": "recordId"}))
    assert codes(missing, SCENES) == [("workflow.source_unknown", "recordId")]


def test_output_must_exist_and_types_must_match() -> None:
    unknown = parsed(chain(recordId={"node": "n1", "output": "nope"}))
    assert codes(unknown, SCENES) == [("workflow.output_unknown", "recordId")]
    mismatch = parsed(chain(recordId={"node": "n1", "output": "quantity"}))
    problems = check_workflow(mismatch, SCENES)
    assert [p.code for p in problems] == ["workflow.type_mismatch"]
    assert "（string）" in problems[0].message
    assert "（integer）" in problems[0].message
    assert compatible("integer", "number")
    assert not compatible("number", "integer")
    assert not compatible("object", "string")


def test_fixed_values_follow_the_input_rules() -> None:
    workflow = parsed(
        {
            "nodes": [
                {
                    "id": "n1",
                    "sceneId": "ba-001",
                    "revision": 1,
                    "inputs": {
                        "title": {"value": 5},
                        "quantity": {"value": 99},
                        "extra": {"value": 1},
                    },
                }
            ]
        }
    )
    problems = check_workflow(workflow, {"n1": load("ba-001")})
    assert [(p.code, p.input) for p in problems] == [
        ("workflow.input_unknown", "extra"),
        ("workflow.value_invalid", "title"),
        ("workflow.value_invalid", "quantity"),
    ]
    assert problems[2].message == "節點 n1：入參 quantity 的固定值不符合 maximum: 30"


def test_unloadable_scenarios_are_left_to_the_caller() -> None:
    assert codes(parsed(chain()), {"n1": None, "n2": load("ba-002")}) == []
    assert codes(parsed({}), {}) == [("workflow.empty", None)]


def test_messages_follow_the_language() -> None:
    workflow = parsed({"nodes": [{"id": "n1", "sceneId": "ba-002", "revision": 1}]})
    with use_locale("en"):
        problems = check_workflow(workflow, {"n1": load("ba-002")})
    assert problems[0].message == (
        "Node n1: input recordId has no default; give it a fixed value or an output of an "
        "earlier node"
    )


# ---------------------------------------------------------------- 執行時


def test_input_sources_for_display() -> None:
    workflow = parsed(chain())
    assert input_sources(workflow.nodes[0], SCENES["n1"]) == {
        "title": InputSource("value", value="試驗"),
        "quantity": InputSource("default", value=12),
    }
    assert input_sources(workflow.nodes[1], SCENES["n2"]) == {
        "recordId": InputSource("output", node="n1", output="recordId")
    }
    alone = parsed({"nodes": [{"id": "n1", "sceneId": "ba-002", "revision": 1}]})
    assert input_sources(alone.nodes[0], SCENES["n2"])["recordId"].to_json() == {
        "kind": "missing",
        "node": None,
        "output": None,
        "value": None,
    }


def test_resolve_takes_published_outputs_only() -> None:
    first, second = parsed(chain()).nodes
    assert resolve_inputs(first, {}) == ({"title": "試驗"}, [])
    values, problems = resolve_inputs(second, {"n1": {"recordId": "DEMO-ABC", "title": "試驗"}})
    assert (values, problems) == ({"recordId": "DEMO-ABC"}, [])

    _, problems = resolve_inputs(second, {"n1": None})
    assert [p.code for p in problems] == ["workflow.source_not_passed"]
    _, problems = resolve_inputs(second, {"n1": {"title": "試驗"}})
    assert [p.message for p in problems] == ["節點 n2：n1 通過了，但沒有發布出參 recordId"]
