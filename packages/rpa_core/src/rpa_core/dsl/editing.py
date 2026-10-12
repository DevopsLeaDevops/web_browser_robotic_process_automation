"""改寫場景檔的一部分，其他內容（包含註解）原樣保留。

管理 Portal 的入參、出參表單存檔時用 :func:`replace_contract`：只替換最上層的
``inputs:``、``outputs:`` 兩段，其他行一個字都不動。入參改名時，場景裡引用舊名稱的
``{{ inputs.舊名稱 }}`` 一併改成新名稱。

改寫後的內容還是要經過完整校驗（存成新版本時）；這裡不負責判斷內容對不對。
"""

import re
from collections.abc import Mapping, Sequence
from typing import Final

from rpa_core.dsl.yaml_writer import block

__all__ = ["INPUT_KEYS", "OUTPUT_KEYS", "find_block", "rename_input", "replace_contract"]

INPUT_KEYS: Final = (
    "type",
    "description",
    "default",
    "enum",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
)
"""寫出入參時欄位的順序。"""
OUTPUT_KEYS: Final = (
    "type",
    "description",
    "from",
    "enum",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
)
"""寫出出參時欄位的順序。"""

_TOP_LEVEL: Final = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:")
_INSERT_BEFORE: Final = (
    "secrets",
    "browser",
    "login",
    "defaults",
    "deadline",
    "steps",
    "verify",
    "script",
)
"""新增 inputs 或 outputs 段落時，放在這些段落之前（依場景檔慣用的順序）。"""


def _is_top_level(line: str) -> bool:
    """最上層的鍵（從第一欄開始、不是註解）。"""
    return bool(line) and not line[0].isspace() and not line.startswith("#")


def find_block(lines: Sequence[str], key: str) -> tuple[int, int] | None:
    """最上層 ``key:`` 段落的 (起始行, 結束行之後) 索引；找不到時回傳 None。

    段落包含後面縮排的行與夾在中間的空行；段落最後的空行、以及緊接著下一個鍵的第一欄註解
    （通常是在說明下一段）不算在內。
    """
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if (match := _TOP_LEVEL.match(line)) and match.group("key") == key
        ),
        None,
    )
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and not _is_top_level(lines[end]) and lines[end].strip() != "---":
        end += 1
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
        end -= 1
    return start, end


def _ordered(spec: Mapping[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    """依固定順序排列欄位；值為 None 的欄位不寫。"""
    ordered = {name: spec[name] for name in keys if spec.get(name) is not None}
    ordered |= {
        name: value for name, value in spec.items() if name not in keys and value is not None
    }
    return ordered


def _section(
    name: str, specs: Mapping[str, Mapping[str, object]], keys: tuple[str, ...]
) -> list[str]:
    return block({name: {item: _ordered(spec, keys) for item, spec in specs.items()}})


def rename_input(text: str, old: str, new: str) -> str:
    """把 ``inputs.舊名稱``、``inputs["舊名稱"]`` 的引用改成新名稱。"""
    pattern = re.compile(
        rf"(?<![\w.])inputs(?:\.{re.escape(old)}(?!\w)|\[\s*(['\"]){re.escape(old)}\1\s*\])"
    )

    def replace(match: re.Match[str]) -> str:
        quote = match.group(1)
        return f"inputs[{quote}{new}{quote}]" if quote else f"inputs.{new}"

    return pattern.sub(replace, text)


def _replace(lines: list[str], key: str, new: list[str], after: str | None = None) -> list[str]:
    found = find_block(lines, key)
    if found is not None:
        start, end = found
        if new:
            return lines[:start] + new + lines[end:]
        rest = lines[end:]
        # 移除整段後不要留下兩個連續的空行
        if start > 0 and not lines[start - 1].strip() and rest and not rest[0].strip():
            rest = rest[1:]
        return lines[:start] + rest
    if not new:
        return lines
    position: int | None = None
    if after is not None and (previous := find_block(lines, after)) is not None:
        position = previous[1]
    if position is None:
        for name in _INSERT_BEFORE:
            if (other := find_block(lines, name)) is not None:
                position = other[0]
                break
    if position is None:
        position = len(lines)
        while position > 0 and not lines[position - 1].strip():
            position -= 1
    # 前後各留一個空行，和其他段落分開
    before = [""] if position > 0 and lines[position - 1].strip() else []
    tail = [""] if position < len(lines) and lines[position].strip() else []
    return lines[:position] + before + new + tail + lines[position:]


def replace_contract(
    text: str,
    *,
    inputs: Mapping[str, Mapping[str, object]],
    outputs: Mapping[str, Mapping[str, object]],
    renames: Mapping[str, str] | None = None,
) -> str:
    """替換場景檔的 inputs 與 outputs 段落；沒有任何項目時移除該段落。

    ``inputs``、``outputs`` 是「名稱 → DSL 寫法的欄位」（camelCase，例如 minLength、from）。
    ``renames`` 是入參的「舊名稱 → 新名稱」，場景其他地方的引用一併改名。
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    ending = text.endswith(("\n", "\r\n"))
    for old, new in (renames or {}).items():
        if old != new:
            text = rename_input(text, old, new)
    lines = text.splitlines()
    lines = _replace(lines, "inputs", _section("inputs", inputs, INPUT_KEYS) if inputs else [])
    lines = _replace(
        lines,
        "outputs",
        _section("outputs", outputs, OUTPUT_KEYS) if outputs else [],
        after="inputs",
    )
    result = newline.join(lines)
    return result + newline if ending or not result else result
