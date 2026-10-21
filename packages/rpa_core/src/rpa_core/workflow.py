"""組合場景的定義、DAG 依賴檢查與入參解析。

第 2 版以 edges 與出參綁定表達依賴，節點陣列和畫布座標不決定執行順序。
同時就緒的節點依定義順序逐個執行，失敗即停。第 1 版 serial 仍按原順序執行；
舊定義與歷史快照不改寫。此模組不依賴資料庫或瀏覽器。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Final, Literal, Self

from pydantic import Discriminator, Field, Tag, ValidationError, model_validator

from rpa_core.dsl.dynamic import DynamicValueError, escape
from rpa_core.dsl.fields import DslModel, Identifier, Slug, catalog, dsl_error
from rpa_core.dsl.issues import format_field
from rpa_core.dsl.scenario import Scenario

__all__ = [
    "MAX_NODES",
    "AutoBinding",
    "Binding",
    "InputSource",
    "NodePosition",
    "OutputBinding",
    "ValueBinding",
    "Workflow",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowProblem",
    "check_workflow",
    "compatible",
    "input_sources",
    "parse_workflow",
    "plan_workflow",
    "resolve_inputs",
    "sequence",
]

MAX_NODES: Final = 50
"""一個組合場景最多幾個節點。"""


class AutoBinding(DslModel):
    """從直接上游尋找唯一的同名相容出參；沒有命中時使用場景預設。"""

    auto: Literal[True]


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
    if isinstance(value, AutoBinding) or (isinstance(value, dict) and "auto" in value):
        return "auto"
    if isinstance(value, ValueBinding) or (isinstance(value, dict) and "value" in value):
        return "value"
    return "output"


Binding = Annotated[
    Annotated[ValueBinding, Tag("value")]
    | Annotated[OutputBinding, Tag("output")]
    | Annotated[AutoBinding, Tag("auto")],
    Discriminator(_binding_kind),
]
"""入參的來源：固定值或前面節點的出參；沒寫就用場景的預設值。"""


class NodePosition(DslModel):
    """畫布座標，僅影響顯示，不影響依賴關係。"""

    x: Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)]


class WorkflowEdge(DslModel):
    """來源通過後，目標才可開始。資料綁定也會形成相同的依賴。"""

    source: Slug
    target: Slug


class WorkflowNode(DslModel):
    """組合場景的一個節點：某個場景的固定版本，加上入參的來源。"""

    position: NodePosition | None = None
    id: Slug
    """節點代號，組合場景裡不能重複；綁定時用它指定上游，例如 n1。"""
    scene_id: Slug
    revision: Annotated[int, Field(ge=1)]
    """固定的版本號碼；只能是發布過的版本。"""
    inputs: dict[Identifier, Binding] = Field(
        default_factory=dict[str, ValueBinding | OutputBinding | AutoBinding]
    )


class Workflow(DslModel):
    """組合場景定義：第 1 版線性序列與第 2 版 DAG。"""

    version: Literal[1, 2] = 1
    mode: Literal["serial", "dag"] = "serial"
    edges: Annotated[list[WorkflowEdge], Field(max_length=2500)] = Field(
        default_factory=list[WorkflowEdge]
    )
    """依賴邊；執行順序由拓撲排序決定。"""
    on_failure: Literal["stop"] = "stop"
    """節點沒有通過時：停止，後面的節點不執行。"""
    nodes: Annotated[list[WorkflowNode], Field(max_length=MAX_NODES)] = Field(
        default_factory=list[WorkflowNode]
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        if (self.version == 1) != (self.mode == "serial") or (self.mode == "serial" and self.edges):
            raise dsl_error("workflow.mode_version")
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

    def dependencies(self) -> dict[str, set[str]]:
        """節點 → 必須先通過的節點；資料綁定不能繞過依賴。"""
        dependencies = {node.id: set[str]() for node in self.nodes}
        if self.mode == "serial":
            for previous, node in zip(self.nodes, self.nodes[1:], strict=False):
                dependencies[node.id].add(previous.id)
        else:
            for edge in self.edges:
                if edge.target in dependencies:
                    dependencies[edge.target].add(edge.source)
            for node in self.nodes:
                for binding in node.inputs.values():
                    if isinstance(binding, OutputBinding):
                        dependencies[node.id].add(binding.node)
        return dependencies

    def execution_nodes(self) -> list[WorkflowNode]:
        """穩定的拓撲排序；有環或缺少來源時回傳可排序的部分，由檢查阻擋執行。"""
        dependencies = self.dependencies()
        ordered: list[WorkflowNode] = []
        done: set[str] = set()
        while len(done) < len(self.nodes):
            ready = next(
                (
                    node
                    for node in self.nodes
                    if node.id not in done and dependencies[node.id] <= done
                ),
                None,
            )
            if ready is None:
                break
            ordered.append(ready)
            done.add(ready.id)
        return ordered

    def to_json(self) -> dict[str, object]:
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        if self.mode == "serial":
            data.pop("edges")
        return data


@dataclass(frozen=True, slots=True)
class WorkflowProblem:
    """組合場景的一個問題；message 是目前語言的說明。"""

    code: str
    message: str
    node: str | None = None
    input: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "node": self.node, "input": self.input}


@dataclass(frozen=True, slots=True)
class InputSource:
    """一個入參的值從哪裡來：場景的預設值、固定值，或前面節點的出參（頁面顯示用）。"""

    kind: Literal["default", "value", "output", "missing", "auto"]
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


_TAGS: Final = frozenset({"value", "output", "auto"})
"""綁定寫法在錯誤路徑裡的標籤；顯示路徑時略過（它們剛好也是欄位名稱，只略過標籤那一層）。"""


def compatible(output_type: str, input_type: str) -> bool:
    """上游出參的型別能不能直接當成下游入參：相同型別，或整數給數字。"""
    return output_type == input_type or (output_type == "integer" and input_type == "number")


def plan_workflow(
    workflow: Workflow, scenarios: Mapping[str, Scenario | None]
) -> tuple[Workflow, list[WorkflowProblem]]:
    """固定同名匹配的結果；執行快照不保留會隨編輯而變動的解析規則。"""
    planned = workflow.model_copy(deep=True)
    problems: list[WorkflowProblem] = []
    for node in planned.nodes:
        scenario = scenarios.get(node.id)
        for name, binding in list(node.inputs.items()):
            if not isinstance(binding, AutoBinding):
                continue
            if workflow.mode != "dag":
                problems.append(_problem("workflow.auto_requires_dag", node.id, name))
            if scenario is not None and name not in scenario.inputs:
                problems.append(_problem("workflow.input_unknown", node.id, name))
            spec = scenario.inputs.get(name) if scenario else None
            candidates: set[str] = set()
            for source_id in workflow.dependencies()[node.id]:
                source = scenarios.get(source_id)
                output = source.outputs.get(name) if source else None
                if spec and output and compatible(output.type, spec.type):
                    candidates.add(source_id)
            if len(candidates) > 1:
                problems.append(_problem("workflow.source_ambiguous", node.id, name))
            if len(candidates) == 1:
                node.inputs[name] = OutputBinding(node=next(iter(candidates)), output=name)
            else:
                del node.inputs[name]
    return planned, problems


def check_workflow(
    workflow: Workflow, scenarios: Mapping[str, Scenario | None]
) -> list[WorkflowProblem]:
    """執行前的靜態檢查；scenarios 是「節點代號 → 固定版本的場景」。

    載入不了的場景是 None，不檢查它的契約；場景不存在、封存、版本沒有發布過等
    資料庫裡的狀態由呼叫端另外檢查。
    """
    workflow, problems = plan_workflow(workflow, scenarios)
    if not workflow.nodes:
        problems.append(_problem("workflow.empty"))
    if workflow.mode == "dag":
        ids = {node.id for node in workflow.nodes}
        seen: set[tuple[str, str]] = set()
        for edge in workflow.edges:
            if edge.source not in ids or edge.target not in ids:
                problems.append(
                    _problem("workflow.edge_unknown", source=edge.source, target=edge.target)
                )
            if (edge.source, edge.target) in seen:
                problems.append(
                    _problem("workflow.edge_duplicate", source=edge.source, target=edge.target)
                )
            seen.add((edge.source, edge.target))
        # 缺少端點另行回報；只有完整圖才判斷環。
        deps = workflow.dependencies()
        if all(sources <= ids for sources in deps.values()) and len(
            workflow.execution_nodes()
        ) != len(workflow.nodes):
            problems.append(_problem("workflow.cycle"))
    positions = {node.id: index for index, node in enumerate(workflow.nodes)}
    for index, node in enumerate(workflow.nodes):
        scenario = scenarios.get(node.id)
        if scenario is not None:
            problems += _check_node(
                node, index, scenario, scenarios, positions, workflow.mode == "serial"
            )
    return problems


def _check_node(
    node: WorkflowNode,
    index: int,
    scenario: Scenario,
    scenarios: Mapping[str, Scenario | None],
    positions: Mapping[str, int],
    serial: bool,
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
            # 固定值可以是動態值（例如 {{today}}），執行時才求值；這裡檢查寫法與代表值
            try:
                rules = spec.check_value(binding.value)
            except DynamicValueError as error:
                problems.append(
                    _problem("workflow.value_dynamic", node.id, name, detail=error.message)
                )
                continue
            for rule in rules[:1]:
                problems.append(_problem("workflow.value_invalid", node.id, name, rule=rule))
        elif isinstance(binding, OutputBinding):
            source = binding.node
            if source not in positions:
                problems.append(_problem("workflow.source_unknown", node.id, name, source=source))
                continue
            if serial and positions[source] >= index:
                problems.append(_problem("workflow.source_order", node.id, name, source=source))
                continue
            upstream = scenarios.get(source)
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
        if isinstance(binding, AutoBinding):
            sources[name] = InputSource("auto")
        elif isinstance(binding, ValueBinding):
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

    固定值與預設值裡的動態值（例如 ``{{today}}``）在執行開始時求值；上游的出參先跳脫，原樣使用。

    outputs 是「節點代號 → 通過之後發布的出參」；上游沒有通過（None）或沒有那個出參時回報問題。
    """
    values: dict[str, object] = {}
    problems: list[WorkflowProblem] = []
    for name, binding in node.inputs.items():
        if isinstance(binding, AutoBinding):
            problems.append(_problem("workflow.auto_unresolved", node.id, name))
            continue
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
            # 上游的出參是資料：文字裡剛好有 {{ 時也照原樣，不當成動態值
            values[name] = escape(published[binding.output])
    return values, problems


def sequence(nodes: Sequence[WorkflowNode]) -> str:
    """節點的場景代號串成一行，例如 ``ba-001 → ba-002``（清單與標題用）。"""
    return " → ".join(node.scene_id for node in nodes)
