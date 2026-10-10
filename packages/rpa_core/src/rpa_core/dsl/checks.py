"""跨欄位、跨步驟的檢查：只在場景的結構都正確之後執行。

- 場景主體：steps 與 script 二擇一；Python 腳本場景不寫 verify 與 outputs 的 from
- 出參：DSL 場景的每個出參都要有 from，有出參就要有 verify（獨立斷言通過才發布）
- 步驟 id、secrets 名稱、extract 的 as 不能重複
- goto 的網址以 / 開頭時，要有 browser.baseUrl
- ``{{ }}``：以 Jinja2 解析，語法要正確；只能用 inputs、secrets、facts、env；
  inputs、secrets 要宣告，facts 要由「之前」的 extract 產生

``{{ }}`` 的求值在 M2 的執行引擎；這裡只做不需要執行就能發現的檢查。
"""

from collections.abc import Iterator, Set
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast

from jinja2 import TemplateError, nodes
from jinja2.meta import find_undeclared_variables
from jinja2.sandbox import SandboxedEnvironment

from rpa_core.dsl.yaml_loader import DataPath

if TYPE_CHECKING:
    from rpa_core.dsl.scenario import Scenario

__all__ = ["RENAMED", "VARIABLES", "CrossIssue", "cross_check"]

VARIABLES: Final = ("inputs", "secrets", "facts", "env")
"""``{{ }}`` 可以使用的變數。"""

RENAMED: Final = {"params": "inputs"}
"""改過名的欄位與變數：舊名 → 新名，用來提示正確寫法。"""

_JINJA: Final = SandboxedEnvironment()


@dataclass(frozen=True, slots=True)
class CrossIssue:
    """一個跨欄位的問題；code 對應訊息目錄的 ``dsl.<code>``。"""

    path: DataPath
    code: str
    params: dict[str, object] = field(default_factory=dict[str, object])


def cross_check(scenario: "Scenario") -> list[CrossIssue]:
    """回傳場景中所有跨欄位的問題。"""
    issues: list[CrossIssue] = []
    issues.extend(_body(scenario))
    issues.extend(_duplicate_names(scenario))
    issues.extend(_relative_urls(scenario))
    issues.extend(_templates(scenario))
    return issues


# ---------------------------------------------------------------- 場景主體與契約


def _body(scenario: "Scenario") -> Iterator[CrossIssue]:
    if scenario.steps is None and scenario.script is None:
        yield CrossIssue((), "one_of.none", {"fields": "steps, script"})
        return
    if scenario.steps is not None and scenario.script is not None:
        yield CrossIssue(("script",), "one_of.many", {"fields": "steps, script"})
        return
    if scenario.script is not None:
        if scenario.verify is not None:
            yield CrossIssue(("verify",), "script.verify_not_allowed")
        for name, spec in scenario.outputs.items():
            if spec.from_ is not None:
                yield CrossIssue(("outputs", name, "from"), "script.output_from_not_allowed")
        return
    for name, spec in scenario.outputs.items():
        if spec.from_ is None:
            yield CrossIssue(("outputs", name), "output.from_required", {"name": name})
    if scenario.outputs and scenario.verify is None:
        yield CrossIssue(("outputs",), "verify.required_for_outputs")


def _duplicate_names(scenario: "Scenario") -> Iterator[CrossIssue]:
    seen_secrets: dict[str, int] = {}
    for index, name in enumerate(scenario.secrets):
        if name in seen_secrets:
            yield CrossIssue(("secrets", index), "secret.duplicate", {"name": name})
        else:
            seen_secrets[name] = index
    seen_steps: dict[str, int] = {}
    seen_facts: dict[str, int] = {}
    for index, step in enumerate(scenario.steps or ()):
        if step.id in seen_steps:
            first = seen_steps[step.id] + 1
            yield CrossIssue(
                ("steps", index, "id"), "step.duplicate_id", {"id": step.id, "first": first}
            )
        else:
            seen_steps[step.id] = index
        if step.action == "extract":
            if step.as_ in seen_facts:
                first = seen_facts[step.as_] + 1
                yield CrossIssue(
                    ("steps", index, "as"),
                    "extract.duplicate_as",
                    {"name": step.as_, "first": first},
                )
            else:
                seen_facts[step.as_] = index


def _relative_urls(scenario: "Scenario") -> Iterator[CrossIssue]:
    if scenario.browser.base_url is not None:
        return
    for index, step in enumerate(scenario.steps or ()):
        if step.action == "goto" and step.url.startswith("/"):
            yield CrossIssue(
                ("steps", index, "url"), "url.relative_without_base", {"value": step.url}
            )


