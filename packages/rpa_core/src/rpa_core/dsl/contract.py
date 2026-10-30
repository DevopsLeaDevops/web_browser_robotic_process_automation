"""場景契約：入參、出參、獨立斷言與 Python 節點（``script``）。決策背景見 ADR 0009、0020。

一次成功的執行是：入參通過校驗 → 自動化（DSL 步驟或 automation.py）→ 留下頁面事實 facts
→ 獨立斷言（verify 或 assertion.py）→ 出參通過校驗 → 才發布 output.json。
「腳本沒有拋錯」不等於成功。

入參與出參的限制取 JSON Schema 2020-12 的常用子集，可以直接匯出成 JSON Schema，
給 API、管理介面與上游場景（編排時串接出參）使用。
"""

import math
import re
from collections.abc import Iterable, Iterator
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from rpa_core.dsl.dynamic import DynamicValueError, has_dynamic, parse
from rpa_core.dsl.fields import DslModel, NonEmptyStr, dsl_error
from rpa_core.dsl.files import (
    ATTACHMENT_DIR,
    FileValueError,
    accept_rule_ok,
    file_values,
    parse_size,
)

__all__ = [
    "PLATFORMS",
    "RUNTIMES",
    "InputSpec",
    "InputType",
    "OutputSpec",
    "OutputType",
    "Platform",
    "ScriptConfig",
    "ScriptFile",
    "ScriptPath",
    "ValueSpec",
    "VerifyCheck",
    "spec_json_schema",
]

InputType = Literal["string", "number", "integer", "boolean", "array", "object", "file"]
"""``file``（M7c）：要上傳的檔案，值的寫法見 :mod:`rpa_core.dsl.files`。
``array``、``object``（Python 節點）：JSON 的陣列與物件，上游的同型別出參可以直接接進來。"""
OutputType = Literal["string", "number", "integer", "boolean", "array", "object", "file"]
"""``file``（ADR 0020）：產出的檔案。``from`` 或 assertion.py 給出共用工作資料夾、或 Python 節點
``outputs/`` 裡的一個檔案（路徑，或 download 步驟的事實）；出參階段把它複製進執行目錄的
``outputs/``，值是 ``{"workspace", "name", "size", "sha256"}``，可以接到下游的 file 入參。"""

