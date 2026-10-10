"""場景契約：入參、出參、獨立斷言與 Python 腳本逃生門。決策背景見 ADR 0009。

一次成功的執行是：入參通過校驗 → 自動化（DSL 步驟或 automation.py）→ 留下頁面事實 facts
→ 獨立斷言（verify 或 assertion.py）→ 出參通過校驗 → 才發布 output.json。
「腳本沒有拋錯」不等於成功。

入參與出參的限制取 JSON Schema 2020-12 的常用子集，可以直接匯出成 JSON Schema，
給 API、管理介面與上游場景（編排時串接出參）使用。
"""

import math
import re
from collections.abc import Iterator
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from rpa_core.dsl.fields import DslModel, NonEmptyStr, dsl_error

__all__ = [
    "InputSpec",
    "InputType",
    "OutputSpec",
    "OutputType",
    "ScriptConfig",
    "ScriptPath",
    "ValueSpec",
    "VerifyCheck",
    "spec_json_schema",
]

InputType = Literal["string", "number", "integer", "boolean"]
OutputType = Literal["string", "number", "integer", "boolean", "array", "object"]

_STRING_ONLY: Final = (
    ("min_length", "minLength"),
    ("max_length", "maxLength"),
    ("pattern", "pattern"),
)
_NUMBER_ONLY: Final = (("minimum", "minimum"), ("maximum", "maximum"))
_SCRIPT_PATH: Final = re.compile(
    r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_.-]*\.py"
)


def matches_type(value: object, value_type: str) -> bool:
    """值是否符合 JSON Schema 的型別（布林不算數字）。"""
    match value_type:
        case "string":
            return isinstance(value, str)
        case "boolean":
            return isinstance(value, bool)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return (
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and not (isinstance(value, float) and not math.isfinite(value))
            )
        case "array":
            return isinstance(value, list)
        case "object":
            return isinstance(value, dict)
        case _:
            return False


class ValueSpec(DslModel):
    """入參與出參共用的型別與限制。"""

    type: str
    description: NonEmptyStr | None = None
    enum: Annotated[list[object], Field(min_length=1)] | None = None
    """允許的值。"""
    min_length: Annotated[int, Field(ge=0)] | None = None
    max_length: Annotated[int, Field(ge=0)] | None = None
    pattern: NonEmptyStr | None = None
    """正規表示式（Python re 語法），整個字串要符合時請加 ^ 與 $。"""
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def _check_constraints(self) -> Self:
        for attr, alias in _STRING_ONLY:
            if getattr(self, attr) is not None and self.type != "string":
                raise dsl_error("value.not_applicable", at=[alias], field=alias, type=self.type)
        for attr, alias in _NUMBER_ONLY:
            if getattr(self, attr) is not None and self.type not in ("number", "integer"):
                raise dsl_error("value.not_applicable", at=[alias], field=alias, type=self.type)
        if self.enum is not None and self.type in ("array", "object"):
            raise dsl_error("value.not_applicable", at=["enum"], field="enum", type=self.type)
        pairs = (("min_length", "max_length", "maxLength"), ("minimum", "maximum", "maximum"))
        for low, high, alias in pairs:
            low_value, high_value = getattr(self, low), getattr(self, high)
            if low_value is not None and high_value is not None and low_value > high_value:
                raise dsl_error("value.range", at=[alias])
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise dsl_error("regex.invalid", at=["pattern"], detail=str(error)) from error
        for index, item in enumerate(self.enum or ()):
            if not matches_type(item, self.type):
                raise dsl_error("value.enum_type", at=["enum", index], type=self.type)
        return self

    def violations(self, value: object) -> Iterator[str]:
        """值不符合的限制（以 DSL 寫法表示，例如 ``maximum: 30``）；完全符合時什麼都不產生。"""
        if not matches_type(value, self.type):
            yield f"type: {self.type}"
            return
        if self.enum is not None and value not in self.enum:
            yield "enum"
        if isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                yield f"minLength: {self.min_length}"
            if self.max_length is not None and len(value) > self.max_length:
                yield f"maxLength: {self.max_length}"
            if self.pattern is not None and re.search(self.pattern, value) is None:
                yield "pattern"
        if isinstance(value, int | float) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                yield f"minimum: {_number(self.minimum)}"
            if self.maximum is not None and value > self.maximum:
                yield f"maximum: {_number(self.maximum)}"


