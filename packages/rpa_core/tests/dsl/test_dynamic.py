"""入參的動態值：{{today}}、{{today+1}}、{{now}}、{{random:10:30}}。"""

from collections.abc import Iterator
from datetime import datetime
from typing import cast

import pytest

from rpa_core.dsl import InputSpec, format_issue, inputs_json_schema, validate_text
from rpa_core.dsl.dynamic import (
    DynamicValueError,
    dynamic_expression,
    escape,
    evaluate,
    has_dynamic,
    parse,
    samples,
)
from rpa_core.dsl.features import input_features, scenario_features
from rpa_core.i18n import use_locale

NOW = datetime(2026, 10, 21, 7, 30, 5)
HEADER = "schemaVersion: 1\nid: demo\nname: 示範\n"
GOTO = "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def low(lo: int, hi: int) -> int:
    del hi
    return lo


def high(lo: int, hi: int) -> int:
    del lo
    return hi


def value(text: object, value_type: str = "string") -> object:
    return evaluate(text, value_type, now=NOW, pick=low)


# ---------------------------------------------------------------- 求值


def test_the_users_example() -> None:
    """使用者給的例子（2026-10-21 的需求）：日期、隔天、10～30 的隨機數、夾在文字裡的日期。"""
    inputs = {
        "arrivalDate": "{{today}}",
        "department": "测试部",
        "expiryDate": "{{today+1}}",
        "purchaseQuantity": "{{random:10:30}}",
        "remark": "CG-001脚本创建{{today}}日期",
    }
    assert {name: value(text) for name, text in inputs.items()} == {
        "arrivalDate": "2026-10-21",
        "department": "测试部",
        "expiryDate": "2026-10-22",
        "purchaseQuantity": "10",
        "remark": "CG-001脚本创建2026-10-21日期",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{{today}}", "2026-10-21"),
        ("{{ today }}", "2026-10-21"),
        ("{{TODAY}}", "2026-10-21"),
        ("{{today+1}}", "2026-10-22"),
        ("{{ today + 11 }}", "2026-11-01"),
        ("{{today-21}}", "2026-09-30"),
        ("{{today+71}}", "2026-12-31"),
        ("{{today+72}}", "2027-01-01"),
        ("{{today:YYYY/MM/DD}}", "2026/10/21"),
        ("{{today+1:yyyyMMdd}}", "20261022"),
        ("{{today:yyyy年MM月dd日}}", "2026年10月21日"),
        ("{{today: DD.MM.YYYY}}", "21.10.2026"),
        ("{{now}}", "2026-10-21 07:30:05"),
        ("{{now:HH:mm}}", "07:30"),
        ("{{now+1:yyyy-MM-dd HH:mm:ss}}", "2026-10-22 07:30:05"),
        ("{{now:yyyyMMddHHmmss}}", "20261021073005"),
        ("PO-{{now:yyyyMMddHHmmss}}-{{random:1:9}}", "PO-20261021073005-1"),
        ('{{"{{"}}today}}', "{{today}}"),
        ("{{ '}}' }}", "}}"),
        ("沒有動態值 }} {", "沒有動態值 }} {"),
        ("", ""),
    ],
)
def test_evaluate_text(text: str, expected: str) -> None:
    assert value(text) == expected


def test_random_is_inclusive_and_independent() -> None:
    assert evaluate("{{random:10:30}}", now=NOW, pick=high) == "30"
    assert evaluate("{{random:-5:-5}}", now=NOW) == "-5"
    seen = {evaluate("{{random:1:3}}", "integer", now=NOW) for _ in range(200)}
    assert seen == {1, 2, 3}
    # 每個 random 各自抽
    draws: list[tuple[int, int]] = []

    def record(lo: int, hi: int) -> int:
        draws.append((lo, hi))
        return lo

    evaluate("{{random:1:2}}-{{random:3:4}}", now=NOW, pick=record)
    assert draws == [(1, 2), (3, 4)]


def test_numbers_for_integer_and_number_inputs() -> None:
    assert value("{{random:10:30}}", "integer") == 10
    assert value(" {{random:10:30}} ", "integer") == 10
    assert value("1{{random:0:9}}", "integer") == 10
    assert value("{{random:10:30}}", "number") == 10
    assert value("{{random:10:30}}.5", "number") == 10.5
    # 不是數字的結果維持文字，交給型別檢查回報
    assert value("{{today}}", "integer") == "2026-10-21"
    assert value("{{random:10:30}}", "boolean") == "10"


def test_values_without_dynamic_parts_are_unchanged() -> None:
    for plain in (12, 1.5, True, None, ["{{today}}"], "2026-10-21", "{today}", "{ {today} }"):
        assert evaluate(plain, now=NOW) == plain
    assert not has_dynamic(12)
    assert not has_dynamic("{today}")
    assert has_dynamic("a {{ b")