_STRING_ONLY: Final = (
    ("min_length", "minLength"),
    ("max_length", "maxLength"),
    ("pattern", "pattern"),
)
_NUMBER_ONLY: Final = (("minimum", "minimum"), ("maximum", "maximum"))
_SCRIPT_PATH: Final = re.compile(
    r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_.-]*\.py"
)
_SCRIPT_FILE: Final = re.compile(r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_.-]*")
MAX_SCRIPT_FILES: Final = 16
"""``script.files`` 最多幾個（加上場景檔與兩支腳本，不超過管理 Portal 一個版本的 20 個檔案）。"""
RUNTIMES: Final = ("1",)
"""這份程式認得的 RPA Python 運行環境主版本（``script.runtime``）。"""
Platform = Literal["windows", "macos", "linux"]
PLATFORMS: Final[tuple[Platform, ...]] = ("windows", "macos", "linux")
"""``script.platforms`` 可以寫的系統。"""


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
        case "file":
            return isinstance(value, str | dict | list)
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
        if self.enum is not None and self.type in ("array", "object", "file"):
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
    """預設值，要符合型別與限制；沒有預設值代表執行時必須提供。

    可以是動態值（例如 ``{{today}}``、``{{random:10:30}}``，見 :mod:`rpa_core.dsl.dynamic`），
    每次執行開始時求值。``type: file`` 的預設值是場景附件或那台電腦上的路徑，不能是上傳檔。
    """
    accept: Annotated[list[NonEmptyStr], Field(min_length=1)] | None = None
    """``type: file``：接受的檔案，``.副檔名`` 或 MIME（``image/png``、``image/*``）。"""
    max_size: NonEmptyStr | None = None
    """``type: file``：單一檔案的上限，例如 ``20MB``（單位 B、KB、MB、GB）。"""
    multiple: bool | None = None
    """``type: file``：true 時一次可以有多個檔案，值是清單；沒寫是單一檔案。"""

    @model_validator(mode="after")
    def _check_file(self) -> Self:
        if self.type != "file":
            for attr, alias in (("accept", "accept"), ("max_size", "maxSize")):
                if getattr(self, attr) is not None:
                    raise dsl_error("value.not_applicable", at=[alias], field=alias, type=self.type)
            if self.multiple is not None:
                raise dsl_error(
                    "value.not_applicable", at=["multiple"], field="multiple", type=self.type
                )
            return self
        for index, rule in enumerate(self.accept or ()):
            if not accept_rule_ok(rule):
                raise dsl_error("file.accept_format", at=["accept", index], value=rule)
        if self.max_size is not None:
            try:
                parse_size(self.max_size)
            except FileValueError as error:
                raise dsl_error("file.max_size", at=["maxSize"], detail=error.message) from error
        return self

    @model_validator(mode="after")
    def _check_default(self) -> Self:
        if self.default is not None:
            try:
                rules = self.check_value(self.default)
            except DynamicValueError as error:
                raise dsl_error(f"dynamic.{error.code}", at=["default"], **error.params) from error
            if self.type == "file" and not rules:
                for item in file_values(self.default, multiple=bool(self.multiple)):
                    if item.source == "upload":
                        raise dsl_error("file.default_upload", at=["default"])
            for rule in rules:
                raise dsl_error("value.default_invalid", at=["default"], rule=rule)
        return self

    @property
    def max_bytes(self) -> int | None:
        """``maxSize`` 的位元組數；沒寫時是 None（用伺服器的上限）。"""
        return parse_size(self.max_size) if self.max_size is not None else None

    def violations(self, value: object) -> Iterator[str]:
        """值不符合的限制；``type: file`` 時是值的寫法錯在哪裡（目前語言的說明）。"""
        if self.type != "file":
            yield from super().violations(value)
            return
        try:
            file_values(value, multiple=bool(self.multiple))
        except FileValueError as error:
            yield error.message

    def check_value(self, value: object) -> list[str]:
        """存檔與排隊前的校驗：動態值只檢查語法，普通值檢查型別與限制。

        不讀時鐘、不抽隨機數，也不推測所有可能的結果；動態值的約束在實際執行開始時校驗。
        ``type: file`` 只檢查寫法（路徑裡的動態值檢查語法），檔案在不在、多大、類型對不對
        要到執行的那台才知道。
        """
        if self.type == "file":
            rules = list(self.violations(value))
            if not rules:
                for item in file_values(value, multiple=bool(self.multiple)):
                    if item.source == "path" and has_dynamic(item.ref):
                        parse(item.ref)
            return rules
        if isinstance(value, str) and has_dynamic(value):
            parse(value)
            return []
        return list(self.violations(value))


