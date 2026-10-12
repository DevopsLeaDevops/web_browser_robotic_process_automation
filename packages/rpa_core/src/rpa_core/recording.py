"""錄製稿轉換：Playwright codegen 產生的 Python → 場景 DSL 草稿（M4）。

錄製稿只當來源，永遠不會直接發布；轉換結果是一個新的草稿版本，之後一樣要驗證才能發布。

- 支援 codegen 的同步、非同步（await）與 pytest 三種寫法，只看操作頁面的那幾行。
- 轉得了的寫法：goto、click／dblclick、fill、press、select_option、check／uncheck，
  expect 的 to_be_visible、to_contain_text、to_have_text、to_have_value、to_be_checked 等，
  以及 get_by_role／label／placeholder／text／alt_text／title／test_id、locator（CSS、XPath）、
  first／last／nth、filter(has_text=…) 與串接（外層 → within）。
- 轉不了的行（例如 hover、上傳檔案、iframe、新分頁）以註解留在草稿裡，並列在警告中。
- **自動參數化**：每個 fill 的值變成一個入參，預設值是錄到的值，名稱取自欄位的英數名稱
  （test id、CSS 的 #id 等），沒有英數名稱時叫 field、field_2…，欄位的標籤寫在入參說明。
- **密碼不落地**：看起來是密碼欄位的輸入改成 Secret 引用，原始錄製稿裡的值也遮罩成 ``***``。
- 第一個網址的來源（例如 http://127.0.0.1:8765）成為 browser.baseUrl，同來源的 goto 改寫成相對路徑。
"""

import ast
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, cast
from urllib.parse import urlsplit

from rpa_core.dsl.fields import catalog
from rpa_core.dsl.validation import validate_text
from rpa_core.dsl.yaml_writer import block, scalar

__all__ = [
    "MASK",
    "PASSWORD_WORDS",
    "Conversion",
    "ConversionError",
    "ConversionWarning",
    "convert_recording",
    "mask_source",
]

PASSWORD_WORDS: Final = ("password", "passwd", "passcode", "pwd", "密碼", "密码", "口令")
"""欄位的標籤、提示文字、名稱或選擇器含有這些字（不分大小寫）時，視為密碼欄位。"""

MASK: Final = "***"

type Span = tuple[int, int, int, int]
"""原始碼中的一段：(起始行, 起始欄, 結束行, 結束欄)；行從 1 開始，欄以 UTF-8 位元組計（同 ast）。"""

_IDENTIFIER: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_REGEX_META: Final = re.compile(r"[.^$*+?{}\[\]\\|()]")
_SIMPLE_KWARGS: Final = frozenset({"name", "exact"})
_PAGE_EXPECTS: Final = {"to_have_url": "url", "to_have_title": "title"}
_TYPING: Final = frozenset({"fill", "type", "press_sequentially"})
_IGNORED_PAGE_CALLS: Final = frozenset(
    {"close", "once", "on", "set_default_timeout", "set_default_navigation_timeout", "pause"}
)
_STRATEGY_METHODS: Final = {
    "get_by_label": "label",
    "get_by_placeholder": "placeholder",
    "get_by_text": "text",
    "get_by_alt_text": "altText",
    "get_by_title": "title",
}
_ELEMENT_EXPECTS: Final = {
    "to_be_visible": ("state", "visible"),
    "not_to_be_visible": ("state", "hidden"),
    "to_be_hidden": ("state", "hidden"),
    "to_be_checked": ("state", "checked"),
    "not_to_be_checked": ("state", "unchecked"),
    "to_be_enabled": ("state", "enabled"),
    "to_be_disabled": ("state", "disabled"),
    "to_be_editable": ("state", "editable"),
}


class ConversionError(Exception):
    """錄製稿無法轉換（例如不是 Python、或沒有任何可以轉換的操作）。"""


@dataclass(frozen=True, slots=True)
class ConversionWarning:
    """轉換時的一個提醒：錄製稿的哪一行、說明、遮罩後的那一行原文。"""

    line: int
    message: str
    source: str = ""

    def to_json(self) -> dict[str, object]:
        return {"line": self.line, "message": self.message, "source": self.source}


