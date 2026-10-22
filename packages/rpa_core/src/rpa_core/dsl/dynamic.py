"""入參的動態值：值裡的 ``{{ … }}`` 在每次執行開始時換成當下的日期、隨機數。

和步驟裡的 ``{{ }}``（Jinja，引用 inputs、facts…）不同：動態值只寫在入參的「值」——
場景的預設值、執行時給的入參、試驗場的固定值——而且只有下面這幾種寫法
（``{{ }}`` 裡可以有空白，名稱不分大小寫）：

==========================  ==============================================
寫法                         結果（以 2026-10-21 07:30:05 執行為例）
==========================  ==============================================
``{{today}}``               2026-10-21
``{{today+1}}``             2026-10-22（``today-7`` 往前 7 天）
``{{today:YYYY/MM/DD}}``    2026/10/21（格式見 :data:`FORMAT_TOKENS`）
``{{now}}``                 2026-10-21 07:30:05（也可以 ``now+1``、``now:HH:mm``）
``{{random:10:30}}``        10 到 30 之間（含兩端）的隨機整數
``{{"{{"}}``                引號裡的文字原樣保留，用來寫出 ``{{`` 本身
==========================  ==============================================

- 文字裡可以夾動態值，例如 ``CG-001 建立於 {{today}}``。
- 入參是整數或數字、求值的結果是數字的文字（例如整個值是 ``{{random:10:30}}``）時得到數字；
  其他都是文字。
- 同一次執行的所有動態值用同一個「現在」（呼叫端傳入，預設是這台電腦的本地時間）；
  每個 random 各自抽。
- 值裡任何 ``{{ … }}`` 都當成動態值：看不懂就是錯，不會把 ``{{tody}}`` 原樣打進頁面。
  別處來的資料（例如上游場景的出參）要原樣使用時，先用 :func:`escape`。
"""

import random
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from rpa_core.dsl.fields import catalog

__all__ = [
    "FEATURE",
    "FORMAT_TOKENS",
    "MAX_OFFSET_DAYS",
    "NAMES",
    "DynamicValueError",
    "dynamic_expression",
    "escape",
    "evaluate",
    "has_dynamic",
    "parse",
    "uses_dynamic",
]

FEATURE: Final = "dynamicValues"
"""DSL 擴充名稱（見 :mod:`rpa_core.dsl.features`）：用到動態值的執行要交給看得懂的 App。"""

FORMAT_TOKENS: Final = {
    "yyyy": "%Y",
    "YYYY": "%Y",
    "MM": "%m",
    "dd": "%d",
    "DD": "%d",
    "HH": "%H",
    "mm": "%M",
    "ss": "%S",
}
"""日期格式裡會換掉的代號（年、月、日、時、分、秒，都補零）；其他字元照寫。

和 Java 的 ``yyyy-MM-dd HH:mm:ss`` 相同，也接受大寫的 ``YYYY``、``DD``。
"""

NAMES: Final = frozenset({"today", "now", "random"})
"""動態值的名稱（不分大小寫）。"""

MAX_OFFSET_DAYS: Final = 36500
"""today±N 的天數上限（一百年）；超過多半是寫錯。"""

_DEFAULT_FORMATS: Final = {"today": "yyyy-MM-dd", "now": "yyyy-MM-dd HH:mm:ss"}
_TIME_TOKENS: Final = frozenset({"HH", "mm", "ss"})
_TOKEN: Final = re.compile("|".join(sorted(FORMAT_TOKENS, key=len, reverse=True)))
_NAME: Final = re.compile(r"([A-Za-z_]+)\s*(.*)", re.DOTALL)
_DATE_REST: Final = re.compile(r"(?:([+-])\s*(\d+))?\s*(?::(.*))?", re.DOTALL)
_RANDOM_REST: Final = re.compile(r":\s*([+-]?\d+)\s*:\s*([+-]?\d+)")
_INTEGER: Final = re.compile(r"[-+]?\d+")
_NUMBER: Final = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_QUOTES: Final = "\"'"
_BRACES: Final = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

type Pick = Callable[[int, int], int]
"""抽隨機整數：(最小, 最大) → 兩端都含的一個整數。"""


class DynamicValueError(ValueError):
    """動態值寫錯；code 對應訊息目錄的 ``dsl.dynamic.<code>``。"""

    def __init__(self, code: str, **params: object) -> None:
        self.code = code
        self.params = params
        super().__init__(self.message)

    @property
    def message(self) -> str:
        """目前語言的說明。"""
        return catalog(f"dsl.dynamic.{self.code}", **self.params)


@dataclass(frozen=True, slots=True)
class Text:
    """原樣的文字。"""

    text: str


@dataclass(frozen=True, slots=True)
class Moment:
    """today、now：現在往後（負數往前）幾天，依格式寫出。"""

    days: int
    format: str


@dataclass(frozen=True, slots=True)
class RandomInteger:
    """random:最小:最大。"""

    low: int
    high: int


type Part = Text | Moment | RandomInteger


def has_dynamic(value: object) -> bool:
    """值裡有沒有 ``{{``（有就要當成動態值求值）。"""
    return isinstance(value, str) and "{{" in value


def uses_dynamic(values: Iterable[object]) -> bool:
    """這些值有沒有任何一個用到動態值（例如一次執行的全部入參）。"""
    return any(has_dynamic(value) for value in values)


