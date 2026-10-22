"""執行時的契約：{{ }} 求值、入參、獨立斷言、出參、Secrets 遮罩。不需要瀏覽器。"""

from collections.abc import Iterator
from datetime import datetime

import pytest

from rpa_core.dsl import InputSpec, Scenario, validate_text
from rpa_core.i18n import use_locale
from rpa_runner.contract import (
    build_outputs,
    check_candidate_outputs,
    check_inputs,
    parse_cli_value,
    prepare_inputs,
    run_verify,
)
from rpa_runner.secrets import mask, missing_secrets, read_secrets
from rpa_runner.templates import TemplateEvaluationError, render, render_native, render_tree

SCENARIO = """\
schemaVersion: 1
id: demo
name: 示範
inputs:
  title: { minLength: 1, maxLength: 5 }
  quantity: { type: integer, minimum: 1, maximum: 30, default: 12 }
  flag: { type: boolean, default: false }
outputs:
  recordId: { pattern: '^DEMO-', from: '{{ facts.record.recordId }}' }
  quantity: { type: integer, maximum: 30, from: '{{ facts.record.quantity }}' }
  rows: { type: array, from: '{{ facts.rows }}' }
secrets: [DEMO_PASSWORD]
steps:
  - { id: read, action: extract, target: { css: a }, as: record }
  - { id: rows, action: extract, target: { css: tr }, as: rows, multiple: true }
verify:
  - { name: 狀態, value: '{{ facts.record.status }}', equals: 已建立 }
  - { value: '{{ facts.record.title }}', equals: '{{ inputs.title }}' }
  - { value: '{{ facts.record.recordId }}', matches: '^DEMO-[A-Z0-9]+$' }
  - { value: '{{ facts.record.note }}', notEmpty: true }
"""

RECORD: dict[str, object] = {
    "recordId": "DEMO-ABC123",
    "title": "標題",
    "quantity": "12",
    "status": "已建立",
    "note": "x",
}
ROWS = [{"a": "1"}, {"a": "2"}]
FACTS: dict[str, object] = {"record": RECORD, "rows": ROWS}


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


@pytest.fixture
def scenario() -> Scenario:
    result = validate_text(SCENARIO)
    assert result.scenario is not None, result.issues
    return result.scenario


# ---------------------------------------------------------------- {{ }}


def test_render_text_and_native() -> None:
    context = {"inputs": {"n": 3, "s": "甲"}, "facts": {"rows": [1, 2]}}

    assert render("第 {{ inputs.n }} 筆：{{ inputs.s | upper }}", context) == "第 3 筆：甲"
    assert render("沒有運算式", context) == "沒有運算式"
    assert render_native("{{ facts.rows }}", context) == [1, 2]
    assert render_native(" {{ inputs.n }} ", context) == 3
    assert render_native("共 {{ inputs.n }} 筆", context) == "共 3 筆"


def test_render_undefined_value_is_an_error() -> None:
    with pytest.raises(TemplateEvaluationError):
        render("{{ facts.missing.value }}", {"facts": {}})
    with pytest.raises(TemplateEvaluationError):
        render_native("{{ facts.missing }}", {"facts": {}})


def test_render_is_sandboxed() -> None:
    with pytest.raises(TemplateEvaluationError):
        render("{{ inputs.__class__.__mro__ }}", {"inputs": {}})


def test_render_tree_skips_names() -> None:
    tree = {"name": "{{ inputs.a }}", "value": "{{ inputs.a }}", "list": ["{{ inputs.a }}", 1]}
    assert render_tree(tree, {"inputs": {"a": "x"}}, skip=frozenset({"name"})) == {
        "name": "{{ inputs.a }}",
        "value": "x",
        "list": ["x", 1],
    }


# ---------------------------------------------------------------- 入參


def test_inputs_get_defaults(scenario: Scenario) -> None:
    resolved, problems = check_inputs(scenario, {"title": "甲乙"})

    assert problems == []
    assert resolved == {"title": "甲乙", "quantity": 12, "flag": False}


def test_input_problems(scenario: Scenario) -> None:
    _, problems = check_inputs(scenario, {"quantity": 31, "extra": 1})
    messages = [problem.message for problem in problems]

    assert messages == [
        "不認得的入參 extra",
        "缺少入參 title",
        "入參 quantity 不符合限制：maximum: 30",
    ]