def test_now_defaults_to_local_time() -> None:
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    assert evaluate("{{today}}") in (today, datetime.now().astimezone().strftime("%Y-%m-%d"))


# ---------------------------------------------------------------- 寫錯


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("{{tody}}", "unknown"),
        ("{{ inputs.title }}", "unknown"),
        ("{{123}}", "unknown"),
        ("{{}}", "empty"),
        ("{{  }}", "empty"),
        ("{{today", "unclosed"),
        ("前面 {{today} 後面", "unclosed"),
        ('{{"abc}}', "quote"),
        ('{{"a"b"}}', "quote"),
        ("{{today+}}", "date_syntax"),
        ("{{today+x}}", "date_syntax"),
        ("{{today1}}", "date_syntax"),
        ("{{today*2}}", "date_syntax"),
        ("{{today+36501}}", "offset_range"),
        ("{{today:}}", "format_no_token"),
        ("{{today:abc}}", "format_no_token"),
        ("{{today:yyyy/mm/dd}}", "format_time"),
        ("{{today:HH}}", "format_time"),
        ("{{random}}", "random_syntax"),
        ("{{random:10}}", "random_syntax"),
        ("{{random:1.5:3}}", "random_syntax"),
        ("{{random:a:b}}", "random_syntax"),
        ("{{random:30:10}}", "random_range"),
    ],
)
def test_mistakes(text: str, code: str) -> None:
    with pytest.raises(DynamicValueError) as caught:
        parse(text)
    assert caught.value.code == code
    assert caught.value.message


def test_mistake_messages() -> None:
    def message(text: str) -> str:
        with pytest.raises(DynamicValueError) as caught:
            evaluate(text)
        return caught.value.message

    assert message("{{tody}}") == (
        "看不懂動態值 {{tody}}；可以用 {{today}}、{{today+1}}、{{now}}、{{random:10:30}}"
    )
    assert message("x {{random:30:10}}") == "{{random:30:10}} 的最小值 30 大於最大值 10"
    with use_locale("en"):
        assert message("{{today:yyyy/mm/dd}}") == (
            "{{today:yyyy/mm/dd}}: today has no time of day; the month is upper-case MM "
            "(lower-case mm is minutes); use now for times"
        )


# ---------------------------------------------------------------- 跳脫、代表值、提示


@pytest.mark.parametrize(
    "text",
    ["{{today}}", "{{{{", "a{{b}}c{{", "{{ '}}' }}", '{{"', "沒有大括號", "}}{{"],
)
def test_escape_keeps_text_as_is(text: str) -> None:
    assert evaluate(escape(text), now=NOW) == text
    assert escape(5) == 5


def test_samples_use_both_ends_of_random_ranges() -> None:
    assert samples("{{random:10:30}}", "integer", now=NOW) == [10, 30]
    assert samples("{{random:7:7}}", "integer", now=NOW) == [7]
    assert samples("{{today}}", now=NOW) == ["2026-10-21"]
    assert samples("固定", now=NOW) == ["固定"]


@pytest.mark.parametrize(
    "spec",
    [
        "{ type: integer, enum: [1, 3], default: '{{random:1:3}}' }",
        "{ enum: ['11', '22'], default: '{{random:1:2}}{{random:1:2}}' }",
        "{ pattern: '^(1|3)$', default: '{{random:1:3}}' }",
    ],
)
def test_random_defaults_check_values_between_endpoints(spec: str) -> None:
    result = validate_text(HEADER + f"inputs:\n  q: {spec}\n" + GOTO)
    assert [issue.code for issue in result.issues] == ["value.default_invalid"]


def test_random_defaults_accept_complete_enum_and_pattern() -> None:
    result = validate_text(
        HEADER
        + "inputs:\n"
        + "  q: { type: integer, enum: [1, 2, 3], default: '{{random:1:3}}' }\n"
        + "  s: { pattern: '^item-[1-3]$', default: 'item-{{random:1:3}}' }\n"
        + GOTO
    )
    assert not result.issues


def test_exhaustive_random_checks_are_bounded_without_restricting_plain_randoms() -> None:
    spec = InputSpec(pattern="^[0-9]+$")
    assert spec.check_value("{{random:1:1000}}") == []
    assert spec.check_value("{{random:1:10}}{{random:1:100}}") == []
    for text in ("{{random:1:1001}}", "{{random:1:100}}{{random:1:100}}"):
        with pytest.raises(DynamicValueError, match="1000") as caught:
            spec.check_value(text)
        assert caught.value.code == "random_checks_limit"
    assert InputSpec(type="integer").check_value("{{random:1:1000000}}") == []
    assert InputSpec(pattern="^[0-9-]+$").check_value("{{today}}", now=NOW) == []