def dynamic_expression(text: str) -> str | None:
    """文字照動態值的寫法讀得懂、而且有 today、now、random 時，第一個動態值的寫法（不含大括號）。

    給步驟的 ``{{ }}`` 校驗提示用：步驟裡寫了 ``{{random:10:30}}`` 時說明要改寫在入參。
    """
    try:
        parts = parse(text)
    except DynamicValueError:
        return None
    if all(isinstance(part, Text) for part in parts):
        return None
    for found in _BRACES.finditer(text):
        inner = found.group(1).strip()
        if inner and inner[0] not in _QUOTES:
            return inner
    return None


def escape(value: object) -> object:
    """讓文字原樣通過求值：每個 ``{{`` 寫成 ``{{"{{"}}``；不是文字的值不變。"""
    if not isinstance(value, str) or "{{" not in value:
        return value
    return value.replace("{{", '{{"{{"}}')


def parse(text: str) -> tuple[Part, ...]:
    """把文字拆成原樣的文字與動態值；寫錯時拋出 :class:`DynamicValueError`。"""
    parts: list[Part] = []
    position = 0
    while True:
        start = text.find("{{", position)
        if start < 0:
            if position < len(text):
                parts.append(Text(text[position:]))
            return tuple(parts)
        if start > position:
            parts.append(Text(text[position:start]))
        end = _closing(text, start)
        source = text[start : end + 2]
        parts.append(_expression(text[start + 2 : end].strip(), source))
        position = end + 2


def _closing(text: str, start: int) -> int:
    """``{{`` 對應的 ``}}`` 的位置；引號裡的 ``}}`` 不算。"""
    inner = start + 2
    while inner < len(text) and text[inner].isspace():
        inner += 1
    search_from = inner
    if inner < len(text) and text[inner] in _QUOTES:
        quote_end = text.find(text[inner], inner + 1)
        if quote_end < 0:
            raise DynamicValueError("quote", text=_excerpt(text[start:]))
        search_from = quote_end + 1
    end = text.find("}}", search_from)
    if end < 0:
        raise DynamicValueError("unclosed", text=_excerpt(text[start:]))
    return end


def _excerpt(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _expression(inner: str, source: str) -> Part:
    if not inner:
        raise DynamicValueError("empty")
    if inner[0] in _QUOTES:
        if len(inner) < 2 or inner[-1] != inner[0] or inner[0] in inner[1:-1]:
            raise DynamicValueError("quote", text=source)
        return Text(inner[1:-1])
    match = _NAME.fullmatch(inner)
    name = match.group(1).lower() if match else ""
    rest = match.group(2) if match else ""
    if name in _DEFAULT_FORMATS:
        return _moment(name, rest, source)
    if name == "random":
        found = _RANDOM_REST.fullmatch(rest)
        if found is None:
            raise DynamicValueError("random_syntax", text=source)
        try:
            low, high = int(found.group(1)), int(found.group(2))
        except ValueError as error:
            raise DynamicValueError("random_syntax", text=_excerpt(source)) from error
        if low > high:
            raise DynamicValueError("random_range", text=source, low=low, high=high)
        return RandomInteger(low, high)
    raise DynamicValueError("unknown", text=source)


def _moment(name: str, rest: str, source: str) -> Moment:
    found = _DATE_REST.fullmatch(rest)
    if found is None:
        raise DynamicValueError("date_syntax", text=source)
    sign, digits, written = found.groups()
    try:
        days = int(digits) if digits else 0
    except ValueError as error:
        raise DynamicValueError(
            "offset_range", text=_excerpt(source), limit=MAX_OFFSET_DAYS
        ) from error
    if days > MAX_OFFSET_DAYS:
        raise DynamicValueError("offset_range", text=source, limit=MAX_OFFSET_DAYS)
    if sign == "-":
        days = -days
    if written is None:
        return Moment(days, _DEFAULT_FORMATS[name])
    layout = written.strip()
    tokens = set(_TOKEN.findall(layout))
    if not tokens:
        raise DynamicValueError("format_no_token", text=source)
    if name == "today" and tokens & _TIME_TOKENS:
        raise DynamicValueError("format_time", text=source)
    return Moment(days, layout)


def _format(moment: datetime, layout: str) -> str:
    return _TOKEN.sub(lambda token: moment.strftime(FORMAT_TOKENS[token.group(0)]), layout)


def _render(parts: Iterable[Part], now: datetime, pick: Pick) -> str:
    pieces: list[str] = []
    for part in parts:
        match part:
            case Text(text):
                pieces.append(text)
            case Moment(days, layout):
                pieces.append(_format(now + timedelta(days=days), layout))
            case RandomInteger(low, high):
                pieces.append(str(pick(low, high)))
    return "".join(pieces)


def _typed(text: str, value_type: str) -> object:
    """整數、數字入參：結果是數字的文字時轉成數字。"""
    stripped = text.strip()
    try:
        if value_type == "integer" and _INTEGER.fullmatch(stripped):
            return int(stripped)
        if value_type == "number" and _NUMBER.fullmatch(stripped):
            return int(stripped) if _INTEGER.fullmatch(stripped) else float(stripped)
    except ValueError as error:
        raise DynamicValueError("number_range", text=_excerpt(text)) from error
    return text


def _local_now() -> datetime:
    return datetime.now().astimezone()


def evaluate(
    value: object,
    value_type: str = "string",
    *,
    now: datetime | None = None,
    pick: Pick | None = None,
) -> object:
    """入參的值求值後的結果；沒有動態值時原樣回傳。

    ``now`` 是這次執行的「現在」（預設是本地時間）；``pick`` 抽隨機整數（預設 random.randint，
    測試時可以固定）。寫錯時拋出 :class:`DynamicValueError`。
    """
    if not isinstance(value, str) or "{{" not in value:
        return value
    parts = parse(value)
    text = _render(parts, now or _local_now(), pick or random.randint)
    return _typed(text, value_type)