@dataclass(frozen=True, slots=True)
class Conversion:
    """轉換結果。"""

    scenario: str
    """DSL 草稿（YAML）；已經通過校驗。"""
    masked_source: str
    """遮罩過密碼的原始錄製稿，可以保存。"""
    warnings: tuple[ConversionWarning, ...]
    inputs: tuple[str, ...]
    """自動產生的入參名稱。"""
    secrets: tuple[str, ...]
    """密碼欄位改成的 Secret 名稱；值要另外設定。"""
    steps: int

    def to_json(self) -> dict[str, object]:
        return {
            "warnings": [warning.to_json() for warning in self.warnings],
            "inputs": list(self.inputs),
            "secrets": list(self.secrets),
            "steps": self.steps,
        }


# ---------------------------------------------------------------- 呼叫鏈


@dataclass(frozen=True, slots=True)
class _Segment:
    """呼叫鏈的一段：``.名稱`` 或 ``.名稱(引數)``。"""

    name: str
    call: bool = False
    args: tuple[ast.expr, ...] = ()
    kwargs: Mapping[str, ast.expr] = field(default_factory=dict[str, ast.expr])


def _chain(node: ast.expr) -> tuple[ast.expr, list[_Segment]] | None:
    """``page.get_by_role("button").click()`` → (page, [get_by_role(...), click()])。"""
    segments: list[_Segment] = []
    current = node
    while True:
        if isinstance(current, ast.Await):
            current = current.value
        elif isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute):
            kwargs = {item.arg: item.value for item in current.keywords if item.arg is not None}
            segments.append(_Segment(current.func.attr, True, tuple(current.args), kwargs))
            current = current.func.value
        elif isinstance(current, ast.Attribute):
            segments.append(_Segment(current.attr))
            current = current.value
        else:
            break
    segments.reverse()
    return (current, segments) if segments else None


def _string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal(node: ast.expr) -> object:
    """常數、清單；其他寫法回傳 ``...``（Ellipsis）代表轉不了。"""
    try:
        return cast("object", ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return ...


def _regex_text(node: ast.expr) -> tuple[str, bool] | None:
    """只是比對固定文字的正規表示式（``re.compile(r"^文字$")``）→ (文字, 是否要完全相符)。"""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
        and node.args
    ):
        return None
    pattern = _string(node.args[0])
    if pattern is None:
        return None
    exact = pattern.startswith("^") and pattern.endswith("$") and not pattern.endswith("\\$")
    body = pattern.removeprefix("^").removesuffix("$") if exact else pattern
    if _REGEX_META.search(re.sub(r"\\.", "", body)):
        return None
    text = re.sub(r"\\(.)", r"\1", body)
    return (text, exact) if text else None


class _UnsupportedError(Exception):
    """這一行轉不了；message 是說明（目前語言）。"""

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.message = catalog(f"recording.unsupported.{key}", **params)


# ---------------------------------------------------------------- 定位器


def _selector(text: str) -> dict[str, object]:
    """``locator("…")`` 的選擇器 → css 或 xpath。"""
    if text.startswith("xpath="):
        return {"xpath": text.removeprefix("xpath=")}
    if text.startswith(("//", "..", "(//")):
        return {"xpath": text}
    if text.startswith("css="):
        return {"css": text.removeprefix("css=")}
    if text.startswith(("internal:", "text=")) or ">>" in text:
        raise _UnsupportedError("selector", value=text)
    return {"css": text}


