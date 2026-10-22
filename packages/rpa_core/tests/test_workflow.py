"""自由試驗場的序列（M6）：定義的格式、執行前的靜態檢查、執行時取值。"""

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from rpa_core.dsl import Scenario, validate_file
from rpa_core.dsl.dynamic import evaluate
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
    assert problems[0].message == "節點 n1：入參 recordId 沒有預設值，請指定固定值或上游節點的出參"


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


def test_fixed_values_can_be_dynamic() -> None:
    def node(title: object, quantity: object) -> Workflow:
        inputs = {"title": {"value": title}, "quantity": {"value": quantity}}
        return parsed(
            {"nodes": [{"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": inputs}]}
        )

    scenes = {"n1": load("ba-001")}
    assert check_workflow(node("試驗 {{today}}", "{{random:1:30}}"), scenes) == []
    problems = check_workflow(node("{{tody}}", "{{random:20:40}}"), scenes)
    assert [(p.code, p.input) for p in problems] == [
        ("workflow.value_dynamic", "title"),
    ]
    assert problems[0].message == (
        "節點 n1：入參 title 的固定值：看不懂動態值 {{tody}}；"
        "可以用 {{today}}、{{today+1}}、{{now}}、{{random:10:30}}"
    )
    # 固定值原樣交給執行，執行開始時才求值
    assert resolve_inputs(node("試驗 {{today}}", 3).nodes[0], {}) == (
        {"title": "試驗 {{today}}", "quantity": 3},
        [],
    )


def test_upstream_outputs_are_never_treated_as_dynamic_values() -> None:
    second = parsed(chain()).nodes[1]
    values, problems = resolve_inputs(second, {"n1": {"recordId": "{{today}} {{x"}})
    assert problems == []
    assert evaluate(values["recordId"]) == "{{today}} {{x"


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


# ---------------------------------------------------------------- DAG


def dag() -> dict[str, object]:
    """刻意把下游放在陣列前面，確認執行依賴不受畫布與儲存順序影響。"""
    return {
        "version": 2,
        "mode": "dag",
        "nodes": [
            {
                "id": "join",
                "sceneId": "ba-001",
                "revision": 1,
                "inputs": {
                    "title": {"node": "left", "output": "title"},
                    "quantity": {"node": "right", "output": "quantity"},
                },
            },
            {
                "id": "right",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"auto": True}},
            },
            {
                "id": "left",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"node": "root", "output": "recordId"}},
            },
            {"id": "root", "sceneId": "ba-001", "revision": 1, "position": {"x": 500, "y": 200}},
        ],
        "edges": [
            {"source": "root", "target": "right"},
            {"source": "root", "target": "left"},
            {"source": "left", "target": "join"},
            {"source": "right", "target": "join"},
        ],
    }


def test_dag_fork_join_order_and_auto_binding_snapshot() -> None:
    from rpa_core.workflow import plan_workflow

    workflow = parsed(dag())
    scenarios = {node.id: load(node.scene_id) for node in workflow.nodes}
    assert check_workflow(workflow, scenarios) == []
    planned, problems = plan_workflow(workflow, scenarios)
    assert problems == []
    assert [node.id for node in planned.execution_nodes()] == ["root", "right", "left", "join"]
    assert planned.nodes[1].inputs["recordId"] == OutputBinding(node="root", output="recordId")
    assert workflow.to_json() == parsed(workflow.to_json()).to_json()
    assert workflow.nodes[1].inputs["recordId"].model_dump() == {"auto": True}
    assert planned.nodes[3].position == workflow.nodes[3].position


@pytest.mark.parametrize(
    ("edge", "code"),
    [
        ({"source": "join", "target": "root"}, "workflow.cycle"),
        ({"source": "root", "target": "root"}, "workflow.cycle"),
        ({"source": "missing", "target": "root"}, "workflow.edge_unknown"),
        ({"source": "root", "target": "right"}, "workflow.edge_duplicate"),
    ],
)
def test_dag_rejects_invalid_graph(edge: dict[str, str], code: str) -> None:
    from rpa_core.workflow import WorkflowEdge

    workflow = parsed(dag())
    workflow.edges.append(WorkflowEdge.model_validate(edge))
    scenarios = {node.id: load(node.scene_id) for node in workflow.nodes}
    assert code in [problem.code for problem in check_workflow(workflow, scenarios)]


def test_bindings_alone_are_dependencies_and_can_form_a_cycle() -> None:
    workflow = parsed(
        {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {
                    "id": "a",
                    "sceneId": "ba-001",
                    "revision": 1,
                    "inputs": {"title": {"node": "b", "output": "title"}},
                },
                {
                    "id": "b",
                    "sceneId": "ba-001",
                    "revision": 1,
                    "inputs": {"title": {"node": "a", "output": "title"}},
                },
            ],
        }
    )
    assert codes(workflow, {"a": load("ba-001"), "b": load("ba-001")}) == [("workflow.cycle", None)]
    workflow.nodes[1].inputs.clear()
    assert [node.id for node in workflow.execution_nodes()] == ["b", "a"]
    assert check_workflow(workflow, {"a": load("ba-001"), "b": load("ba-001")}) == []


def test_auto_matching_requires_unique_direct_upstream_and_preserves_defaults() -> None:
    from rpa_core.workflow import AutoBinding, WorkflowEdge, plan_workflow

    workflow = parsed(dag())
    scenarios = {node.id: load(node.scene_id) for node in workflow.nodes}
    workflow.nodes[0].inputs["title"] = AutoBinding(auto=True)
    assert ("workflow.source_ambiguous", "title") in codes(workflow, scenarios)
    workflow.nodes[0].inputs["title"] = ValueBinding(value="明確固定值")
    assert check_workflow(workflow, scenarios) == []
    workflow.nodes[0].inputs["title"] = AutoBinding(auto=True)
    workflow.nodes[0].inputs.pop("quantity")
    workflow.edges[:] = [WorkflowEdge(source="root", target="right")]
    planned, problems = plan_workflow(workflow, scenarios)
    assert problems == []
    assert "title" not in planned.nodes[0].inputs  # 無直接同名上游，沿用場景預設
    assert "title" in workflow.nodes[0].inputs  # 不修改編輯中的定義


@pytest.mark.parametrize("x", [-1, float("nan"), float("inf"), 100001])
def test_canvas_coordinates_are_bounded(x: float) -> None:
    workflow, problems = parse_workflow(
        {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {"id": "n", "sceneId": "ba-001", "revision": 1, "position": {"x": x, "y": 0}}
            ],
        }
    )
    assert workflow is None
    assert problems


def test_auto_binding_to_unknown_input_is_not_silently_dropped() -> None:
    workflow = parsed(
        {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {"id": "n", "sceneId": "ba-001", "revision": 1, "inputs": {"typo": {"auto": True}}}
            ],
        }
    )
    assert codes(workflow, {"n": load("ba-001")}) == [("workflow.input_unknown", "typo")]


def test_auto_matching_uses_the_same_dependencies_as_output_bindings() -> None:
    from rpa_core.workflow import plan_workflow

    workflow = parsed(
        {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {"id": "a", "sceneId": "ba-001", "revision": 1},
                {
                    "id": "b",
                    "sceneId": "ba-001",
                    "revision": 1,
                    "inputs": {
                        "title": {"node": "a", "output": "title"},
                        "quantity": {"auto": True},
                    },
                },
            ],
        }
    )
    planned, problems = plan_workflow(workflow, {"a": load("ba-001"), "b": load("ba-001")})
    assert problems == []
    assert planned.nodes[1].inputs["quantity"] == OutputBinding(node="a", output="quantity")
