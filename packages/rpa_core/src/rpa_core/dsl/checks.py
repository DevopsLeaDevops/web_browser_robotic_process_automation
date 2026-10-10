"""跨欄位、跨步驟的檢查：只在場景的結構都正確之後執行。

- 步驟 id 不能重複、secrets 名稱不能重複
- goto 的網址以 / 開頭時，要有 browser.baseUrl
- ``{{ }}`` 要成對、不能是空的；``params.名稱``、``secrets.名稱`` 要先宣告

``{{ }}`` 的求值在 M3 才加入，這裡只做不需要執行就能發現的檢查。
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast

from rpa_core.dsl.yaml_loader import DataPath

if TYPE_CHECKING:
    from rpa_core.dsl.scenario import Scenario

__all__ = ["CrossIssue", "cross_check"]

_TEMPLATE: Final = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_REFERENCE: Final = re.compile(r"(?<![\w.])(params|secrets)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True, slots=True)
class CrossIssue:
    """一個跨欄位的問題；code 對應訊息目錄的 ``dsl.<code>``。"""

    path: DataPath
    code: str
    params: dict[str, object] = field(default_factory=dict[str, object])


def cross_check(scenario: "Scenario") -> list[CrossIssue]:
    """回傳場景中所有跨欄位的問題，依出現順序排列。"""
    issues: list[CrossIssue] = []
    issues.extend(_duplicate_names(scenario))
    issues.extend(_relative_urls(scenario))
    data = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    declared = {"params": set(scenario.params), "secrets": set(scenario.secrets)}
    for path, text in _strings(data, ()):
        if not _is_free_text(path):
            issues.extend(_check_template(path, text, declared))
    return issues


def _duplicate_names(scenario: "Scenario") -> Iterator[CrossIssue]:
    seen_secrets: dict[str, int] = {}
    for index, name in enumerate(scenario.secrets):
        if name in seen_secrets:
            yield CrossIssue(("secrets", index), "secret.duplicate", {"name": name})
        else:
            seen_secrets[name] = index
    seen_steps: dict[str, int] = {}
    for index, step in enumerate(scenario.steps):
        if step.id in seen_steps:
            first = seen_steps[step.id] + 1
            yield CrossIssue(
                ("steps", index, "id"), "step.duplicate_id", {"id": step.id, "first": first}
            )
        else:
            seen_steps[step.id] = index


def _relative_urls(scenario: "Scenario") -> Iterator[CrossIssue]:
    if scenario.browser.base_url is not None:
        return
    for index, step in enumerate(scenario.steps):
        if step.action == "goto" and step.url.startswith("/"):
            yield CrossIssue(
                ("steps", index, "url"), "url.relative_without_base", {"value": step.url}
            )


def _strings(value: object, path: DataPath) -> Iterator[tuple[DataPath, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in cast("dict[str, object]", value).items():
            yield from _strings(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            yield from _strings(item, (*path, index))


def _is_free_text(path: DataPath) -> bool:
    """場景與步驟的名稱、說明是給人看的文字，不會代入 {{ }}。"""
    match path:
        case ("name" | "description",):
            return True
        case ("params", _, "description"):
            return True
        case ("steps", int(), "name"):
            return True
        case _:
            return False


def _check_template(
    path: DataPath, text: str, declared: dict[str, set[str]]
) -> Iterator[CrossIssue]:
    if "{{" not in text:
        return
    for match in _TEMPLATE.finditer(text):
        expression = match.group(1).strip()
        if not expression:
            yield CrossIssue(path, "template.empty")
            continue
        for reference in _REFERENCE.finditer(expression):
            kind, name = reference.group(1), reference.group(2)
            if name not in declared[kind]:
                yield CrossIssue(path, f"template.undeclared_{kind}", {"name": name})
    if "{{" in _TEMPLATE.sub("", text):
        yield CrossIssue(path, "template.unclosed")