def _strategy(segment: _Segment) -> dict[str, object]:
    """一個取得元素的方法 → 定位器的主要方式。"""
    name = segment.name
    extra = set(segment.kwargs) - _SIMPLE_KWARGS
    if extra:
        raise _UnsupportedError("options", name=name, options=", ".join(sorted(extra)))
    exact = _literal(segment.kwargs["exact"]) is True if "exact" in segment.kwargs else False
    first = segment.args[0] if segment.args else None
    if name == "get_by_role":
        role = _string(first)
        if role is None:
            raise _UnsupportedError("arguments", name=name)
        found: dict[str, object] = {"role": role}
        if "name" in segment.kwargs:
            text = _string(segment.kwargs["name"])
            if text is None:
                regex = _regex_text(segment.kwargs["name"])
                if regex is None:
                    raise _UnsupportedError("regex", name=name)
                text, exact = regex[0], regex[1] or exact
            found["name"] = text
        if exact and "name" in found:
            found["exact"] = True
        return found
    if name == "get_by_test_id":
        value = _string(first)
        if value is None:
            raise _UnsupportedError("arguments", name=name)
        return {"testId": value}
    if name in _STRATEGY_METHODS:
        if first is None:
            raise _UnsupportedError("arguments", name=name)
        text = _string(first)
        if text is None:
            regex = _regex_text(first)
            if regex is None:
                raise _UnsupportedError("regex", name=name)
            text, exact = regex[0], regex[1] or exact
        found = {_STRATEGY_METHODS[name]: text}
        if exact:
            found["exact"] = True
        return found
    if name == "locator":
        value = _string(first)
        if value is None or segment.kwargs or len(segment.args) != 1:
            raise _UnsupportedError("arguments", name=name)
        return _selector(value)
    if name in ("frame_locator", "content_frame"):
        raise _UnsupportedError("frame")
    raise _UnsupportedError("method", name=name)


def _filter(current: dict[str, object], segment: _Segment) -> list[str]:
    """``.filter(has_text=…)``；回傳要附加的警告。"""
    if "nth" in current or "hasText" in current or segment.args:
        raise _UnsupportedError("filter")
    if set(segment.kwargs) != {"has_text"}:
        raise _UnsupportedError("filter")
    value = segment.kwargs["has_text"]
    text = _string(value)
    if text is not None:
        if not text:
            raise _UnsupportedError("filter")
        current["hasText"] = text
        return []
    regex = _regex_text(value)
    if regex is None:
        raise _UnsupportedError("filter")
    text, exact = regex
    css = current.get("css")
    if exact and isinstance(css, str) and set(current) == {"css"}:
        # 「整段文字就是…」：用 Playwright CSS 的 :text-is()，比 hasText（包含）精確
        current["css"] = f"{css}:text-is({json.dumps(text, ensure_ascii=False)})"
        return []
    current["hasText"] = text
    return [catalog("recording.loose_filter", text=text)] if exact else []


def _locator(segments: Sequence[_Segment]) -> tuple[dict[str, object], list[str]]:
    """定位器的呼叫鏈 → (DSL 定位器（camelCase 欄位）, 警告)。"""
    current: dict[str, object] | None = None
    notes: list[str] = []
    for segment in segments:
        name = segment.name
        if name in ("first", "last") and not segment.call:
            if current is None or "nth" in current:
                raise _UnsupportedError("chain")
            current["nth"] = 0 if name == "first" else -1
        elif name == "content_frame":
            raise _UnsupportedError("frame")
        elif not segment.call:
            raise _UnsupportedError("chain")
        elif name == "nth":
            value = _literal(segment.args[0]) if segment.args else ...
            if current is None or "nth" in current or type(value) is not int:
                raise _UnsupportedError("chain")
            current["nth"] = value
        elif name == "filter":
            if current is None:
                raise _UnsupportedError("filter")
            notes += _filter(current, segment)
        else:
            found = _strategy(segment)
            if current is not None:
                found["within"] = current
            current = found
    if current is None:
        raise _UnsupportedError("chain")
    return current, notes


# ---------------------------------------------------------------- 名稱


def _describe(locator: Mapping[str, object]) -> str:
    """給人看的元素說明，用在步驟名稱與入參說明。"""
    for name in ("name", "label", "placeholder", "text", "altText", "title", "testId"):
        value = locator.get(name)
        if isinstance(value, str) and value:
            return value
    for name in ("css", "xpath", "role"):
        value = locator.get(name)
        if isinstance(value, str):
            return value
    return "?"


def _words(locator: Mapping[str, object]) -> list[str]:
    """定位器裡可以拿來取名、判斷是不是密碼欄位的文字（不含外層）。"""
    values: list[str] = []
    for name in ("testId", "label", "placeholder", "name", "text", "title", "css", "xpath"):
        value = locator.get(name)
        if isinstance(value, str):
            values.append(value)
    return values


def _is_password(locator: Mapping[str, object]) -> bool:
    text = " ".join(_words(locator)).lower()
    return any(word in text for word in PASSWORD_WORDS)


