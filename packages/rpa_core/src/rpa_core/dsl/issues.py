"""把 YAML 錯誤、Pydantic 錯誤與跨欄位問題轉成 Issue：位置、步驟、欄位與目前語言的訊息。

Pydantic 的錯誤是英文且路徑包含內部細節（例如判別聯集的標籤），這裡依模型結構把路徑
還原成 YAML 裡的路徑，再依錯誤種類從訊息目錄取出對應語言的文字。
"""

import difflib
import types
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Final, Literal, Union, cast, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from rpa_core.dsl.checks import CrossIssue
from rpa_core.dsl.fields import catalog, join_names
from rpa_core.dsl.scenario import Scenario
from rpa_core.dsl.steps import ACTIONS
from rpa_core.dsl.yaml_loader import DataPath, Position, SourceMap, YamlLoadError

__all__ = [
    "Issue",
    "format_field",
    "format_issue",
    "issue_from_cross",
    "issue_from_yaml_error",
    "issues_from_validation_error",
]

_MAX_LISTED_CHOICES: Final = 12
"""選項超過這個數量時，訊息不列出全部（例如 ARIA 角色），改提示用 rpa schema 查詢。"""

# Pydantic 錯誤種類 → 訊息目錄的 code
_TYPE_CODES: Final[Mapping[str, str]] = {
    "string_type": "type.string",
    "int_type": "type.integer",
    "int_parsing": "type.integer",
    "int_from_float": "type.integer",
    "float_type": "type.number",
    "float_parsing": "type.number",
    "bool_type": "type.boolean",
    "bool_parsing": "type.boolean",
    "list_type": "type.list",
    "dict_type": "type.object",
    "model_type": "type.object",
    "model_attributes_type": "type.object",
    "string_too_short": "empty_string",
    "too_short": "too_few_items",
    "greater_than": "greater_than",
    "greater_than_equal": "greater_than_equal",
    "less_than": "less_than",
    "less_than_equal": "less_than_equal",
}


@dataclass(frozen=True, slots=True)
class Issue:
    """校驗發現的一個問題。"""

    code: str
    """問題種類，例如 ``missing``、``locator.no_strategy``；訊息目錄的鍵是 ``dsl.<code>``。"""
    message: str
    """目前語言的說明。"""
    path: DataPath
    """在 YAML 中的路徑，例如 ``("steps", 2, "target")``。"""
    position: Position | None
    """在檔案中的位置；無法對應時為 None。"""
    step: int | None = None
    """第幾個步驟（從 1 開始）；問題不在步驟裡時為 None。"""
    step_id: str | None = None
    """該步驟的 id（如果寫了）。"""

    @property
    def field(self) -> str:
        """步驟內（或場景頂層）的欄位路徑，例如 ``target.fallback[0].css``。"""
        return format_field(self.path[2:] if self.step is not None else self.path)


def format_field(path: Sequence[str | int]) -> str:
    """把路徑寫成 ``a.b[0].c`` 的形式。"""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text


def format_issue(issue: Issue) -> str:
    """問題的說明，含步驟與欄位，不含檔案位置。"""
    if issue.step is None:
        location = ""
    elif issue.step_id:
        location = catalog("dsl.location.step", number=issue.step, id=issue.step_id)
    else:
        location = catalog("dsl.location.step_without_id", number=issue.step)
    field = issue.field
    if location and field:
        return catalog("dsl.issue.step_field", step=location, field=field, message=issue.message)
    if location:
        return catalog("dsl.issue.step", step=location, message=issue.message)
    if field:
        return catalog("dsl.issue.field", field=field, message=issue.message)
    return issue.message


# ---------------------------------------------------------------- 建立 Issue


def _make(
    code: str,
    path: DataPath,
    data: object,
    position: Position | None,
    params: Mapping[str, object],
) -> Issue:
    step, step_id = _step_of(path, data)
    message = catalog(f"dsl.{code}", **params)
    return Issue(code, message, path, position, step, step_id)


