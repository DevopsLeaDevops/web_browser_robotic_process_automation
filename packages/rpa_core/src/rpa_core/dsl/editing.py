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

__all__ = [
    "INPUT_KEYS",
    "OUTPUT_KEYS",
    "SECTION_KEYS",
    "append_items",
    "contract_section",
    "find_block",
    "rename_input",
    "replace_contract",
    "replace_section",
    "section_text",
]

SECTION_KEYS: Final = ("inputs", "outputs", "steps", "verify")
"""可以單獨編輯的段落：入參、出參、自動化步驟、獨立斷言。"""

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
    """最上層的鍵（從第一欄開始、不是註解）。

    從第一欄開始的 ``- `` 是上一個鍵的清單項目（YAML 允許清單和鍵對齊），不算新的鍵。
    """
    if not line or line[0].isspace() or line.startswith("#"):
        return False
    return not (line.startswith("-") and (len(line) == 1 or line[1] == " "))


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


def contract_section(key: str, specs: Mapping[str, Mapping[str, object]]) -> str:
    """入參或出參段落的原文（表格切換成 YAML 時用）；沒有任何項目時是空字串。"""
    if not specs:
        return ""
    return "\n".join(_section(key, specs, INPUT_KEYS if key == "inputs" else OUTPUT_KEYS))


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


def _text(lines: Sequence[str], newline: str, ending: bool) -> str:
    result = newline.join(lines)
    return result + newline if ending or not result else result


def section_text(text: str, key: str) -> str:
    """最上層 ``key:`` 段落的原文（含 ``key:`` 那一行，不含最後的換行）；沒有這段時回傳空字串。"""
    lines = text.splitlines()
    found = find_block(lines, key)
    if found is None:
        return ""
    start, end = found
    return "\n".join(lines[start:end])


_AFTER: Final = {"outputs": "inputs", "verify": "steps"}
"""新增段落時要接在哪一段後面（找不到時依 _INSERT_BEFORE 的順序）。"""


def replace_section(text: str, key: str, section: str) -> str:
    """把最上層 ``key:`` 段落換成 ``section``（它自己的原文，含 ``key:`` 那一行）。

    ``section`` 是空白時移除整段。其他行一個字都不動；內容對不對由之後的完整校驗判斷。
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    ending = text.endswith(("\n", "\r\n"))
    new = section.strip("\n").splitlines() if section.strip() else []
    lines = _replace(text.splitlines(), key, new, after=_AFTER.get(key))
    return _text(lines, newline, ending)


def _item_indent(lines: Sequence[str]) -> int | None:
    """段落裡第一個項目的縮排（略過空行與註解）。"""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return len(line) - len(line.lstrip(" "))
    return None


def _shift(line: str, columns: int) -> str:
    """整行往右（正數）或往左（負數，最多移掉行首的空白）平移。"""
    if not line.strip():
        return line
    if columns >= 0:
        return " " * columns + line
    leading = len(line) - len(line.lstrip(" "))
    return line[min(-columns, leading) :]


def append_items(text: str, key: str, items: Sequence[str], *, whole: Sequence[str]) -> str:
    """在最上層 ``key:`` 段落的最後加上項目（例如步驟、入參），原有內容一個字都不動。

    ``items`` 是以兩格縮排寫好的項目原文（``block()`` 的輸出去掉第一行）；原段落用別的縮排時
    整體平移成一樣的縮排。段落寫成一行（例如 ``secrets: [A, B]``）或還沒有這段時，改用
    ``whole``（合併後整段的原文）取代。
    """
    if not items:
        return text
    newline = "\r\n" if "\r\n" in text else "\n"
    ending = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    found = find_block(lines, key)
    inline = found is not None and lines[found[0]].split(":", 1)[1].split("#", 1)[0].strip()
    if found is None or inline:
        return _text(_replace(lines, key, list(whole), after=_AFTER.get(key)), newline, ending)
    start, end = found
    indent = _item_indent(lines[start + 1 : end])
    shift = (indent if indent is not None else 2) - 2
    moved = [_shift(item, shift) for item in items]
    return _text([*lines[:end], *moved, *lines[end:]], newline, ending)


def replace_contract(
    text: str,
    *,
    inputs: Mapping[str, Mapping[str, object]] | None,
    outputs: Mapping[str, Mapping[str, object]] | None,
    renames: Mapping[str, str] | None = None,
) -> str:
    """替換場景檔的 inputs 與 outputs 段落；沒有任何項目時移除該段落，None 時不動那一段。

    ``inputs``、``outputs`` 是「名稱 → DSL 寫法的欄位」（camelCase，例如 minLength、from）。
    ``renames`` 是入參的「舊名稱 → 新名稱」，場景其他地方的引用一併改名。
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    ending = text.endswith(("\n", "\r\n"))
    for old, new in (renames or {}).items():
        if old != new:
            text = rename_input(text, old, new)
    lines = text.splitlines()
    if inputs is not None:
        lines = _replace(lines, "inputs", _section("inputs", inputs, INPUT_KEYS) if inputs else [])
    if outputs is not None:
        lines = _replace(
            lines,
            "outputs",
            _section("outputs", outputs, OUTPUT_KEYS) if outputs else [],
            after="inputs",
        )
    return _text(lines, newline, ending)