DYNAMIC = """\
schemaVersion: 1
id: purchase
name: 採購單
inputs:
  arrivalDate: { default: '{{today}}' }
  expiryDate: { default: '{{today+1}}' }
  purchaseQuantity: { type: integer, minimum: 10, maximum: 30, default: '{{random:10:30}}' }
  remark: { default: 'CG-001脚本创建{{today}}日期' }
  skuCode: { default: '455590002' }
steps:
  - { id: open, action: goto, url: https://example.test/ }
"""


def test_dynamic_values_are_evaluated_for_each_run() -> None:
    result = validate_text(DYNAMIC)
    assert result.scenario is not None, result.issues
    now = datetime(2026, 12, 31, 23, 59, 59)

    resolved, problems = check_inputs(result.scenario, {}, now=now, pick=lambda lo, hi: hi)

    assert problems == []
    assert resolved == {
        "arrivalDate": "2026-12-31",
        "expiryDate": "2027-01-01",
        "purchaseQuantity": 30,
        "remark": "CG-001脚本创建2026-12-31日期",
        "skuCode": "455590002",
    }
    # 執行時給的入參也可以是動態值；沒給 now 時用這台電腦的本地時間
    resolved, problems = check_inputs(
        result.scenario, {"skuCode": "SKU-{{random:1:1}}", "purchaseQuantity": "{{random:12:12}}"}
    )
    assert problems == []
    assert resolved["skuCode"] == "SKU-1"
    assert resolved["purchaseQuantity"] == 12
    assert resolved["arrivalDate"] == datetime.now().astimezone().strftime("%Y-%m-%d")


def test_preparation_keeps_expressions_and_each_run_draws_once() -> None:
    result = validate_text(DYNAMIC)
    assert result.scenario is not None
    raw, problems = prepare_inputs(result.scenario, {})
    assert problems == []
    assert raw["purchaseQuantity"] == "{{random:10:30}}"
    assert raw["arrivalDate"] == "{{today}}"
    draws = iter([26, 18])
    calls: list[tuple[int, int]] = []

    def pick(low: int, high: int) -> int:
        calls.append((low, high))
        return next(draws)

    now = datetime(2026, 10, 22, 23, 59, 59)
    for quantity in (26, 18):
        resolved, problems = check_inputs(result.scenario, raw, now=now, pick=pick)
        assert problems == []
        assert resolved["arrivalDate"] == "2026-10-22"
        assert resolved["expiryDate"] == "2026-10-23"
        assert resolved["remark"] == "CG-001脚本创建2026-10-22日期"
        assert resolved["skuCode"] == "455590002"
        assert resolved["purchaseQuantity"] == quantity
        # 後續引用與斷言讀取運行態值，不再抽樣。
        assert render("{{ inputs.purchaseQuantity }}", {"inputs": resolved}) == str(quantity)
        assert render("{{ inputs.purchaseQuantity }}", {"inputs": resolved}) == str(quantity)
    assert calls == [(10, 30), (10, 30)]


@pytest.mark.parametrize("picked", [1, 2, 3])
def test_random_enum_validation_uses_only_the_actual_draw(picked: int) -> None:
    result = validate_text(
        "schemaVersion: 1\nid: demo\nname: 示範\n"
        "inputs:\n  q: { type: integer, enum: [1, 3] }\n"
        "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n"
    )
    assert result.scenario is not None
    _, problems = check_inputs(
        result.scenario, {"q": "{{random:1:3}}"}, pick=lambda _lo, _hi: picked
    )
    expected = ["入參 q 不符合限制：enum"] if picked == 2 else []
    assert [problem.message for problem in problems] == expected


def test_dynamic_value_problems() -> None:
    result = validate_text(DYNAMIC)
    assert result.scenario is not None, result.issues

    _, problems = check_inputs(
        result.scenario,
        {"arrivalDate": "{{tody}}", "purchaseQuantity": "{{random:31:40}}", "remark": "{{today"},
    )

    assert [problem.message for problem in problems] == [
        "入參 arrivalDate 的動態值寫錯：看不懂動態值 {{tody}}；"
        "可以用 {{today}}、{{today+1}}、{{now}}、{{random:10:30}}",
        "入參 purchaseQuantity 不符合限制：maximum: 30",
        "入參 remark 的動態值寫錯：{{today 的 {{ 沒有對應的 }}",
    ]


