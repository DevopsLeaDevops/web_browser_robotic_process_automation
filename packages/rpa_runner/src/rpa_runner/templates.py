"""``{{ }}`` 求值：Jinja2 沙箱環境，只能讀取 inputs、secrets、facts、env。

- 一般欄位代入後一律是文字。
- 整個值只有一個 ``{{ }}`` 時（例如出參的 ``from``），用 :func:`render_native` 保留原本的型別，
  清單、物件、數字不會被轉成文字。
- 引用不存在的值直接報錯（StrictUndefined），不會默默變成空字串。
"""

import re
from collections.abc import Mapping
from typing import Final

from jinja2 import StrictUndefined, TemplateError, Undefined
from jinja2.sandbox import SandboxedEnvironment

__all__ = ["Context", "TemplateEvaluationError", "render", "render_native", "render_tree"]

type Context = Mapping[str, object]
"""求值時可用的變數：inputs、secrets、facts、env。"""

_ENV: Final = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
_SINGLE: Final = re.compile(r"^\s*\{\{(?P<expr>.*?)\}\}\s*$", re.DOTALL)


class TemplateEvaluationError(Exception):
    """``{{ }}`` 無法求值，例如引用的值不存在。"""


def render(text: str, context: Context) -> str:
    """代入後的文字；沒有 ``{{`` 或 ``{%`` 時原樣回傳。"""
    if "{{" not in text and "{%" not in text:
        return text
    try:
        return _ENV.from_string(text).render(context)
    except TemplateError as error:
        raise TemplateEvaluationError(error.message or str(error)) from error


def render_native(text: str, context: Context) -> object:
    """整個值只有一個 ``{{ }}`` 時回傳運算結果本身；否則同 render。"""
    match = _SINGLE.match(text)
    if match is None or "{{" in match.group("expr"):
        return render(text, context)
    try:
        value: object = _ENV.compile_expression(match.group("expr"), undefined_to_none=False)(
            context
        )
    except TemplateError as error:
        raise TemplateEvaluationError(error.message or str(error)) from error
    if isinstance(value, Undefined):
        # 只取值、沒有進一步運算時，StrictUndefined 不會自己拋錯；轉成文字時才會
        try:
            str(value)
        except TemplateError as error:
            raise TemplateEvaluationError(error.message or str(error)) from error
    return value


def render_tree(value: object, context: Context, *, skip: frozenset[str] = frozenset()) -> object:
    """把資料結構中的每個字串都代入；``skip`` 中的鍵（例如 name）原樣保留。"""
    if isinstance(value, str):
        return render(value, context)
    if isinstance(value, Mapping):
        items: Mapping[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        return {
            key: item if key in skip else render_tree(item, context, skip=skip)
            for key, item in items.items()
        }
    if isinstance(value, list):
        elements: list[object] = value  # pyright: ignore[reportUnknownVariableType]
        return [render_tree(item, context, skip=skip) for item in elements]
    return value
