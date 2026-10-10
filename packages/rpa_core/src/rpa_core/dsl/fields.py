"""DSL 模型共用的基底類別、欄位型別與自訂錯誤。

自訂錯誤的 error_type 就是 rpa_core 訊息目錄中 ``dsl.<code>`` 的 code；英文訊息當作
Pydantic 的 message_template，所以直接印出 ValidationError 時也看得懂。
需要指向模型裡某個欄位時，在 context 放 ``at``（相對路徑），轉換成 Issue 時會接在後面。
"""

import re
from collections.abc import Iterable
from typing import Annotated, Final, LiteralString, cast

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from rpa_core.i18n import Catalog

__all__ = [
    "ABSOLUTE_URL",
    "DslModel",
    "FileName",
    "Identifier",
    "NonEmptyStr",
    "OneOrMany",
    "SecretName",
    "Slug",
    "TimeoutMs",
    "dsl_error",
    "join_names",
]

catalog: Final = Catalog("rpa_core")
"""rpa_core 的訊息目錄。"""

ABSOLUTE_URL: Final = re.compile(r"https?://\S+")
"""完整的 http(s) 網址（只粗略檢查開頭與沒有空白）。"""

MAX_TIMEOUT_MS: Final = 3_600_000
"""逾時上限一小時；超過多半是多打了幾個 0。"""


class DslModel(BaseModel):
    """所有 DSL 模型的基底：欄位用 camelCase、不接受未知欄位、不自動轉型、建立後不可修改。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
    )


def dsl_error(code: str, at: Iterable[str | int] = (), **params: object) -> PydanticCustomError:
    """建立自訂的校驗錯誤；``at`` 是相對於目前模型的欄位路徑。"""
    template = catalog.messages("en")[f"dsl.{code}"]
    # 英文訊息只在直接印出 ValidationError 時用到，大括號照 Pydantic 的規則寫
    context: dict[str, object] = {**params, "at": tuple(at)}
    # Pydantic 要求 LiteralString 以防注入；code 與範本都來自本套件的程式與訊息目錄
    return PydanticCustomError(
        cast("LiteralString", code), cast("LiteralString", template), context
    )


def join_names(names: Iterable[str]) -> str:
    """把欄位或選項名稱串成一行，給訊息參數用（名稱本身不翻譯）。"""
    return ", ".join(names)


def _pattern_checker(code: str, pattern: str) -> AfterValidator:
    compiled = re.compile(pattern)

    def check(value: str) -> str:
        if not compiled.fullmatch(value):
            raise dsl_error(f"format.{code}", value=value)
        return value

    return AfterValidator(check)


NonEmptyStr = Annotated[str, Field(min_length=1)]
"""不能是空字串。"""

Slug = Annotated[str, _pattern_checker("slug", r"[a-z0-9][a-z0-9_-]{0,63}")]
"""場景與步驟的 id：小寫英文字母、數字、- 與 _，以英數開頭，最長 64 個字元。

會用在產物的檔名與網址，所以不允許中文與大寫。
"""

Identifier = Annotated[str, _pattern_checker("identifier", r"[A-Za-z_][A-Za-z0-9_]{0,63}")]
"""參數名稱、extract 的變數名稱：之後要在 ``{{ params.名稱 }}`` 中引用。"""

SecretName = Annotated[str, _pattern_checker("secret_name", r"[A-Z][A-Z0-9_]{0,63}")]
"""Secrets 名稱：大寫英文字母、數字與 _，例如 ERP_PASSWORD。"""

FileName = Annotated[str, _pattern_checker("file_name", r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")]
"""產物檔名（不含副檔名）。"""

TimeoutMs = Annotated[int, Field(gt=0, le=MAX_TIMEOUT_MS)]
"""逾時，毫秒整數。"""


def _one_or_many(value: object) -> object:
    """單一字串視為只有一項的清單；其他型別交給清單校驗回報。"""
    if isinstance(value, str):
        return [value]
    return value


OneOrMany = Annotated[
    list[str],
    BeforeValidator(_one_or_many, json_schema_input_type=str | list[str]),
    Field(min_length=1),
]
"""可以寫單一字串，也可以寫字串清單；載入後一律是清單。"""
