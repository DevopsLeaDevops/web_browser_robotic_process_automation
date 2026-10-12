"""產生場景 YAML 的片段：錄製稿轉換與入參、出參表單編輯共用。

只產生 :mod:`rpa_core.dsl.yaml_loader` 讀得回來、而且值不變的寫法：

- 字串能寫成純量（不加引號）時就不加，例如 ``name: 建立紀錄``；可能被讀成其他型別
  （``true``、``123``、``null``）、含有 YAML 特殊字元或 ``{{ }}`` 時改用雙引號。
  雙引號字串用 JSON 的跳脫規則，JSON 字串也是合法的 YAML。
- 定位器這類小物件寫成一行的流式寫法：``{ role: button, name: 登入 }``。
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

__all__ = ["block", "flow", "key", "scalar"]

# 與 yaml_loader 相同的 YAML 1.2 core 規則：符合的文字會被讀成 null、布林或數字
_NULL: Final = re.compile(r"^(?:~|null|Null|NULL|)$")
_BOOL: Final = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT: Final = re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT: Final = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)
_FIRST_EXTRA: Final = frozenset("_/.")
_REST_EXTRA: Final = frozenset("_/.- ()")
_UNSAFE: Final = frozenset("  ﻿ ")


def _plain(text: str) -> bool:
    """這段文字能不能不加引號（在區塊與流式寫法中都讀回同一個字串）。"""
    if not text or text != text.strip() or _UNSAFE.intersection(text):
        return False
    if _NULL.match(text) or _BOOL.match(text) or _INT.match(text) or _FLOAT.match(text):
        return False
    first, rest = text[0], text[1:]
    if not (first.isalnum() or first in _FIRST_EXTRA):
        return False
    return all(char.isalnum() or char in _REST_EXTRA for char in rest)


def scalar(value: object) -> str:
    """一個純量值的 YAML 寫法。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("只能寫出有限的數字")
        return repr(value)
    text = str(value)
    return text if _plain(text) else json.dumps(text, ensure_ascii=False)


def key(name: str) -> str:
    """物件的鍵；與值的規則相同（例如鍵 ``on`` 不必加引號，``123`` 要加）。"""
    return scalar(name)


def flow(value: object) -> str:
    """一行的流式寫法：``{ a: 1, b: [x, y] }``。"""
    if isinstance(value, Mapping):
        items = cast("Mapping[str, object]", value)
        if not items:
            return "{}"
        inner = ", ".join(f"{key(name)}: {flow(item)}" for name, item in items.items())
        return "{ " + inner + " }"
    if isinstance(value, list | tuple):
        elements = cast("Sequence[object]", value)
        return "[" + ", ".join(flow(item) for item in elements) + "]"
    return scalar(value)


def _scalars(value: Sequence[object]) -> bool:
    """只有純量的清單（例如 enum）寫成一行：``[a, b]``。"""
    return all(not isinstance(item, Mapping | list | tuple) for item in value)


def _inline(value: object) -> bool:
    """寫成一行的值：純量，或只有純量的清單。"""
    if isinstance(value, Mapping):
        return False
    if isinstance(value, list | tuple):
        return _scalars(cast("Sequence[object]", value))
    return True


def block(
    value: Mapping[str, object], indent: int = 0, *, flow_keys: frozenset[str] = frozenset()
) -> list[str]:
    """區塊寫法的物件，一行一個鍵；``flow_keys`` 中的鍵（例如 target）寫成一行的流式寫法。

    只有純量的清單寫成一行；清單裡的物件寫成 ``- 鍵: 值`` 接著縮排兩格的其他鍵。
    """
    pad = " " * indent
    lines: list[str] = []
    for name, item in value.items():
        if name in flow_keys or _inline(item):
            lines.append(f"{pad}{key(name)}: {flow(item)}")
        elif isinstance(item, Mapping):
            nested = cast("Mapping[str, object]", item)
            if not nested:
                lines.append(f"{pad}{key(name)}: {{}}")
                continue
            lines.append(f"{pad}{key(name)}:")
            lines += block(nested, indent + 2, flow_keys=flow_keys)
        else:
            elements = cast("Sequence[object]", item)
            if not elements:
                lines.append(f"{pad}{key(name)}: []")
                continue
            lines.append(f"{pad}{key(name)}:")
            for element in elements:
                if isinstance(element, Mapping):
                    nested = block(
                        cast("Mapping[str, object]", element), indent + 4, flow_keys=flow_keys
                    )
                    lines.append(f"{pad}  - {nested[0].lstrip()}")
                    lines += nested[1:]
                else:
                    lines.append(f"{pad}  - {flow(element)}")
    return lines
