"""YAML 載入：只用 YAML 1.2 core 規則，記下每個鍵與值的位置，拒絕重複的鍵。

PyYAML 預設是 YAML 1.1：``yes``、``on`` 會變成布林，``2026-09-01`` 會變成日期，
重複的鍵默默取最後一個。場景檔由人、錄製器與 AI 撰寫，這些行為都會造成難以察覺的錯誤，
所以這裡只借用 PyYAML 的解析器（compose 出節點樹），自己把節點轉成 Python 值：

- 純量只認 YAML 1.2 core schema：null、true/false、整數、浮點數，其餘都是字串。
- 只接受 str、int、float、bool、null、seq、map 七種標籤；``!!python/...`` 等一律拒絕。
- 同一個物件裡的鍵不能重複，鍵必須是字串。
- 錨點與別名可以用，但不能自我參照，展開後的節點數有上限。

位置一律從 1 開始，與編輯器顯示的行號、列號一致。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar, Final, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

__all__ = [
    "MAX_NODES",
    "DataPath",
    "Position",
    "SourceMap",
    "YamlLoadError",
    "load_yaml",
]

type DataPath = tuple[str | int, ...]
"""從根開始的路徑，例如 ``("steps", 2, "target", "role")``。"""

MAX_NODES: Final = 100_000
"""展開別名後最多的節點數，防止「十億笑聲」這類用別名放大的檔案。"""

_TAG_PREFIX: Final = "tag:yaml.org,2002:"
_STR: Final = _TAG_PREFIX + "str"
_INT: Final = _TAG_PREFIX + "int"
_FLOAT: Final = _TAG_PREFIX + "float"
_BOOL: Final = _TAG_PREFIX + "bool"
_NULL: Final = _TAG_PREFIX + "null"
_SEQ: Final = _TAG_PREFIX + "seq"
_MAP: Final = _TAG_PREFIX + "map"

# YAML 1.2 core schema（https://yaml.org/spec/1.2.2/#1032-tag-resolution）
_NULL_RE: Final = re.compile(r"^(?:~|null|Null|NULL|)$")
_BOOL_RE: Final = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_RE: Final = re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT_RE: Final = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)


@dataclass(frozen=True, slots=True, order=True)
class Position:
    """檔案中的位置，行與列都從 1 開始。"""

    line: int
    column: int


@dataclass(frozen=True, slots=True)
class SourceMap:
    """每個路徑在原始檔中的位置。"""

    values: Mapping[DataPath, Position] = field(default_factory=dict[DataPath, Position])
    """值的開頭位置；物件與清單是第一個成員的位置。"""
    keys: Mapping[DataPath, Position] = field(default_factory=dict[DataPath, Position])
    """物件成員的鍵所在位置。"""

    def locate(self, path: DataPath) -> Position | None:
        """路徑本身的位置；路徑不存在（例如缺少的欄位）時往上找最近的祖先。"""
        for end in range(len(path), -1, -1):
            if (position := self.values.get(path[:end])) is not None:
                return position
        return None

    def locate_key(self, path: DataPath) -> Position | None:
        """物件成員的鍵所在位置；找不到時同 locate。"""
        return self.keys.get(path) or self.locate(path)


class YamlLoadError(Exception):
    """無法轉成資料的 YAML：語法錯誤、重複的鍵、不支援的標籤等。

    ``code`` 與 ``params`` 對應 rpa_core 訊息目錄中 ``yaml.<code>`` 的訊息。
    """

    def __init__(
        self, code: str, position: Position | None, path: DataPath = (), **params: object
    ) -> None:
        super().__init__(code, position, params)
        self.code = code
        self.position = position
        self.path = path
        self.params = params


class _CoreResolver(yaml.SafeLoader):
    """只認 YAML 1.2 core schema 的隱式型別。"""

    # 自己的空表，不繼承 SafeLoader 的 YAML 1.1 規則
    yaml_implicit_resolvers: ClassVar[dict[str | None, list[tuple[str, re.Pattern[str]]]]] = {}  # pyright: ignore[reportIncompatibleVariableOverride]


for _tag, _regexp, _first in (
    (_NULL, _NULL_RE, ["~", "n", "N", ""]),
    (_BOOL, _BOOL_RE, list("tTfF")),
    (_INT, _INT_RE, list("-+0123456789")),
    (_FLOAT, _FLOAT_RE, list("-+.0123456789")),
):
    _CoreResolver.add_implicit_resolver(_tag, _regexp, _first)  # pyright: ignore[reportUnknownMemberType]


def _position(node: Node) -> Position:
    mark = node.start_mark
    return Position(mark.line + 1, mark.column + 1)


@dataclass
class _Builder:
    values: dict[DataPath, Position] = field(default_factory=dict[DataPath, Position])
    keys: dict[DataPath, Position] = field(default_factory=dict[DataPath, Position])
    count: int = 0
    active: set[int] = field(default_factory=set[int])

    def build(self, node: Node, path: DataPath) -> object:
        self.count += 1
        if self.count > MAX_NODES:
            raise YamlLoadError("too_large", _position(node), path, limit=MAX_NODES)
        self.values[path] = _position(node)
        if isinstance(node, ScalarNode):
            return _scalar(node, path)
        if id(node) in self.active:
            raise YamlLoadError("recursive", _position(node), path)
        self.active.add(id(node))
        try:
            if isinstance(node, SequenceNode):
                _check_tag(node, _SEQ, path)
                return [self.build(child, (*path, i)) for i, child in enumerate(node.value)]
            if isinstance(node, MappingNode):
                _check_tag(node, _MAP, path)
                return self._mapping(node, path)
        finally:
            self.active.discard(id(node))
        raise YamlLoadError(
            "unsupported_tag", _position(node), path, tag=node.tag
        )  # pragma: no cover

    def _mapping(self, node: MappingNode, path: DataPath) -> dict[str, object]:
        result: dict[str, object] = {}
        first_seen: dict[str, Position] = {}
        for key_node, value_node in node.value:
            key_position = _position(key_node)
            if not isinstance(key_node, ScalarNode) or key_node.tag != _STR:
                raise YamlLoadError("key_not_string", key_position, path)
            key = str(key_node.value)
            if key in first_seen:
                raise YamlLoadError(
                    "duplicate_key", key_position, (*path, key), key=key, line=first_seen[key].line
                )
            first_seen[key] = key_position
            self.keys[(*path, key)] = key_position
            result[key] = self.build(value_node, (*path, key))
        return result


def _check_tag(node: Node, expected: str, path: DataPath) -> None:
    if node.tag != expected:
        raise YamlLoadError("unsupported_tag", _position(node), path, tag=node.tag)


def _scalar(node: ScalarNode, path: DataPath) -> object:
    value = str(node.value)
    tag = node.tag
    if tag == _STR:
        return value
    if tag == _NULL and _NULL_RE.match(value):
        return None
    if tag == _BOOL and _BOOL_RE.match(value):
        return value.lower() == "true"
    if tag == _INT and _INT_RE.match(value):
        if value.startswith("0o"):
            return int(value[2:], 8)
        if value.startswith("0x"):
            return int(value[2:], 16)
        return int(value, 10)
    if tag == _FLOAT and _FLOAT_RE.match(value):
        lowered = value.lower()
        if lowered.endswith(".nan"):
            return float("nan")
        if lowered.endswith(".inf"):
            return float("-inf") if lowered.startswith("-") else float("inf")
        return float(value)
    if tag in (_NULL, _BOOL, _INT, _FLOAT):
        # 明確寫了 !!int 之類的標籤，但內容不符
        raise YamlLoadError("invalid_scalar", _position(node), path, value=value, tag=tag)
    raise YamlLoadError("unsupported_tag", _position(node), path, tag=tag)


def load_yaml(text: str) -> tuple[object, SourceMap]:
    """把 YAML 文字轉成資料，並回傳每個路徑的位置。

    只接受一份文件。空白檔案、語法錯誤或不符合上述規則時拋出 YamlLoadError。
    """
    try:
        root = cast("Node | None", yaml.compose(text, Loader=_CoreResolver))  # pyright: ignore[reportUnknownMemberType]
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        position = Position(mark.line + 1, mark.column + 1) if mark is not None else None
        detail = error.problem or error.context or ""
        raise YamlLoadError("syntax", position, detail=detail) from error
    except yaml.YAMLError as error:  # pragma: no cover - 其他 PyYAML 錯誤都帶有位置
        raise YamlLoadError("syntax", None, detail=str(error)) from error
    if root is None:
        raise YamlLoadError("empty", Position(1, 1))
    builder = _Builder()
    data = builder.build(root, ())
    return data, SourceMap(builder.values, builder.keys)
