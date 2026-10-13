"""自由試驗場的序列（編排，M6）：已發布場景的固定版本排成序列，上游的出參綁定到下游的入參。

定義是一份 JSON（第 1 版），管理 Portal 存在資料庫，也可以匯出、匯入::

    {
      "version": 1, "mode": "serial", "onFailure": "stop",
      "nodes": [
        {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "試驗"}}},
        {"id": "n2", "sceneId": "ba-002", "revision": 1,
         "inputs": {"recordId": {"node": "n1", "output": "recordId"}}}
      ]
    }

- **依序、失敗即停。**一個節點通過才執行下一個；失敗、逾時、取消或需要登入就停止，後面的節點不執行。
- **固定版本。**每個節點寫明場景的版本號碼，之後發布新版本也不影響這個序列，直到使用者改版本。
- **入參的來源。**沒寫的入參用場景的預設值；``{"value": …}`` 是固定值；
  ``{"node": 節點, "output": 出參}`` 是前面某個節點**通過之後發布**的出參。
- **先檢查、再執行。**:func:`check_workflow` 在執行前找出不能執行的地方（取自後面的節點、
  出參不存在、型別不相容、必填入參沒有來源、固定值不符合規則）；綁定的值要等上游通過才知道，
  那時由 :func:`resolve_inputs` 取值，再依入參規則校驗（rpa_runner.contract.check_inputs）。

這裡只有資料與規則，不碰資料庫與瀏覽器；序列的執行由管理 Portal 負責（rpa_server.workflows）。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Final, Literal, Self

from pydantic import Discriminator, Field, Tag, ValidationError, model_validator

from rpa_core.dsl.fields import DslModel, Identifier, Slug, catalog, dsl_error
from rpa_core.dsl.issues import format_field
from rpa_core.dsl.scenario import Scenario

__all__ = [
    "MAX_NODES",
    "Binding",
    "InputSource",
    "OutputBinding",
    "ValueBinding",
    "Workflow",
    "WorkflowNode",
    "WorkflowProblem",
    "check_workflow",
    "compatible",
    "input_sources",
    "parse_workflow",
    "resolve_inputs",
    "sequence",
]

MAX_NODES: Final = 50
"""一個序列最多幾個節點。"""


class ValueBinding(DslModel):
    """固定值：執行時直接當成入參。"""

    value: object

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.value is None:
            raise dsl_error("workflow.value_null", at=["value"])
        return self


class OutputBinding(DslModel):
    """前面某個節點的出參：上游通過之後才有值。"""

    node: Slug
    output: Identifier


def _binding_kind(value: object) -> str:
    if isinstance(value, ValueBinding) or (isinstance(value, dict) and "value" in value):
        return "value"
    return "output"


Binding = Annotated[
    Annotated[ValueBinding, Tag("value")] | Annotated[OutputBinding, Tag("output")],
    Discriminator(_binding_kind),
]
"""入參的來源：固定值或前面節點的出參；沒寫就用場景的預設值。"""


class WorkflowNode(DslModel):
    """序列的一個節點：某個場景的固定版本，加上入參的來源。"""

    id: Slug
    """節點代號，序列裡不能重複；綁定時用它指定上游，例如 n1。"""
    scene_id: Slug
    revision: Annotated[int, Field(ge=1)]
    """固定的版本號碼；只能是發布過的版本。"""
    inputs: dict[Identifier, Binding] = Field(
        default_factory=dict[str, ValueBinding | OutputBinding]
    )


class Workflow(DslModel):
    """一個序列的定義（第 1 版）。"""

    version: Literal[1] = 1
    mode: Literal["serial"] = "serial"
    """執行方式：依序（MVP 只有這一種）。"""
    on_failure: Literal["stop"] = "stop"
    """節點沒有通過時：停止，後面的節點不執行。"""
    nodes: Annotated[list[WorkflowNode], Field(max_length=MAX_NODES)] = Field(
        default_factory=list[WorkflowNode]
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        seen: set[str] = set()
        for index, node in enumerate(self.nodes):
            if node.id in seen:
                raise dsl_error("workflow.node_duplicate", at=["nodes", index, "id"], node=node.id)
            seen.add(node.id)
        return self

    def node(self, node_id: str) -> WorkflowNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def index(self, node_id: str) -> int:
        """節點的位置（從 0 開始）；沒有這個節點時是 -1。"""
        return next((i for i, node in enumerate(self.nodes) if node.id == node_id), -1)

    def to_json(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


@dataclass(frozen=True, slots=True)
class WorkflowProblem:
    """序列的一個問題；message 是目前語言的說明。"""

    code: str
    message: str
    node: str | None = None
    input: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "node": self.node, "input": self.input}


@dataclass(frozen=True, slots=True)
class InputSource:
    """一個入參的值從哪裡來：場景的預設值、固定值，或前面節點的出參（頁面顯示用）。"""

    kind: Literal["default", "value", "output", "missing"]
    node: str | None = None
    output: str | None = None
    value: object = None

    def to_json(self) -> dict[str, object]:
        return {"kind": self.kind, "node": self.node, "output": self.output, "value": self.value}


def _problem(
    code: str, node: str | None = None, input_name: str | None = None, **params: object
) -> WorkflowProblem:
    message = catalog(f"dsl.{code}", node=node, input=input_name, **params)
    return WorkflowProblem(code, message, node, input_name)


def parse_workflow(data: object) -> tuple[Workflow | None, list[WorkflowProblem]]:
    """JSON 資料 → 序列；格式不對時回傳 (None, 問題)。"""
    try:
        return Workflow.model_validate(data), []
    except ValidationError as error:
        problems: list[WorkflowProblem] = []
        for details in error.errors():
            context: dict[str, object] = dict(details.get("ctx") or {})
            at = context.pop("at", ())
            location = [
                part for part in details["loc"] if not (isinstance(part, str) and part in _TAGS)
            ]
            if isinstance(at, tuple | list):
                location += [part for part in at if isinstance(part, str | int)]  # pyright: ignore[reportUnknownVariableType]
            error_type = details["type"]
            if "." in error_type:
                message = catalog(f"dsl.{error_type}", **context)
            elif error_type == "missing":
                message = catalog("dsl.missing", field=location[-1] if location else "")
            else:
                message = catalog("dsl.generic", detail=details["msg"])
            field = format_field(location)
            text = catalog("dsl.issue.field", field=field, message=message) if field else message
            problems.append(WorkflowProblem("workflow.invalid", text))
        return None, list(dict.fromkeys(problems))


_TAGS: Final = frozenset({"value", "output"})
"""綁定的兩種寫法在錯誤路徑裡的標籤；顯示路徑時略過（它們剛好也是欄位名稱，只略過標籤那一層）。"""


def compatible(output_type: str, input_type: str) -> bool:
    """上游出參的型別能不能直接當成下游入參：相同型別，或整數給數字。"""
    return output_type == input_type or (output_type == "integer" and input_type == "number")


def check_workflow(
    workflow: Workflow, scenarios: Mapping[str, Scenario | None]
) -> list[WorkflowProblem]:
    """執行前的靜態檢查；scenarios 是「節點代號 → 固定版本的場景」。

    載入不了的場景是 None，不檢查它的契約；場景不存在、封存、版本沒有發布過等
    資料庫裡的狀態由呼叫端另外檢查。
    """
    problems: list[WorkflowProblem] = []
    if not workflow.nodes:
        problems.append(_problem("workflow.empty"))
    earlier: dict[str, Scenario | None] = {}
    positions = {node.id: index for index, node in enumerate(workflow.nodes)}
    for index, node in enumerate(workflow.nodes):
        scenario = scenarios.get(node.id)
        if scenario is not None:
            problems += _check_node(node, index, scenario, earlier, positions)
        earlier[node.id] = scenario
    return problems


def _check_node(
    node: WorkflowNode,
    index: int,
    scenario: Scenario,
    earlier: Mapping[str, Scenario | None],
    positions: Mapping[str, int],
) -> list[WorkflowProblem]:
    problems: list[WorkflowProblem] = []
    for name in node.inputs:
        if name not in scenario.inputs:
            problems.append(_problem("workflow.input_unknown", node.id, name))
    for name, spec in scenario.inputs.items():
        binding = node.inputs.get(name)
        if binding is None:
            if spec.default is None:
                problems.append(_problem("workflow.input_missing", node.id, name))
        elif isinstance(binding, ValueBinding):
            for rule in spec.violations(binding.value):
                problems.append(_problem("workflow.value_invalid", node.id, name, rule=rule))
                break
        else:
            source = binding.node
            if source not in positions:
                problems.append(_problem("workflow.source_unknown", node.id, name, source=source))
                continue
            if positions[source] >= index:
                problems.append(_problem("workflow.source_order", node.id, name, source=source))
                continue
            upstream = earlier.get(source)
            if upstream is None:
                continue
            output = upstream.outputs.get(binding.output)
            if output is None:
                problems.append(
                    _problem(
                        "workflow.output_unknown",
                        node.id,
                        name,
                        source=source,
                        output=binding.output,
                    )
                )
            elif not compatible(output.type, spec.type):
                problems.append(
                    _problem(
                        "workflow.type_mismatch",
                        node.id,
                        name,
                        source=source,
                        output=binding.output,
                        input_type=spec.type,
                        output_type=output.type,
                    )
                )
    return problems


def input_sources(node: WorkflowNode, scenario: Scenario) -> dict[str, InputSource]:
    """場景每個入參的來源，依場景檔的順序；頁面顯示「recordId ← n1.recordId」用。"""
    sources: dict[str, InputSource] = {}
    for name, spec in scenario.inputs.items():
        binding = node.inputs.get(name)
        if isinstance(binding, ValueBinding):
            sources[name] = InputSource("value", value=binding.value)
        elif isinstance(binding, OutputBinding):
            sources[name] = InputSource("output", node=binding.node, output=binding.output)
        elif spec.default is not None:
            sources[name] = InputSource("default", value=spec.default)
        else:
            sources[name] = InputSource("missing")
    return sources


def resolve_inputs(
    node: WorkflowNode, outputs: Mapping[str, Mapping[str, object] | None]
) -> tuple[dict[str, object], list[WorkflowProblem]]:
    """執行到這個節點時的入參：固定值與上游節點的出參（預設值由執行時補上）。

    outputs 是「節點代號 → 通過之後發布的出參」；上游沒有通過（None）或沒有那個出參時回報問題。
    """
    values: dict[str, object] = {}
    problems: list[WorkflowProblem] = []
    for name, binding in node.inputs.items():
        if isinstance(binding, ValueBinding):
            values[name] = binding.value
            continue
        published = outputs.get(binding.node)
        if published is None:
            problems.append(
                _problem("workflow.source_not_passed", node.id, name, source=binding.node)
            )
        elif binding.output not in published:
            problems.append(
                _problem(
                    "workflow.output_missing",
                    node.id,
                    name,
                    source=binding.node,
                    output=binding.output,
                )
            )
        else:
            values[name] = published[binding.output]
    return values, problems


def sequence(nodes: Sequence[WorkflowNode]) -> str:
    """節點的場景代號串成一行，例如 ``ba-001 → ba-002``（清單與標題用）。"""
    return " → ".join(node.scene_id for node in nodes)
