"""場景：DSL 的最上層。"""

import math
from typing import Annotated, Final, Literal, Self, cast

from pydantic import Field, ValidationInfo, model_validator

from rpa_core.dsl.checks import CrossIssue, cross_check
from rpa_core.dsl.fields import (
    ABSOLUTE_URL,
    DslModel,
    Identifier,
    NonEmptyStr,
    SecretName,
    Slug,
    TimeoutMs,
    dsl_error,
)
from rpa_core.dsl.steps import Step

__all__ = [
    "CROSS_ISSUES_CONTEXT",
    "SCHEMA_VERSION",
    "BrowserConfig",
    "Defaults",
    "ParamSpec",
    "Scenario",
    "Viewport",
]

SCHEMA_VERSION: Final = 1
"""目前的 DSL 版本。格式有不相容的變更時遞增，並提供遷移。"""

CROSS_ISSUES_CONTEXT: Final = "cross_issues"
"""校驗時在 context 放一個 list 用這個鍵，跨欄位的問題會全部收集進去，而不是只拋出第一個。"""

ParamType = Literal["string", "number", "integer", "boolean"]


def _matches_type(value: object, param_type: ParamType) -> bool:
    match param_type:
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


class ParamSpec(DslModel):
    """場景參數的宣告；執行時由使用者或排程提供值。"""

    type: ParamType = "string"
    default: object = None
    """預設值，型別要符合 type；沒有預設值代表執行時必須提供。"""
    description: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.default is not None and not _matches_type(self.default, self.type):
            raise dsl_error("param.default_type", at=["default"], type=self.type)
        return self


class Viewport(DslModel):
    """瀏覽器視窗大小（像素）。"""

    width: Annotated[int, Field(gt=0, le=10_000)]
    height: Annotated[int, Field(gt=0, le=10_000)]


class BrowserConfig(DslModel):
    """執行這個場景的瀏覽器設定。"""

    engine: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = True
    viewport: Viewport | None = None
    base_url: NonEmptyStr | None = None
    """goto 的網址以 / 開頭時接在這後面；不同環境（測試、正式）可以只換這一項。"""
    locale: NonEmptyStr | None = None
    """瀏覽器語言，例如 zh-TW；影響頁面顯示的語言與日期格式。"""

    @model_validator(mode="after")
    def _check(self) -> Self:
        url = self.base_url
        if url is not None and "{{" not in url and not ABSOLUTE_URL.fullmatch(url):
            raise dsl_error("url.invalid_base", at=["baseUrl"], value=url)
        return self


class Defaults(DslModel):
    """所有步驟共用的預設值。"""

    timeout: TimeoutMs | None = None
    """步驟預設逾時（毫秒）；沒寫由執行引擎決定。"""


class Scenario(DslModel):
    """一個瀏覽器自動化場景。

    以 ``rpa_core.dsl.validate_text`` 或 ``validate_file`` 載入 YAML，可以得到所有問題與位置；
    直接 ``Scenario.model_validate(資料)`` 也會做同樣的檢查，但只回報每個物件的第一個問題。
    """

    schema_version: Literal[1]
    """DSL 版本，目前是 1。"""
    id: Slug
    name: NonEmptyStr
    description: NonEmptyStr | None = None
    params: dict[Identifier, ParamSpec] = Field(default_factory=dict[str, ParamSpec])
    secrets: list[SecretName] = Field(default_factory=list[str])
    """執行時注入的機密名稱。值不寫在場景裡，日誌與截圖說明會遮罩。"""
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    defaults: Defaults = Field(default_factory=Defaults)
    steps: Annotated[list[Step], Field(min_length=1)]

    @model_validator(mode="after")
    def _cross_check(self, info: ValidationInfo) -> Self:
        issues = cross_check(self)
        context: object = info.context
        if isinstance(context, dict) and CROSS_ISSUES_CONTEXT in context:
            sink = cast(
                "list[CrossIssue]", cast("dict[str, object]", context)[CROSS_ISSUES_CONTEXT]
            )
            sink.extend(issues)
        elif issues:
            first = issues[0]
            raise dsl_error(first.code, at=first.path, **first.params)
        return self
