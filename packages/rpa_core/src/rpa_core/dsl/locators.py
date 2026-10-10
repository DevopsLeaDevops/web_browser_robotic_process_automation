"""定位器：描述要操作的頁面元素。

每個定位器恰好指定一種主要方式，優先順序（錄製與 AI 生成時依此挑選）：
testId → role + name → label → placeholder → text → altText → title → css → xpath。
對應 Playwright 的 get_by_test_id、get_by_role、get_by_label 等方法。
"""

from typing import Final, Literal, Self, get_args

from pydantic import Field, model_validator

from rpa_core.dsl.fields import DslModel, NonEmptyStr, dsl_error, join_names

__all__ = ["ARIA_ROLES", "STRATEGIES", "AriaRole", "Locator"]

STRATEGIES: Final = (
    "testId",
    "role",
    "label",
    "placeholder",
    "text",
    "altText",
    "title",
    "css",
    "xpath",
)
"""主要定位方式（DSL 欄位名稱），依建議的優先順序排列。"""

_EXACT_STRATEGIES: Final = frozenset({"role", "label", "placeholder", "text", "altText", "title"})
"""支援 exact（完全相符）的定位方式；role 要搭配 name 才有意義。"""

AriaRole = Literal[
    "alert",
    "alertdialog",
    "application",
    "article",
    "banner",
    "blockquote",
    "button",
    "caption",
    "cell",
    "checkbox",
    "code",
    "columnheader",
    "combobox",
    "complementary",
    "contentinfo",
    "definition",
    "deletion",
    "dialog",
    "directory",
    "document",
    "emphasis",
    "feed",
    "figure",
    "form",
    "generic",
    "grid",
    "gridcell",
    "group",
    "heading",
    "img",
    "insertion",
    "link",
    "list",
    "listbox",
    "listitem",
    "log",
    "main",
    "marquee",
    "math",
    "menu",
    "menubar",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "meter",
    "navigation",
    "none",
    "note",
    "option",
    "paragraph",
    "presentation",
    "progressbar",
    "radio",
    "radiogroup",
    "region",
    "row",
    "rowgroup",
    "rowheader",
    "scrollbar",
    "search",
    "searchbox",
    "separator",
    "slider",
    "spinbutton",
    "status",
    "strong",
    "subscript",
    "superscript",
    "switch",
    "tab",
    "table",
    "tablist",
    "tabpanel",
    "term",
    "textbox",
    "time",
    "timer",
    "toolbar",
    "tooltip",
    "tree",
    "treegrid",
    "treeitem",
]
"""Playwright get_by_role 接受的 ARIA 角色。"""

ARIA_ROLES: Final[frozenset[str]] = frozenset(get_args(AriaRole))


class Locator(DslModel):
    """頁面元素的定位器。

    範例::

        { role: button, name: 登入 }
        { label: 密碼 }
        { css: "tr", hasText: 訂單 123, within: { role: table, name: 訂單 } }
    """

    # ------------------------------------------------ 主要定位方式（恰好一種）
    test_id: NonEmptyStr | None = None
    """data-testid 屬性。內部系統若有測試用屬性，這是最穩定的方式。"""
    role: AriaRole | None = None
    """ARIA 角色，通常搭配 name。"""
    label: NonEmptyStr | None = None
    """表單元素的標籤文字。"""
    placeholder: NonEmptyStr | None = None
    """輸入框的提示文字。"""
    text: NonEmptyStr | None = None
    """元素的文字內容。"""
    alt_text: NonEmptyStr | None = None
    """圖片的替代文字。"""
    title: NonEmptyStr | None = None
    """title 屬性。"""
    css: NonEmptyStr | None = None
    """CSS 選擇器。避免使用自動產生的 id 或 class。"""
    xpath: NonEmptyStr | None = None
    """XPath。最後手段。"""

    # ------------------------------------------------ 修飾
    name: NonEmptyStr | None = None
    """role 的無障礙名稱，例如按鈕上的文字。只能搭配 role。"""
    exact: bool | None = None
    """文字是否要完全相符（預設為包含，且不分大小寫）。"""
    nth: int | None = None
    """符合多個元素時取第幾個：0 是第一個，-1 是最後一個。"""
    has_text: NonEmptyStr | None = None
    """只保留內含這段文字的元素。"""
    within: "Locator | None" = None
    """先找到這個外層元素，再在裡面找。"""
    fallback: list["Locator"] | None = Field(default=None, min_length=1)
    """主要定位失敗時依序嘗試的備用定位器（M2 執行、M5 自癒時使用）。"""

    @property
    def strategy(self) -> str:
        """使用的主要定位方式（DSL 欄位名稱）。"""
        return self._strategies()[0]

    def _strategies(self) -> list[str]:
        values = self.model_dump(by_alias=True, include=set(_STRATEGY_FIELDS))
        return [name for name in STRATEGIES if values.get(name) is not None]

    @model_validator(mode="after")
    def _check(self) -> Self:
        used = self._strategies()
        if not used:
            raise dsl_error("locator.no_strategy", choices=join_names(STRATEGIES))
        if len(used) > 1:
            raise dsl_error("locator.multiple_strategies", at=[used[1]], fields=join_names(used))
        strategy = used[0]
        if self.name is not None and strategy != "role":
            raise dsl_error("locator.name_requires_role", at=["name"], strategy=strategy)
        if self.exact is not None:
            if strategy not in _EXACT_STRATEGIES:
                raise dsl_error("locator.exact_not_supported", at=["exact"], strategy=strategy)
            if strategy == "role" and self.name is None:
                raise dsl_error("locator.exact_requires_name", at=["exact"])
        for index, item in enumerate(self.fallback or ()):
            if item.fallback is not None:
                raise dsl_error("locator.nested_fallback", at=["fallback", index, "fallback"])
        return self


_STRATEGY_FIELDS: Final = (
    "test_id",
    "role",
    "label",
    "placeholder",
    "text",
    "alt_text",
    "title",
    "css",
    "xpath",
)
"""STRATEGIES 對應的 Python 屬性名稱。"""