def test_exhaustive_random_limit_is_reported_as_a_default_issue() -> None:
    result = validate_text(
        HEADER + "inputs:\n  q: { pattern: '^[0-9]+$', default: '{{random:1:1001}}' }\n" + GOTO
    )
    assert [issue.code for issue in result.issues] == ["dynamic.random_checks_limit"]


def test_dynamic_expression() -> None:
    assert dynamic_expression("{{random:10:30}}") == "random:10:30"
    assert dynamic_expression("單號 {{ today+1 }}") == "today+1"
    assert dynamic_expression('{{"{{"}} {{now}}') == "now"
    assert dynamic_expression('{{"{{"}}') is None
    assert dynamic_expression("{{ inputs.title }}") is None
    assert dynamic_expression("沒有") is None


# ---------------------------------------------------------------- 場景校驗


def test_defaults_can_be_dynamic() -> None:
    text = (
        HEADER
        + "inputs:\n"
        + "  arrivalDate: { default: '{{today}}', pattern: '^\\d{4}-\\d{2}-\\d{2}$' }\n"
        + "  expiryDate: { default: '{{today+1}}' }\n"
        + "  purchaseQuantity:\n"
        + "    { type: integer, minimum: 10, maximum: 30, default: '{{random:10:30}}' }\n"
        + "  remark: { default: 'CG-001脚本创建{{today}}日期', maxLength: 40 }\n"
        + GOTO
    )
    result = validate_text(text)
    assert not result.issues, [format_issue(i) for i in result.issues]
    assert result.scenario is not None
    assert scenario_features(result.scenario) == {"dynamicValues"}
    schema = inputs_json_schema(result.scenario)
    properties = cast("dict[str, object]", schema["properties"])
    assert properties["purchaseQuantity"] == {
        "type": "integer",
        "minimum": 10,
        "maximum": 30,
        "x-dynamicDefault": "{{random:10:30}}",
    }


@pytest.mark.parametrize(
    ("line", "code", "message"),
    [
        (
            "  d: { default: '{{tody}}' }\n",
            "dynamic.unknown",
            "入參 d › default：看不懂動態值 {{tody}}；"
            "可以用 {{today}}、{{today+1}}、{{now}}、{{random:10:30}}",
        ),
        (
            "  q: { type: integer, minimum: 10, maximum: 20, default: '{{random:10:30}}' }\n",
            "value.default_invalid",
            "入參 q › default：預設值不符合限制：maximum: 20",
        ),
        (
            "  q: { type: integer, default: '{{today}}' }\n",
            "value.default_invalid",
            "入參 q › default：預設值不符合限制：type: integer",
        ),
        (
            "  r: { maxLength: 5, default: '單號{{random:1:1000}}' }\n",
            "value.default_invalid",
            "入參 r › default：預設值不符合限制：maxLength: 5",
        ),
    ],
)
def test_wrong_dynamic_defaults(line: str, code: str, message: str) -> None:
    result = validate_text(HEADER + "inputs:\n" + line + GOTO)
    assert [(i.code, i.field) for i in result.issues] == [
        (code, "inputs." + line.split(":")[0].strip() + ".default")
    ]
    assert format_issue(result.issues[0]).endswith(message.split("：", 1)[1])


def test_unquoted_braces_in_yaml_ask_for_quotes() -> None:
    result = validate_text(HEADER + "inputs:\n  d:\n    default: {{today}}\n" + GOTO)
    assert [(i.code, i.field, i.position.line if i.position else 0) for i in result.issues] == [
        ("yaml.unquoted_template", "inputs.d.default", 6)
    ]
    assert result.issues[0].message.startswith("以 {{ 開頭的值要加上引號")


@pytest.mark.parametrize(
    ("value_text", "name"),
    [
        ("'{{ today }}'", "today"),
        ("'{{random:10:30}}'", "random:10:30"),
        ("'到貨 {{today+1}}'", "today+1"),
    ],
)
def test_dynamic_values_in_steps_point_to_inputs(value_text: str, name: str) -> None:
    text = (
        HEADER
        + "steps:\n"
        + "  - { id: open, action: goto, url: https://example.test/ }\n"
        + f"  - {{ id: date, action: fill, target: {{ css: '#d' }}, value: {value_text} }}\n"
    )
    result = validate_text(text)
    assert [i.code for i in result.issues] == ["template.dynamic_in_step"]
    assert result.issues[0].message.startswith(f"{name} 是入參值用的動態值")
    assert "{{" + name + "}}" in result.issues[0].message


def test_run_inputs_need_the_feature_only_with_dynamic_values() -> None:
    assert input_features({"a": "{{today}}", "b": 1}) == {"dynamicValues"}
    assert input_features({"a": "2026-10-21"}) == frozenset()
    assert input_features({}) == frozenset()
    assert input_features(None) == frozenset()