@pytest.mark.parametrize("pick_index", [0, 1, 2])
@pytest.mark.parametrize(
    ("spec", "expression", "draws", "rule"),
    [
        ("{minLength: 2}", "{{random:-10:10}}", (-10, 0, 10), "minLength: 2"),
        ("{type: number, maximum: 0.5}", "0.{{random:1:10}}", (1, 9, 10), "maximum: 0.5"),
    ],
)
def test_random_constraints_validate_the_actual_value(
    spec: str, expression: str, draws: tuple[int, int, int], rule: str, pick_index: int
) -> None:
    result = validate_text(
        "schemaVersion: 1\nid: demo\nname: 示範\n"
        f"inputs:\n  q: {spec}\n"
        "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n"
    )
    assert result.scenario is not None
    _, problems = check_inputs(
        result.scenario, {"q": expression}, pick=lambda _lo, _hi: draws[pick_index]
    )
    expected = [f"入參 q 不符合限制：{rule}"] if pick_index == 1 else []
    assert [problem.message for problem in problems] == expected


@pytest.mark.parametrize(
    ("spec", "text", "expected"),
    [
        ({"type": "integer"}, "12", 12),
        ({"type": "integer"}, "1.5", "1.5"),
        ({"type": "number"}, "1.5", 1.5),
        ({"type": "number"}, "2", 2),
        ({"type": "boolean"}, "TRUE", True),
        ({"type": "boolean"}, "no", "no"),
        ({"type": "string"}, "0123", "0123"),
    ],
)
def test_parse_cli_value(spec: dict[str, object], text: str, expected: object) -> None:
    assert parse_cli_value(InputSpec.model_validate(spec), text) == expected


# ---------------------------------------------------------------- 獨立斷言與出參


def test_verify_all_pass(scenario: Scenario) -> None:
    checks = run_verify(scenario, {"inputs": {"title": "標題"}, "facts": FACTS})

    assert [check.passed for check in checks] == [True, True, True, True]
    assert checks[0].name == "狀態"
    assert checks[1].name == "第 2 條斷言"


def test_verify_failures_are_reported_per_check(scenario: Scenario) -> None:
    record = {**RECORD, "status": "已取消"}
    del record["note"]
    facts = {"record": record}
    checks = run_verify(scenario, {"inputs": {"title": "標題"}, "facts": facts})

    assert [check.passed for check in checks] == [False, True, True, False]
    assert checks[0].actual == "已取消"
    assert checks[3].error is not None


def test_outputs_are_converted_and_checked(scenario: Scenario) -> None:
    outputs, problems = build_outputs(scenario, {"facts": FACTS})

    assert problems == []
    assert outputs == {"recordId": "DEMO-ABC123", "quantity": 12, "rows": ROWS}


def test_output_problems(scenario: Scenario) -> None:
    facts = {"record": {"recordId": "X-1", "quantity": "99"}, "rows": "不是清單"}
    _, problems = build_outputs(scenario, {"facts": facts})

    assert [problem.name for problem in problems] == ["recordId", "quantity", "rows"]
    assert problems[1].message == "出參 quantity 不符合限制：maximum: 30"


def test_candidate_outputs_from_script(scenario: Scenario) -> None:
    problems = check_candidate_outputs(scenario, {"recordId": "DEMO-1", "quantity": 1, "x": 1})
    assert [problem.message for problem in problems] == [
        "assertion.py 寫出了沒有宣告的出參 x",
        "缺少出參 rows",
    ]


# ---------------------------------------------------------------- Secrets


def test_secrets_from_environment(scenario: Scenario) -> None:
    assert read_secrets(scenario, {"DEMO_PASSWORD": "s3cret!"}) == {"DEMO_PASSWORD": "s3cret!"}
    assert missing_secrets(scenario, {}) == ["DEMO_PASSWORD"]


def test_mask() -> None:
    text = "登入失敗：密碼 s3cret! 錯誤，ab 不遮"
    assert mask(text, {"P": "s3cret!", "Q": "ab"}) == "登入失敗：密碼 *** 錯誤，ab 不遮"