# ---------------------------------------------------------------- {{ }}


@dataclass(frozen=True, slots=True)
class _Scope:
    inputs: Set[str]
    secrets: Set[str]
    facts_before: Set[str] | None
    """這個位置之前已產生的 facts；None 代表這裡不能用 facts。"""
    all_facts: Set[str]


def _templates(scenario: "Scenario") -> Iterator[CrossIssue]:
    data = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    inputs, secrets = set(scenario.inputs), set(scenario.secrets)
    all_facts = {step.as_ for step in scenario.steps or () if step.action == "extract"}

    def scope(facts_before: Set[str] | None) -> _Scope:
        return _Scope(inputs, secrets, facts_before, all_facts)

    browser = cast("dict[str, object]", data.get("browser", {}))
    for path, text in _strings(browser, ("browser",)):
        yield from _check_template(path, text, scope(None))
    produced: set[str] = set()
    for index, (step, raw) in enumerate(
        zip(scenario.steps or (), _list(data, "steps"), strict=True)
    ):
        for path, text in _strings(raw, ("steps", index)):
            if path[2:] != ("name",):
                yield from _check_template(path, text, scope(frozenset(produced)))
        if step.action == "extract":
            produced.add(step.as_)
    for index, raw in enumerate(_list(data, "verify")):
        for path, text in _strings(raw, ("verify", index)):
            if path[2:] != ("name",):
                yield from _check_template(path, text, scope(all_facts))
    for name, spec in scenario.outputs.items():
        if spec.from_ is not None:
            yield from _check_template(("outputs", name, "from"), spec.from_, scope(all_facts))


def _list(data: dict[str, object], key: str) -> list[object]:
    value = data.get(key)
    return cast("list[object]", value) if isinstance(value, list) else []


def _strings(value: object, path: DataPath) -> Iterator[tuple[DataPath, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in cast("dict[str, object]", value).items():
            yield from _strings(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            yield from _strings(item, (*path, index))


def _check_template(path: DataPath, text: str, scope: _Scope) -> Iterator[CrossIssue]:
    if "{{" not in text and "{%" not in text:
        return
    try:
        tree = _JINJA.parse(text)
        _JINJA.compile(text)
    except TemplateError as error:
        yield _syntax_issue(path, text, error)
        return
    for name in sorted(find_undeclared_variables(tree)):
        if name in RENAMED:
            yield CrossIssue(path, "template.renamed", {"old": name, "new": RENAMED[name]})
        elif name not in VARIABLES:
            yield CrossIssue(
                path, "template.unknown_variable", {"name": name, "choices": ", ".join(VARIABLES)}
            )
    for root, key in _references(tree):
        yield from _check_reference(path, root, key, scope)


def _syntax_issue(path: DataPath, text: str, error: TemplateError) -> CrossIssue:
    stripped = text.replace(" ", "")
    if "{{}}" in stripped:
        return CrossIssue(path, "template.empty")
    if text.count("{{") > text.count("}}"):
        return CrossIssue(path, "template.unclosed")
    return CrossIssue(path, "template.syntax", {"detail": error.message or str(error)})


def _references(tree: nodes.Template) -> Iterator[tuple[str, str]]:
    """``變數.名稱`` 與 ``變數["名稱"]`` 形式的引用，依出現順序、不重複。"""
    found: dict[tuple[str, str], None] = {}
    for node in tree.find_all((nodes.Getattr, nodes.Getitem)):
        target = node.node
        if not isinstance(target, nodes.Name) or target.name not in VARIABLES:
            continue
        if isinstance(node, nodes.Getattr):
            found[(target.name, node.attr)] = None
        elif isinstance(node.arg, nodes.Const) and isinstance(node.arg.value, str):
            found[(target.name, node.arg.value)] = None
    return iter(found)


def _check_reference(path: DataPath, root: str, key: str, scope: _Scope) -> Iterator[CrossIssue]:
    match root:
        case "inputs" if key not in scope.inputs:
            yield CrossIssue(path, "template.undeclared_inputs", {"name": key})
        case "secrets" if key not in scope.secrets:
            yield CrossIssue(path, "template.undeclared_secrets", {"name": key})
        case "facts":
            if scope.facts_before is None:
                yield CrossIssue(path, "template.facts_unavailable")
            elif key not in scope.all_facts:
                yield CrossIssue(path, "template.unknown_fact", {"name": key})
            elif key not in scope.facts_before:
                yield CrossIssue(path, "template.fact_not_yet", {"name": key})
        case _:
            pass
