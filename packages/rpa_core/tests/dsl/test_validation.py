"""校驗結果：每個問題都要指出正確的行號、列號、步驟與欄位（M1 驗收條件）。"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import (
    Issue,
    Position,
    Scenario,
    format_issue,
    validate_data,
    validate_file,
    validate_text,
)
from rpa_core.i18n import use_locale

HEADER = "schemaVersion: 1\nid: demo\nname: 示範\n"
EXTRACT = "action: extract\n    target: { css: a }\n    as: x\n    "


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def position_of(text: str, needle: str, occurrence: int = 1) -> Position:
    """needle 第 occurrence 次出現的位置（行、列從 1 開始）。"""
    index = -1
    for _ in range(occurrence):
        index = text.index(needle, index + 1)
    line = text.count("\n", 0, index) + 1
    column = index - (text.rfind("\n", 0, index) + 1) + 1
    return Position(line, column)


def only_issue(text: str) -> Issue:
    result = validate_text(text)
    assert result.scenario is None
    assert len(result.issues) == 1, [format_issue(i) for i in result.issues]
    return result.issues[0]


def scenario(steps: str, top: str = "") -> str:
    return HEADER + top + "steps:\n" + steps


# ---------------------------------------------------------------- 合法的場景


def test_valid_scenario() -> None:
    text = scenario(
        "  - id: open\n"
        "    action: goto\n"
        "    url: https://example.test/\n"
        "  - id: ok\n"
        "    action: expect\n"
        "    title: 首頁\n"
    )
    result = validate_text(text)

    assert result.ok
    assert result.issues == ()
    assert isinstance(result.scenario, Scenario)
    assert [step.id for step in result.scenario.steps or ()] == ["open", "ok"]


# ---------------------------------------------------------------- 結構錯誤


def test_unknown_field_suggests_close_name() -> None:
    text = scenario("  - id: s\n    action: screenshot\n    fullpage: true\n")
    issue = only_issue(text)

    assert issue.code == "unknown_field.suggest"
    assert issue.position == position_of(text, "fullpage")
    assert (issue.step, issue.step_id, issue.field) == (1, "s", "fullpage")
    assert format_issue(issue) == "步驟 1（s） › fullpage：不認得的欄位 fullpage，是不是 fullPage？"


def test_unknown_field_lists_allowed_fields_when_nothing_is_close() -> None:
    text = scenario("  - id: s\n    action: screenshot\n    zzz: 1\n")
    issue = only_issue(text)

    assert issue.code == "unknown_field"
    assert "fullPage" in issue.message
    assert "target" in issue.message


def test_unknown_top_level_field() -> None:
    text = HEADER + "step:\n  - id: a\n"
    result = validate_text(text)

    assert [(i.code, i.field) for i in result.issues] == [("unknown_field.suggest", "step")]


def test_unknown_action_points_at_action() -> None:
    text = scenario("  - id: a\n    action: clik\n    target: { css: a }\n")
    issue = only_issue(text)

    assert issue.code == "unknown_action.suggest"
    assert issue.position == position_of(text, "clik")
    assert issue.field == "action"
    assert "click" in issue.message


def test_missing_action() -> None:
    text = scenario("  - id: a\n    url: https://example.test/\n")
    issue = only_issue(text)

    assert issue.code == "missing_action"
    assert issue.position == position_of(text, "id: a")
    assert (issue.step, issue.field) == (1, "action")


def test_missing_field_points_at_step() -> None:
    text = scenario("  - id: open\n    action: goto\n")
    issue = only_issue(text)

    assert issue.code == "missing"
    assert issue.position == position_of(text, "id: open")
    assert format_issue(issue) == "步驟 1（open） › url：缺少必填欄位 url"


def test_step_without_id_is_numbered() -> None:
    text = scenario("  - action: goto\n    url: https://example.test/\n")
    issue = only_issue(text)

    assert issue.code == "missing"
    assert (issue.step, issue.step_id) == (1, None)
    assert format_issue(issue) == "步驟 1 › id：缺少必填欄位 id"


def test_number_where_string_expected() -> None:
    text = scenario("  - id: pw\n    action: fill\n    target: { label: 密碼 }\n    value: 1234\n")
    issue = only_issue(text)

    assert issue.code == "type.string"
    assert issue.position == position_of(text, "1234")
    assert "引號" in issue.message


def test_yes_stays_a_string() -> None:
    text = scenario("  - id: a\n    action: fill\n    target: { label: 同意 }\n    value: yes\n")
    result = validate_text(text)

    assert result.ok
    assert result.scenario is not None
    assert result.scenario.steps is not None
    step = result.scenario.steps[0]
    assert step.action == "fill"
    assert step.value == "yes"


def test_choice_with_suggestion() -> None:
    text = scenario("  - id: a\n    action: click\n    target: { role: buton }\n")
    issue = only_issue(text)

    assert issue.code == "choice.suggest"
    assert issue.position == position_of(text, "buton")
    assert issue.field == "target.role"
    assert "button" in issue.message


def test_choice_lists_values_when_few() -> None:
    text = scenario("  - id: a\n    action: click\n    target: { css: a }\n    button: top\n")
    issue = only_issue(text)

    assert issue.code == "choice"
    assert "left, right, middle" in issue.message


def test_choice_without_listing_many_values() -> None:
    text = scenario("  - id: a\n    action: click\n    target: { role: qqqqqq }\n")
    issue = only_issue(text)

    assert issue.code == "choice.many"
    assert "rpa schema" in issue.message


def test_choice_in_list() -> None:
    text = scenario(
        "  - id: a\n    action: click\n    target: { css: a }\n    modifiers: [Shift, ctrl]\n"
    )
    issue = only_issue(text)

    assert issue.code == "choice.suggest"
    assert issue.field == "modifiers[1]"
    assert issue.position == position_of(text, "ctrl")
    assert "Control" in issue.message


def test_schema_version() -> None:
    text = "schemaVersion: 2\nid: demo\nname: 示範\nsteps:\n  - { id: a, action: goto, url: /x }\n"
    issue = only_issue(text.replace("url: /x", "url: https://example.test/"))

    assert issue.code == "schema_version"
    assert issue.position == Position(1, 16)
    assert issue.field == "schemaVersion"


def test_root_must_be_a_mapping() -> None:
    issue = only_issue("- a\n- b\n")

    assert issue.code == "type.object"
    assert issue.field == ""
    assert issue.position == Position(1, 1)


def test_steps_must_not_be_empty() -> None:
    issue = only_issue(HEADER + "steps: []\n")

    assert issue.code == "too_few_items"
    assert issue.field == "steps"


def test_id_format() -> None:
    text = scenario("  - id: Login Step\n    action: goto\n    url: https://example.test/\n")
    issue = only_issue(text)

    assert issue.code == "format.slug"
    assert issue.position == position_of(text, "Login Step")


def test_invalid_dict_key_points_at_key() -> None:
    text = scenario(
        "  - id: rows\n"
        "    action: extract\n"
        "    target: { css: tr }\n"
        "    as: rows\n"
        "    fields:\n"
        "      order-no: { target: { css: td } }\n"
    )
    issue = only_issue(text)

    assert issue.code == "format.identifier"
    assert issue.position == position_of(text, "order-no")
    assert issue.field == "fields.order-no"


def test_timeout_limits() -> None:
    text = scenario("  - id: a\n    action: goto\n    url: https://example.test/\n    timeout: 0\n")
    issue = only_issue(text)

    assert issue.code == "greater_than"
    assert format_issue(issue) == "步驟 1（a） › timeout：必須大於 0"


def test_several_errors_are_reported_in_file_order() -> None:
    text = scenario(
        "  - id: a\n"
        "    action: goto\n"
        "  - id: b\n"
        "    action: fill\n"
        "    target: { label: x }\n"
        "    value: 1\n"
        "    extra: 1\n"
    )
    result = validate_text(text)

    assert [(i.step, i.code) for i in result.issues] == [
        (1, "missing"),
        (2, "type.string"),
        (2, "unknown_field"),
    ]
    lines = [i.position.line for i in result.issues if i.position]
    assert lines == sorted(lines)


# ---------------------------------------------------------------- 欄位之間的規則


def test_locator_needs_a_strategy() -> None:
    text = scenario("  - id: a\n    action: click\n    target: { nth: 1 }\n")
    issue = only_issue(text)

    assert issue.code == "locator.no_strategy"
    assert issue.field == "target"
    assert issue.position == position_of(text, "{ nth")


def test_locator_with_two_strategies_points_at_second() -> None:
    text = scenario("  - id: a\n    action: click\n    target: { label: 密碼, css: '#p' }\n")
    issue = only_issue(text)

    assert issue.code == "locator.multiple_strategies"
    assert issue.field == "target.css"
    assert issue.position == position_of(text, "'#p'")


@pytest.mark.parametrize(
    ("target", "code", "field"),
    [
        ("{ text: 登入, name: 登入 }", "locator.name_requires_role", "target.name"),
        ("{ css: a, exact: true }", "locator.exact_not_supported", "target.exact"),
        ("{ role: button, exact: true }", "locator.exact_requires_name", "target.exact"),
        (
            "{ css: a, fallback: [{ css: b, fallback: [{ css: c }] }] }",
            "locator.nested_fallback",
            "target.fallback[0].fallback",
        ),
        ("{ css: a, within: { nth: 0 } }", "locator.no_strategy", "target.within"),
        ("{ css: a, fallback: [] }", "too_few_items", "target.fallback"),
    ],
)
def test_locator_rules(target: str, code: str, field: str) -> None:
    issue = only_issue(scenario(f"  - id: a\n    action: click\n    target: {target}\n"))

    assert (issue.code, issue.field) == (code, field)


@pytest.mark.parametrize(
    ("body", "code", "field"),
    [
        ("action: waitFor", "one_of.none", ""),
        ("action: waitFor\n    url: /a\n    loadState: load", "one_of.many", "loadState"),
        ("action: waitFor\n    url: /a\n    state: hidden", "field.requires", "state"),
        ("action: waitFor\n    target: { css: a }\n    match: equals", "field.requires", "match"),
        ("action: waitFor\n    url: '['\n    match: regex", "regex.invalid", "url"),
        ("action: expect", "one_of.none", ""),
        ("action: expect\n    target: { css: a }", "one_of.none", ""),
        ("action: expect\n    text: 歡迎", "field.requires", "text"),
        (
            "action: expect\n    target: { css: a }\n    title: x",
            "expect.page_check_with_target",
            "title",
        ),
        (
            "action: expect\n    target: { css: a }\n    text: a\n    count: 1",
            "one_of.many",
            "count",
        ),
        (
            "action: expect\n    target: { css: a }\n    state: visible\n    match: equals",
            "expect.match_not_applicable",
            "match",
        ),
        ("action: expect\n    target: { css: a }\n    count: -1", "greater_than_equal", "count"),
        ("action: expect\n    url: '('\n    match: regex", "regex.invalid", "url"),
        (
            EXTRACT + "get: attribute",
            "extract.attribute_required",
            "",
        ),
        (
            EXTRACT + "attribute: href",
            "field.requires",
            "attribute",
        ),
        ("action: extract\n    target: { css: a }\n    as: 1x", "format.identifier", "as"),
        (
            EXTRACT + "get: table\n    multiple: true",
            "extract.table_conflict",
            "multiple",
        ),
        (
            EXTRACT + "get: text\n    fields: { a: {} }",
            "extract.fields_with_get",
            "get",
        ),
        (
            EXTRACT + "fields: { a: { get: attribute } }",
            "extract.attribute_required",
            "fields.a",
        ),
        (
            "action: screenshot\n    target: { css: a }\n    fullPage: true",
            "screenshot.full_page_with_target",
            "fullPage",
        ),
        ("action: screenshot\n    file: 截圖", "format.file_name", "file"),
        ("action: select\n    target: { css: a }\n    option: []", "too_few_items", "option"),
        ("action: select\n    target: { css: a }\n    option: [a, 1]", "type.string", "option[1]"),
        ("action: press\n    key: ''", "empty_string", "key"),
        (
            "action: click\n    target: { css: a }\n    clickCount: 4",
            "less_than_equal",
            "clickCount",
        ),
        ("action: goto\n    url: www.example.test", "url.invalid", "url"),
    ],
)
def test_step_rules(body: str, code: str, field: str) -> None:
    issue = only_issue(scenario(f"  - id: a\n    {body}\n"))

    assert (issue.code, issue.step, issue.field) == (code, 1, field)


def test_select_accepts_one_or_many_options() -> None:
    text = scenario(
        "  - id: one\n    action: select\n    target: { label: 區域 }\n    option: 北區\n"
        "  - id: many\n    action: select\n    target: { label: 狀態 }\n    option: [甲, 乙]\n"
    )
    result = validate_text(text)

    assert result.scenario is not None
    options = [step.option for step in result.scenario.steps or () if step.action == "select"]
    assert options == [["北區"], ["甲", "乙"]]


@pytest.mark.parametrize(
    ("top", "code", "field"),
    [
        (
            "inputs:\n  n: { type: integer, default: '1' }\n",
            "value.default_invalid",
            "inputs.n.default",
        ),
        (
            "inputs:\n  n: { type: number, default: true }\n",
            "value.default_invalid",
            "inputs.n.default",
        ),
        ("inputs:\n  n: { type: date }\n", "choice", "inputs.n.type"),
        ("inputs:\n  1n: { type: string }\n", "format.identifier", "inputs.1n"),
        ("secrets: [erp_password]\n", "format.secret_name", "secrets[0]"),
        ("browser: { baseUrl: example.test }\n", "url.invalid_base", "browser.baseUrl"),
        ("browser: { engine: chrome }\n", "choice.suggest", "browser.engine"),
        ("browser: { engine: edge }\n", "choice", "browser.engine"),
        (
            "browser: { viewport: { width: 0, height: 600 } }\n",
            "greater_than",
            "browser.viewport.width",
        ),
        ("defaults: { timeout: 99999999 }\n", "less_than_equal", "defaults.timeout"),
    ],
)
def test_top_level_rules(top: str, code: str, field: str) -> None:
    steps = "  - { id: a, action: goto, url: https://example.test/ }\n"
    issue = only_issue(scenario(steps, top))

    assert (issue.code, issue.step, issue.field) == (code, None, field)


# ---------------------------------------------------------------- 跨步驟的規則


def test_duplicate_step_id_points_at_second() -> None:
    text = scenario(
        "  - id: open\n    action: goto\n    url: https://example.test/\n"
        "  - id: open\n    action: goto\n    url: https://example.test/b\n"
    )
    issue = only_issue(text)

    assert issue.code == "step.duplicate_id"
    assert issue.position == position_of(text, "open", occurrence=2)
    assert format_issue(issue) == "步驟 2（open） › id：步驟 id open 重複，第一次出現在步驟 1"


def test_duplicate_secret() -> None:
    steps = "  - { id: a, action: goto, url: https://example.test/ }\n"
    issue = only_issue(scenario(steps, "secrets: [A, A]\n"))

    assert (issue.code, issue.field) == ("secret.duplicate", "secrets[1]")


def test_relative_url_needs_base_url() -> None:
    steps = "  - { id: a, action: goto, url: /login }\n"
    issue = only_issue(scenario(steps))
    assert issue.code == "url.relative_without_base"

    result = validate_text(scenario(steps, "browser: { baseUrl: https://example.test }\n"))
    assert result.ok


def test_template_references_must_be_declared() -> None:
    text = scenario(
        "  - id: a\n"
        "    action: fill\n"
        "    target: { label: 帳號 }\n"
        "    value: '{{ inputs.user }}-{{ secrets.PASSWORD }}-{{ env.HOME }}'\n",
        "inputs:\n  other: {}\n",
    )
    result = validate_text(text)

    assert [(i.code, i.field) for i in result.issues] == [
        ("template.undeclared_inputs", "value"),
        ("template.undeclared_secrets", "value"),
    ]
    assert result.issues[0].position == position_of(text, "'{{")
    assert "user" in result.issues[0].message


def test_declared_template_references_are_fine() -> None:
    text = scenario(
        "  - id: a\n"
        "    action: fill\n"
        "    target: { label: '{{ inputs.field }}' }\n"
        "    value: '{{ inputs.user | upper }} {{ secrets.PASSWORD }}'\n",
        "inputs:\n  user: {}\n  field: { default: 帳號 }\nsecrets: [PASSWORD]\n",
    )
    assert validate_text(text).ok


@pytest.mark.parametrize(
    ("value", "code"),
    [("'{{ }}'", "template.empty"), ("'a {{ inputs.x'", "template.unclosed")],
)
def test_template_syntax(value: str, code: str) -> None:
    text = scenario(
        f"  - id: a\n    action: fill\n    target: {{ label: x }}\n    value: {value}\n",
        "inputs:\n  x: {}\n",
    )
    assert only_issue(text).code == code


def test_names_and_descriptions_are_free_text() -> None:
    text = scenario(
        "  - id: a\n    name: 說明 {{ 不檢查\n    action: goto\n    url: https://example.test/\n",
        "description: 用 {{ inputs.x }} 舉例\n",
    )
    assert validate_text(text).ok


# ---------------------------------------------------------------- YAML 與檔案


def test_yaml_error_becomes_issue() -> None:
    issue = only_issue(HEADER + "steps:\n  - id: a\n    id: b\n")

    assert issue.code == "yaml.duplicate_key"
    assert issue.position == Position(6, 5)
    assert issue.step is not None
    assert issue.message == "鍵 id 重複，第一次出現在第 5 行"


def test_yaml_tag_is_shown_short() -> None:
    issue = only_issue("a: !!binary aGk=\n")
    assert issue.message == "不支援標籤 !!binary"


def test_validate_data_without_positions() -> None:
    result = validate_data({"schemaVersion": 1, "id": "x", "name": "x", "steps": [{"id": "a"}]})

    assert len(result.issues) == 1
    assert result.issues[0].position is None
    assert result.issues[0].code == "missing_action"


def test_validate_file_reads_utf8_with_bom(tmp_path: Path) -> None:
    path = tmp_path / "a.yaml"
    path.write_bytes(
        "﻿".encode() + scenario("  - { id: a, action: goto, url: https://example.test/ }\n").encode()
    )
    assert validate_file(path).ok


def test_validate_file_rejects_other_encodings(tmp_path: Path) -> None:
    path = tmp_path / "big5.yaml"
    path.write_bytes(("id: a\nname: 登入\n").encode("big5"))
    issue = validate_file(path).issues[0]

    assert issue.code == "file.encoding"
    assert issue.position == Position(2, 1)


def test_validate_file_missing(tmp_path: Path) -> None:
    issue = validate_file(tmp_path / "nope.yaml").issues[0]
    assert issue.code == "file.unreadable"


# ---------------------------------------------------------------- 語言


def test_messages_in_english() -> None:
    text = scenario("  - id: s\n    action: screenshot\n    fullpage: true\n")
    with use_locale("en"):
        issue = only_issue(text)
        line = format_issue(issue)

    assert line == "Step 1 (s) › fullpage: Unknown field fullpage. Did you mean fullPage?"


def test_model_validate_raises_first_cross_issue() -> None:
    data = {
        "schemaVersion": 1,
        "id": "x",
        "name": "x",
        "steps": [
            {"id": "a", "action": "goto", "url": "https://example.test/"},
            {"id": "a", "action": "goto", "url": "https://example.test/"},
        ],
    }
    with pytest.raises(ValueError, match="already used by step 1"):
        Scenario.model_validate(data)