def _step_of(path: DataPath, data: object) -> tuple[int | None, str | None]:
    if len(path) < 2 or path[0] != "steps" or not isinstance(path[1], int):
        return None, None
    index = path[1]
    step_id: str | None = None
    if isinstance(data, dict):
        steps = cast("dict[str, object]", data).get("steps")
        if isinstance(steps, list) and index < len(cast("list[object]", steps)):
            step = cast("list[object]", steps)[index]
            if isinstance(step, dict):
                value = cast("dict[str, object]", step).get("id")
                if isinstance(value, str) and value:
                    step_id = value
    return index + 1, step_id


def issue_from_yaml_error(error: YamlLoadError) -> Issue:
    """YAML 無法載入時的問題。"""
    params = dict(error.params)
    if isinstance(tag := params.get("tag"), str):
        params["tag"] = tag.replace("tag:yaml.org,2002:", "!!")
    return _make(f"yaml.{error.code}", error.path, None, error.position, params)


def issue_from_cross(issue: CrossIssue, data: object, source: SourceMap | None) -> Issue:
    """跨欄位檢查的問題。"""
    position = source.locate(issue.path) if source else None
    return _make(issue.code, issue.path, data, position, issue.params)


def issues_from_validation_error(
    error: ValidationError, data: object, source: SourceMap | None
) -> list[Issue]:
    """Pydantic 校驗錯誤 → 問題清單，依在檔案中的位置排序。"""
    issues = [_from_details(details, data, source) for details in error.errors()]
    unique = list(dict.fromkeys(issues))
    return sorted(unique, key=lambda i: (i.position or Position(0, 0), str(i.path)))


def _from_details(details: ErrorDetails, data: object, source: SourceMap | None) -> Issue:
    walk = _walk(details["loc"])
    error_type = details["type"]
    context: dict[str, object] = dict(details.get("ctx") or {})
    path = walk.path

    at = context.pop("at", ())
    if isinstance(at, tuple | list):
        path = (*path, *(part for part in at if isinstance(part, str | int)))  # pyright: ignore[reportUnknownVariableType]
    if error_type in ("union_tag_invalid", "union_tag_not_found"):
        # 步驟的 action 寫錯或沒寫：指向 action 欄位（沒寫時位置會落在步驟開頭）
        path = (*path, "action")

    def position(*, key: bool = False) -> Position | None:
        if source is None:
            return None
        return source.locate_key(path) if key else source.locate(path)

    if "." in error_type:
        # 自訂錯誤（dsl_error）的種類都帶有「.」，Pydantic 內建的種類沒有
        return _make(error_type, path, data, position(), context)

    match error_type:
        case "missing":
            return _make("missing", path, data, position(), {"field": path[-1]})
        case "extra_forbidden":
            return _unknown_field(path, walk, data, position(key=True))
        case "union_tag_invalid":
            tag = str(context.get("tag", ""))
            return _with_suggestion("unknown_action", path, data, position(), tag, ACTIONS)
        case "union_tag_not_found":
            return _make("missing_action", path, data, position(), {"choices": join_names(ACTIONS)})
        case "literal_error":
            return _literal(path, walk, data, position(), details.get("input"))
        case _ if error_type in _TYPE_CODES:
            if walk.is_key:
                return _make(_TYPE_CODES[error_type], path, data, position(key=True), context)
            return _make(_TYPE_CODES[error_type], path, data, position(), context)
        case _:
            return _make("generic", path, data, position(), {"detail": details["msg"]})


def _unknown_field(path: DataPath, walk: "_Walk", data: object, position: Position | None) -> Issue:
    name = str(path[-1])
    allowed = list(_aliases(walk.parent)) if walk.parent is not None else []
    return _with_suggestion("unknown_field", path, data, position, name, allowed)


def _with_suggestion(
    code: str,
    path: DataPath,
    data: object,
    position: Position | None,
    value: str,
    choices: Sequence[str],
) -> Issue:
    suggestion = _suggest(value, choices)
    if suggestion is not None:
        return _make(
            f"{code}.suggest", path, data, position, {"value": value, "suggestion": suggestion}
        )
    return _make(code, path, data, position, {"value": value, "choices": join_names(choices)})