class OutputSpec(ValueSpec):
    """一個出參：自動化與獨立斷言都通過之後才發布，可以串到下游場景的入參。"""

    type: OutputType = "string"  # pyright: ignore[reportIncompatibleVariableOverride]
    from_: NonEmptyStr | None = Field(default=None, alias="from")
    """取值的運算式，例如 ``{{ facts.record.recordId }}``。

    Python 節點用 assertion.py 斷言時，出參由它產生，不寫 from；用 verify 時同 DSL。
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


def _check_script_file(value: str) -> str:
    if not _SCRIPT_FILE.fullmatch(value) or len(value) > 200:
        raise dsl_error("format.script_file", value=value)
    if value == ATTACHMENT_DIR or value.startswith(f"{ATTACHMENT_DIR}/"):
        raise dsl_error("script.file_in_attachments", value=value, folder=ATTACHMENT_DIR)
    return value


ScriptFile = Annotated[str, AfterValidator(_check_script_file)]
"""腳本會用到的其他文字檔（相對於場景檔所在目錄），任何副檔名；二進位檔放場景附件 ``files/``。"""


class ScriptConfig(DslModel):
    """Python 節點：DSL 表達不了、或瀏覽器做不到的事（檔案、資料、網路），沿用同一份檔案契約。

    - automation.py 接受 ``--input --facts --screenshot --target-url``，把觀察到的事實寫進 facts
    - assertion.py 接受 ``--input --facts --output``，獨立比對事實與入參，寫出候選出參

    兩種模式（ADR 0020）：

    - **相容模式**（沒寫 ``runtime``）：和 M1.1 起的腳本場景完全相同，用執行端自己的 Python，
      腳本可以自己用 Playwright 開瀏覽器；``assertion`` 必要。
    - **運行環境模式**（``runtime: "1"``）：跑在平台建置的 RPA Python 運行環境，不開瀏覽器；
      斷言可以是 ``assertion`` 或場景的 ``verify``。

    審核時特別標示；錄製與 AI 不會產生這種場景。
    """

    runtime: Literal["1"] | None = None
    """RPA Python 運行環境的主版本；沒寫是相容模式。"""
    automation: ScriptPath
    assertion: ScriptPath | None = None
    """獨立斷言的腳本；相容模式必要，運行環境模式可以改用場景的 ``verify``。"""
    files: Annotated[list[ScriptFile], Field(max_length=MAX_SCRIPT_FILES)] | None = None
    """腳本會用到的其他文字檔（例如 helpers.py、SQL、JSON 範本），跟著版本存放、納入雜湊。"""
    platforms: Annotated[list[Platform], Field(min_length=1)] | None = None
    """只在這些系統執行；沒寫是不限。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        scripts = {self.automation, *([self.assertion] if self.assertion else [])}
        seen: set[str] = set()
        for index, name in enumerate(self.files or ()):
            if name in seen or name in scripts:
                raise dsl_error("script.file_duplicate", at=["files", index], value=name)
            seen.add(name)
        if self.platforms is not None and len(set(self.platforms)) != len(self.platforms):
            raise dsl_error("script.platform_duplicate", at=["platforms"])
        return self

    @property
    def uses_runtime(self) -> bool:
        """運行環境模式：用 RPA Python 運行環境、不開瀏覽器。"""
        return self.runtime is not None

    def runs_on(self, runtimes: Iterable[str], platform: str | None) -> bool:
        """一台裝置能不能執行這個運行環境模式的節點（派工用）。

        ``runtimes`` 是裝置有的運行環境版本（例如 ``1.0.0``），要有這個主版本；``platform`` 是
        平台代號（例如 ``windows-x86_64``），系統要在 ``platforms`` 裡（沒寫是不限）。
        """
        if self.runtime is None:
            return True
        if not any(version.split(".", 1)[0] == self.runtime for version in runtimes):
            return False
        family = (platform or "").split("-", 1)[0]
        return self.platforms is None or family in self.platforms


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
    if isinstance(spec, InputSpec) and spec.type == "file":
        # 檔案入參的值有三種寫法（見 rpa_core.dsl.files），不是單一 JSON 型別：用擴充欄位說明
        del schema["type"]
        info: dict[str, object] = {"multiple": bool(spec.multiple)}
        if spec.accept is not None:
            info["accept"] = list(spec.accept)
        if spec.max_size is not None:
            info["maxSize"] = spec.max_size
        schema["x-rpa-file"] = info
    if isinstance(spec, InputSpec) and spec.default is not None:
        if has_dynamic(spec.default):
            # 動態值每次執行才求值，不是 JSON Schema 的 default（整數入參的寫法還是文字）
            schema["x-dynamicDefault"] = spec.default
        else:
            schema["default"] = spec.default
    return schema