def _identifier_from(text: str) -> str | None:
    """英數文字 → 入參名稱（snake_case）；沒有英數字時回傳 None。"""
    match = re.search(r"#([A-Za-z][\w-]*)|\[name=['\"]?([\w-]+)", text)
    if match:
        text = match.group(1) or match.group(2)
    elif not re.fullmatch(r"[\w\s-]+", text, flags=re.ASCII):
        return None
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return None
    name = "_".join(word.lower() for word in words)[:40].strip("_")
    if name[:1].isdigit():
        name = f"field_{name}"
    return name if _IDENTIFIER.fullmatch(name) else None


def _unique(name: str, used: set[str]) -> str:
    candidate, number = name, 2
    while candidate in used:
        candidate = f"{name}_{number}"
        number += 1
    used.add(candidate)
    return candidate


def _secret_name(scene_id: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", scene_id.upper()).strip("_") or "SCENE"
    if not base[0].isalpha():
        base = f"S_{base}"
    return _unique(f"{base[:50]}_PASSWORD", used)


# ---------------------------------------------------------------- 轉換


@dataclass(slots=True)
class _Step:
    action: str
    fields: dict[str, object]
    name: str


@dataclass(slots=True)
class _State:
    scene_id: str
    origin: str | None
    source: str
    masked: set[Span] = field(default_factory=set[Span])
    entries: list[_Step | ConversionWarning] = field(
        default_factory=list[_Step | ConversionWarning]
    )
    warnings: list[ConversionWarning] = field(default_factory=list[ConversionWarning])
    inputs: dict[str, dict[str, object]] = field(default_factory=dict[str, dict[str, object]])
    secrets: list[str] = field(default_factory=list[str])
    used_inputs: set[str] = field(default_factory=set[str])
    used_secrets: set[str] = field(default_factory=set[str])
    other_pages: set[str] = field(default_factory=set[str])

    def warn(self, node: ast.AST, message: str) -> None:
        line = cast("int", getattr(node, "lineno", 0))
        masked = mask_source(self.source, sorted(self.masked)).splitlines()
        text = masked[line - 1].strip() if 1 <= line <= len(masked) else ""
        warning = ConversionWarning(line, message, text)
        self.warnings.append(warning)
        self.entries.append(warning)

    def add(self, action: str, fields: dict[str, object], target: str = "") -> None:
        params = {"target": target, "url": fields.get("url", ""), "key": fields.get("key", "")}
        key = "uncheck" if action == "check" and fields.get("checked") is False else action
        self.entries.append(_Step(action, fields, catalog(f"recording.step.{key}", **params)))

    def relative(self, url: str) -> str:
        if self.origin is None:
            return url
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != self.origin:
            return url
        path = parts.path or "/"
        if parts.query:
            path += f"?{parts.query}"
        if parts.fragment:
            path += f"#{parts.fragment}"
        return path

    @property
    def steps(self) -> list[_Step]:
        return [entry for entry in self.entries if isinstance(entry, _Step)]


def _span(node: ast.expr) -> Span:
    return (node.lineno, node.col_offset, node.end_lineno or node.lineno, node.end_col_offset or 0)


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _statements(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """依原本的順序走過所有敘述，包含函式與 with 區塊裡面的。"""
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _statements(statement.body)
        elif isinstance(statement, ast.With | ast.AsyncWith):
            yield statement
            yield from _statements(statement.body)
        else:
            yield statement


def _first_goto(tree: ast.Module) -> str | None:
    for statement in _statements(tree.body):
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "goto"
                and node.args
            ):
                return _string(node.args[0])
    return None


def _assignment(state: _State, statement: ast.Assign | ast.AnnAssign) -> None:
    """記下其他分頁的變數名稱：``page1 = context.new_page()``、``page1 = page1_info.value``。"""
    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
    found = _chain(statement.value) if statement.value is not None else None
    if found is None:
        return
    method = found[1][-1].name
    for target in targets:
        if not isinstance(target, ast.Name) or target.id == "page":
            continue
        if method in ("new_page", "value"):
            state.other_pages.add(target.id)


def _with(state: _State, statement: ast.With | ast.AsyncWith) -> None:
    """``with page.expect_popup() as page1_info:`` 這類區塊：裡面的操作照常轉換，新分頁轉不了。"""
    for item in statement.items:
        found = _chain(item.context_expr)
        if found is None:
            continue
        method = found[1][-1].name
        if method == "expect_popup":
            state.warn(statement, catalog("recording.unsupported.popup"))
        elif method == "expect_download":
            state.warn(statement, catalog("recording.unsupported.download"))


def _mask_typing(state: _State, segments: Sequence[_Segment]) -> None:
    """輸入到密碼欄位的文字一律遮罩（不論這一行轉不轉得了）。"""
    action = segments[-1]
    if action.name not in _TYPING or not action.call:
        return
    words = [
        value
        for segment in segments[:-1]
        for value in (*(_string(arg) for arg in segment.args), _string(segment.kwargs.get("name")))
        if value
    ]
    if not any(word in " ".join(words).lower() for word in PASSWORD_WORDS):
        return
    for argument in action.args:
        if _string(argument) is not None:
            state.masked.add(_span(argument))


def _expression(state: _State, statement: ast.Expr) -> None:
    node = statement.value
    if isinstance(node, ast.Await):
        node = node.value
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return
    inner = node.func.value
    if (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "expect"
    ):
        _assertion(state, statement, node, inner)
        return
    found = _chain(node)
    if found is None:
        return
    subject, segments = found
    if not isinstance(subject, ast.Name) or subject.id in ("context", "browser", "playwright"):
        return
    _mask_typing(state, segments)
    if subject.id in state.other_pages:
        state.warn(statement, catalog("recording.unsupported.other_page", page=subject.id))
    elif subject.id == "page":
        _action(state, statement, segments)


def _page_action(state: _State, statement: ast.Expr, segments: Sequence[_Segment]) -> None:
    """直接對頁面的操作：goto、wait_for_url、keyboard.press。"""
    action = segments[-1]
    name = action.name
    if segments[0].name == "keyboard" and len(segments) == 2 and name == "press":
        key = _string(action.args[0]) if action.args else None
        if key is None:
            state.warn(statement, catalog("recording.unsupported.arguments", name=name))
            return
        state.add("press", {"key": key}, "")
        return
    if segments[0].name in ("keyboard", "mouse"):
        state.warn(
            statement, catalog("recording.unsupported.method", name=f"{segments[0].name}.{name}")
        )
        return
    url = _string(action.args[0]) if action.args else None
    if name == "goto" and url is not None:
        relative = state.relative(url)
        state.add("goto", {"url": relative})
    elif name == "wait_for_url" and url is not None:
        state.add("waitFor", {"url": state.relative(url)})
    elif name in _IGNORED_PAGE_CALLS:
        return
    elif name in ("goto", "wait_for_url"):
        state.warn(statement, catalog("recording.unsupported.arguments", name=name))
    else:
        state.warn(statement, catalog("recording.unsupported.method", name=name))


def _action(state: _State, statement: ast.Expr, segments: list[_Segment]) -> None:
    action = segments[-1]
    if not action.call:
        return
    if len(segments) == 1 or segments[0].name in ("keyboard", "mouse"):
        _page_action(state, statement, segments)
        return
    try:
        target, notes = _locator(segments[:-1])
    except _UnsupportedError as problem:
        state.warn(statement, problem.message)
        return
    for note in notes:
        state.warn(statement, note)
    described = _describe(target)
    name = action.name
    first = action.args[0] if action.args else None
    match name:
        case "click" | "dblclick":
            _click(state, statement, action, target, described)
        case "fill" | "type" | "press_sequentially" | "clear":
            text = "" if name == "clear" else _string(first)
            if text is None:
                state.warn(statement, catalog("recording.unsupported.arguments", name=name))
                return
            _fill(state, target, text, described)
        case "press":
            key = _string(first)
            if key is None:
                state.warn(statement, catalog("recording.unsupported.arguments", name=name))
                return
            state.add("press", {"target": target, "key": key}, described)
        case "select_option":
            value = _literal(first) if first is not None else ...
            items = cast("list[object]", value) if isinstance(value, list) else None
            if isinstance(value, str) or (items and all(isinstance(item, str) for item in items)):
                state.add("select", {"target": target, "option": value}, described)
            else:
                state.warn(statement, catalog("recording.unsupported.arguments", name=name))
        case "check" | "uncheck":
            fields: dict[str, object] = {"target": target}
            if name == "uncheck":
                fields["checked"] = False
            state.add("check", fields, described)
        case "hover":
            state.warn(statement, catalog("recording.unsupported.hover"))
        case "set_input_files":
            state.warn(statement, catalog("recording.unsupported.upload"))
        case _:
            state.warn(statement, catalog("recording.unsupported.method", name=name))


def _click(
    state: _State,
    statement: ast.Expr,
    action: _Segment,
    target: dict[str, object],
    described: str,
) -> None:
    fields: dict[str, object] = {"target": target}
    button = action.kwargs.get("button")
    if button is not None:
        value = _literal(button)
        if value not in ("left", "right", "middle"):
            state.warn(statement, catalog("recording.unsupported.arguments", name=action.name))
            return
        if value != "left":
            fields["button"] = value
    if action.name == "dblclick":
        fields["clickCount"] = 2
    modifiers = action.kwargs.get("modifiers")
    if modifiers is not None:
        value = _literal(modifiers)
        if not isinstance(value, list):
            state.warn(statement, catalog("recording.unsupported.arguments", name=action.name))
            return
        fields["modifiers"] = cast("list[object]", value)
    if "position" in action.kwargs:
        state.warn(statement, catalog("recording.dropped_position"))
    state.add("click", fields, described)


def _fill(state: _State, target: dict[str, object], text: str, described: str) -> None:
    # codegen 常常先錄一次點擊、再錄 fill；點的是同一個欄位而且沒有其他選項時，點擊沒有意義
    last = state.entries[-1] if state.entries else None
    if isinstance(last, _Step) and last.action == "click" and last.fields == {"target": target}:
        state.entries.pop()
    if _is_password(target) and text:
        secret = _secret_name(state.scene_id, state.used_secrets)
        state.secrets.append(secret)
        state.add("fill", {"target": target, "value": f"{{{{ secrets.{secret} }}}}"}, described)
        return
    if not text:
        state.add("fill", {"target": target, "value": ""}, described)
        return
    candidates = (_identifier_from(word) for word in _words(target))
    name = _unique(next((item for item in candidates if item), None) or "field", state.used_inputs)
    state.inputs[name] = {"type": "string", "description": _describe(target), "default": text}
    state.add("fill", {"target": target, "value": f"{{{{ inputs.{name} }}}}"}, described)


def _assertion(state: _State, statement: ast.Expr, node: ast.Call, inner: ast.Call) -> None:
    """``expect(…).to_xxx(…)`` → expect 步驟。"""
    method = cast("ast.Attribute", node.func).attr
    if not inner.args:
        return
    found = _chain(inner.args[0])
    subject = inner.args[0] if found is None else found[0]
    if not isinstance(subject, ast.Name):
        return
    if subject.id in state.other_pages:
        state.warn(statement, catalog("recording.unsupported.other_page", page=subject.id))
        return
    if subject.id != "page":
        return
    value = _string(node.args[0]) if node.args else None
    if found is None:
        field_name = _PAGE_EXPECTS.get(method)
        if field_name is None or value is None:
            state.warn(statement, catalog("recording.unsupported.assertion", name=method))
            return
        if field_name == "url":
            value = state.relative(value)
        state.add("expect", {field_name: value, "match": "equals"}, value)
        return
    try:
        target, notes = _locator(found[1])
    except _UnsupportedError as problem:
        state.warn(statement, problem.message)
        return
    for note in notes:
        state.warn(statement, note)
    fields: dict[str, object] = {"target": target}
    if method in _ELEMENT_EXPECTS:
        field_name, expected = _ELEMENT_EXPECTS[method]
        fields[field_name] = expected
    elif method in ("to_contain_text", "to_have_text", "to_have_value") and value is not None:
        fields["value" if method == "to_have_value" else "text"] = value
        if method != "to_contain_text":
            fields["match"] = "equals"
    elif method == "to_be_empty":
        fields["value"] = ""
        fields["match"] = "equals"
    else:
        state.warn(statement, catalog("recording.unsupported.assertion", name=method))
        return
    state.add("expect", fields, _describe(target))


def mask_source(source: str, spans: Sequence[Span]) -> str:
    """把指定位置的字串常數換成 ``"***"``。"""
    if not spans:
        return source
    lines = source.splitlines(keepends=True)
    for start_line, start_col, end_line, end_col in sorted(set(spans), reverse=True):
        first = lines[start_line - 1].encode("utf-8")
        last = lines[end_line - 1].encode("utf-8")
        replaced = first[:start_col] + f'"{MASK}"'.encode() + last[end_col:]
        lines[start_line - 1 : end_line] = [replaced.decode("utf-8")]
    return "".join(lines)


def convert_recording(
    source: str,
    *,
    scene_id: str,
    name: str,
    url: str | None = None,
    engine: str | None = None,
    role: str | None = None,
    category: str | None = None,
    now: datetime | None = None,
) -> Conversion:
    """把 codegen 的錄製稿轉成場景草稿。

    ``url`` 是錄製時的起始網址（錄製稿第一步不是 goto 時，補一個 goto 到這裡）；
    ``engine`` 是錄製用的瀏覽器；``role`` 是錄製時載入的登入角色，寫成 ``login: { role: … }``。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ConversionError(catalog("recording.syntax", line=error.lineno or 0)) from error
    start = _first_goto(tree) or url
    state = _State(scene_id=scene_id, origin=_origin(start), source=source)
    for statement in _statements(tree.body):
        if isinstance(statement, ast.Assign | ast.AnnAssign):
            _assignment(state, statement)
        elif isinstance(statement, ast.With | ast.AsyncWith):
            _with(state, statement)
        elif isinstance(statement, ast.Expr):
            _expression(state, statement)
    steps = state.steps
    if not steps or steps[0].action != "goto":
        if start is None:
            raise ConversionError(catalog("recording.empty"))
        first = state.relative(start)
        state.entries.insert(
            0,
            _Step(
                "goto", {"url": first}, catalog("recording.step.goto", url=first, target="", key="")
            ),
        )
    text = _render(state, name=name, engine=engine, role=role, category=category, now=now)
    checked = validate_text(text)
    if not checked.ok:  # pragma: no cover - 轉換器本身的錯誤，測試會發現
        details = "; ".join(issue.message for issue in checked.issues)
        raise ConversionError(catalog("recording.invalid", detail=details))
    return Conversion(
        scenario=text,
        masked_source=mask_source(source, sorted(state.masked)),
        warnings=tuple(state.warnings),
        inputs=tuple(state.inputs),
        secrets=tuple(state.secrets),
        steps=len(state.steps),
    )


def _render(
    state: _State,
    *,
    name: str,
    engine: str | None,
    role: str | None,
    category: str | None,
    now: datetime | None,
) -> str:
    moment = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# {catalog('recording.header', time=moment)}"]
    if state.warnings:
        lines.append(f"# {catalog('recording.header_warnings', count=len(state.warnings))}")
    lines += [
        "schemaVersion: 1",
        f"id: {scalar(state.scene_id)}",
        f"name: {scalar(name)}",
        f"description: {scalar(catalog('recording.description'))}",
    ]
    if category:
        lines.append(f"category: {scalar(category)}")
    if state.inputs:
        lines += ["", *block({"inputs": state.inputs})]
    if state.secrets:
        lines += ["", "secrets:", *(f"  - {scalar(secret)}" for secret in state.secrets)]
    browser: dict[str, object] = {}
    if engine:
        browser["engine"] = engine
    if state.origin:
        browser["baseUrl"] = state.origin
    if browser:
        lines += ["", *block({"browser": browser})]
    if role:
        lines += ["", *block({"login": {"role": role}})]
    lines += ["", "steps:"]
    number = 0
    for entry in state.entries:
        if isinstance(entry, ConversionWarning):
            note = catalog("recording.comment", line=entry.line, message=entry.message)
            lines.append(f"  # {note}")
            if entry.source:
                lines.append(f"  #   {entry.source}")
            continue
        number += 1
        step: dict[str, object] = {
            "id": f"{entry.action.lower()}-{number}",
            "name": entry.name,
            "action": entry.action,
            **entry.fields,
        }
        lines += block({"steps": [step]}, flow_keys=frozenset({"target"}))[1:]
    return "\n".join(lines) + "\n"