def _number(value: float) -> int | float:
    """整數值的 float 顯示成整數（30.0 → 30）。"""
    return int(value) if value.is_integer() else value


class InputSpec(ValueSpec):
    """一個入參：執行時由使用者、API 或上游場景的出參提供。啟動瀏覽器之前校驗。"""

    type: InputType = "string"  # pyright: ignore[reportIncompatibleVariableOverride]
    default: object = None
    """預設值，要符合型別與限制；沒有預設值代表執行時必須提供。"""

    @model_validator(mode="after")
    def _check_default(self) -> Self:
        if self.default is not None:
            for rule in self.violations(self.default):
                raise dsl_error("value.default_invalid", at=["default"], rule=rule)
        return self


class OutputSpec(ValueSpec):
    """一個出參：自動化與獨立斷言都通過之後才發布，可以串到下游場景的入參。"""

    type: OutputType = "string"  # pyright: ignore[reportIncompatibleVariableOverride]
    from_: NonEmptyStr | None = Field(default=None, alias="from")
    """取值的運算式，例如 ``{{ facts.record.recordId }}``。

    Python 腳本場景的出參由 assertion.py 產生，不寫 from。
    """


class VerifyCheck(DslModel):
    """獨立斷言的一條規則：在自動化結束後，比對頁面事實與入參。

    value 與比較值都以 ``{{ }}`` 代入後的文字比較。
    """

    name: NonEmptyStr | None = None
    """給人看的說明，會出現在報告。"""
    value: NonEmptyStr
    """要檢查的值，必須含有 ``{{ }}``，例如 ``{{ facts.record.status }}``。"""
    equals: str | None = None
    contains: str | None = None
    matches: NonEmptyStr | None = None
    """正規表示式（Python re 語法）。"""
    not_empty: Literal[True] | None = None
    """值不是空字串。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if "{{" not in self.value:
            raise dsl_error("verify.constant_value", at=["value"])
        checks = (("equals", "equals"), ("contains", "contains"), ("matches", "matches"))
        used = [
            alias
            for attr, alias in (*checks, ("not_empty", "notEmpty"))
            if getattr(self, attr) is not None
        ]
        if not used:
            raise dsl_error("one_of.none", fields="equals, contains, matches, notEmpty")
        if len(used) > 1:
            raise dsl_error("one_of.many", at=[used[1]], fields=", ".join(used))
        if self.matches is not None and "{{" not in self.matches:
            try:
                re.compile(self.matches)
            except re.error as error:
                raise dsl_error("regex.invalid", at=["matches"], detail=str(error)) from error
        return self


def _check_script_path(value: str) -> str:
    if not _SCRIPT_PATH.fullmatch(value):
        raise dsl_error("format.script_path", value=value)
    return value


ScriptPath = Annotated[str, AfterValidator(_check_script_path)]
"""Python 腳本的相對路徑（相對於場景檔所在目錄），不能用 .. 或絕對路徑。"""


class ScriptConfig(DslModel):
    """Python 腳本逃生門：DSL 表達不了的場景，用原型的檔案契約執行。

    - automation.py 接受 ``--input --facts --screenshot --target-url``，把頁面事實寫進 facts
    - assertion.py 接受 ``--input --facts --output``，獨立比對事實與入參，寫出候選出參

    審核時特別標示；錄製與 AI 不會產生這種場景。
    """

    automation: ScriptPath
    assertion: ScriptPath


def spec_json_schema(spec: ValueSpec) -> dict[str, object]:
    """一個入參或出參的 JSON Schema（2020-12）。"""
    schema: dict[str, object] = {"type": spec.type}
    if spec.description is not None:
        schema["description"] = spec.description
    if spec.enum is not None:
        schema["enum"] = list(spec.enum)
    if spec.min_length is not None:
        schema["minLength"] = spec.min_length
    if spec.max_length is not None:
        schema["maxLength"] = spec.max_length
    if spec.pattern is not None:
        schema["pattern"] = spec.pattern
    if spec.minimum is not None:
        schema["minimum"] = _number(spec.minimum)
    if spec.maximum is not None:
        schema["maximum"] = _number(spec.maximum)
    if isinstance(spec, InputSpec) and spec.default is not None:
        schema["default"] = spec.default
    return schema