def _literal(
    path: DataPath, walk: "_Walk", data: object, position: Position | None, value: object
) -> Issue:
    choices = [str(choice) for choice in walk.literal_choices]
    if path == ("schemaVersion",):
        return _make(
            "schema_version", path, data, position, {"value": value, "current": choices[0]}
        )
    text = value if isinstance(value, str) else repr(value)
    suggestion = _suggest(text, choices) if isinstance(value, str) else None
    if suggestion is not None:
        return _make(
            "choice.suggest", path, data, position, {"value": text, "suggestion": suggestion}
        )
    if choices and len(choices) <= _MAX_LISTED_CHOICES:
        return _make(
            "choice", path, data, position, {"value": text, "choices": join_names(choices)}
        )
    return _make("choice.many", path, data, position, {"value": text})


def _suggest(value: str, choices: Sequence[str]) -> str | None:
    """找出最接近的名稱：先比不分大小寫，再比拼字相近。"""
    if not value or not choices:
        return None
    lowered = {choice.lower(): choice for choice in choices}
    if (exact := lowered.get(value.lower())) is not None and exact != value:
        return exact
    matches = difflib.get_close_matches(value, list(choices), n=1, cutoff=0.6)
    if matches and matches[0] != value:
        return matches[0]
    matches = difflib.get_close_matches(value.lower(), list(lowered), n=1, cutoff=0.6)
    return lowered[matches[0]] if matches and lowered[matches[0]] != value else None


# ---------------------------------------------------------------- 依模型結構還原路徑


@dataclass(frozen=True, slots=True)
class _Walk:
    path: DataPath
    """YAML 中的路徑（去掉判別聯集的標籤）。"""
    annotation: object
    """路徑終點的型別註記；無法判斷時為 None。"""
    parent: type[BaseModel] | None
    """路徑終點所在的模型（終點是欄位時）或終點本身（終點是物件時）。"""
    is_key: bool = False
    """錯誤出在物件的鍵而不是值。"""

    @property
    def literal_choices(self) -> tuple[object, ...]:
        annotation = _strip(self.annotation)
        if get_origin(annotation) is Literal:
            return get_args(annotation)
        return ()


def _strip(annotation: object) -> object:
    """去掉 Annotated 與 ``| None``。"""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
        elif origin in (Union, types.UnionType):
            members = [a for a in get_args(annotation) if a is not type(None)]
            if len(members) != 1:
                return annotation
            annotation = members[0]
        else:
            return annotation


def _model_class(annotation: object) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _aliases(model: type[BaseModel]) -> Iterable[str]:
    for name, info in model.model_fields.items():
        yield info.alias or name


def _field_annotation(model: type[BaseModel], key: str) -> object:
    for name, info in model.model_fields.items():
        if (info.alias or name) == key:
            # 保留 Annotated 的資訊（例如 Literal 的選項）
            return info.rebuild_annotation()
    return None


def _union_member(annotation: object, tag: str) -> type[BaseModel] | None:
    """判別聯集中 action 為 tag 的模型。"""
    if get_origin(annotation) not in (Union, types.UnionType):
        return None
    for member in get_args(annotation):
        model = _model_class(member)
        if model is None or "action" not in model.model_fields:
            continue
        if tag in get_args(model.model_fields["action"].annotation):
            return model
    return None


def _walk(loc: Sequence[str | int]) -> _Walk:
    annotation: object = Scenario
    parent: type[BaseModel] | None = None
    path: list[str | int] = []
    is_key = False
    for part in loc:
        annotation = _strip(annotation)
        if part == "[key]":
            is_key = True
            continue
        if isinstance(part, str) and (member := _union_member(annotation, part)) is not None:
            annotation = member
            continue
        path.append(part)
        if (model := _model_class(annotation)) is not None:
            parent = model
            annotation = _field_annotation(model, str(part))
        else:
            origin = get_origin(annotation)
            args = get_args(annotation)
            if origin is list and args:
                annotation = args[0]
            elif origin is dict and len(args) == 2:
                annotation = args[1]
            else:
                annotation = None
    final_model = _model_class(_strip(annotation))
    return _Walk(tuple(path), annotation, final_model or parent, is_key)
