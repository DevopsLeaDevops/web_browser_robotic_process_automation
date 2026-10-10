"""場景契約：入參、出參、獨立斷言、總期限與 Python 腳本逃生門（ADR 0009）。"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import (
    Issue,
    format_issue,
    inputs_json_schema,
    outputs_json_schema,
    validate_file,
    validate_text,
)
from rpa_core.i18n import use_locale

HEADER = "schemaVersion: 1\nid: demo\nname: 示範\n"
GOTO = "  - { id: open, action: goto, url: https://example.test/ }\n"
EXTRACT = (
    "  - id: read\n"
    "    action: extract\n"
    "    target: { css: '#receipt' }\n"
    "    as: record\n"
    "    fields:\n"
    "      recordId: { target: { css: '#record-id' } }\n"
    "      status: { target: { css: '#record-status' } }\n"
)


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def issues(text: str) -> list[tuple[str, str]]:
    return [(i.code, i.field) for i in validate_text(text).issues]


def only(text: str) -> Issue:
    result = validate_text(text)
    assert len(result.issues) == 1, [format_issue(i) for i in result.issues]
    return result.issues[0]


# ---------------------------------------------------------------- 入參


def test_inputs_with_constraints() -> None:
    text = (
        HEADER
        + "inputs:\n"
        + "  title: { type: string, minLength: 1, maxLength: 60, pattern: '\\S' }\n"
        + "  quantity: { type: integer, minimum: 1, maximum: 30, default: 12 }\n"
        + "  region: { enum: [北區, 南區], default: 北區 }\n"
        + "steps:\n"
        + GOTO
    )
    result = validate_text(text)
    assert result.scenario is not None, result.issues

    schema = inputs_json_schema(result.scenario)
    assert schema["required"] == ["title"]
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties == {
        "title": {"type": "string", "minLength": 1, "maxLength": 60, "pattern": "\\S"},
        "quantity": {"type": "integer", "minimum": 1, "maximum": 30, "default": 12},
        "region": {"type": "string", "enum": ["北區", "南區"], "default": "北區"},
    }


@pytest.mark.parametrize(
    ("spec", "code", "field"),
    [
        ("{ type: integer, minLength: 1 }", "value.not_applicable", "inputs.x.minLength"),
        ("{ type: string, maximum: 3 }", "value.not_applicable", "inputs.x.maximum"),
        ("{ type: integer, minimum: 5, maximum: 1 }", "value.range", "inputs.x.maximum"),
        ("{ minLength: 3, maxLength: 1 }", "value.range", "inputs.x.maxLength"),
        ("{ pattern: '(' }", "regex.invalid", "inputs.x.pattern"),
        ("{ type: integer, enum: [1, a] }", "value.enum_type", "inputs.x.enum[1]"),
        (
            "{ type: integer, maximum: 30, default: 31 }",
            "value.default_invalid",
            "inputs.x.default",
        ),
        ("{ enum: [甲], default: 乙 }", "value.default_invalid", "inputs.x.default"),
        ("{ type: array }", "choice", "inputs.x.type"),
    ],
)
def test_input_rules(spec: str, code: str, field: str) -> None:
    issue = only(HEADER + f"inputs:\n  x: {spec}\nsteps:\n" + GOTO)
    assert (issue.code, issue.field) == (code, field)


def test_default_violation_names_the_rule() -> None:
    issue = only(
        HEADER + "inputs:\n  x: { type: integer, maximum: 30, default: 31 }\nsteps:\n" + GOTO
    )
    assert issue.message == "預設值不符合限制：maximum: 30"


def test_params_was_renamed_to_inputs() -> None:
    issue = only(HEADER + "params:\n  x: {}\nsteps:\n" + GOTO)

    assert issue.code == "unknown_field.renamed"
    assert issue.message == "params 已改名為 inputs"


# ---------------------------------------------------------------- 出參與獨立斷言


def contract(outputs: str, verify: str) -> str:
    return HEADER + outputs + "steps:\n" + GOTO + EXTRACT + verify


VERIFY = "verify:\n  - { value: '{{ facts.record.status }}', equals: 已建立 }\n"


def test_outputs_and_verify() -> None:
    text = contract(
        "outputs:\n"
        "  recordId: { pattern: '^DEMO-', from: '{{ facts.record.recordId }}' }\n"
        "  rows: { type: array, from: '{{ facts.record }}' }\n",
        VERIFY,
    )
    result = validate_text(text)
    assert result.scenario is not None, result.issues

    schema = outputs_json_schema(result.scenario)
    assert schema["required"] == ["recordId", "rows"]
    assert schema["properties"] == {
        "recordId": {"type": "string", "pattern": "^DEMO-"},
        "rows": {"type": "array"},
    }


def test_outputs_need_verify() -> None:
    text = contract("outputs:\n  id: { from: '{{ facts.record.recordId }}' }\n", "")
    issue = only(text)

    assert (issue.code, issue.field) == ("verify.required_for_outputs", "outputs")
    assert "獨立斷言" in issue.message


def test_dsl_outputs_need_from() -> None:
    issue = only(contract("outputs:\n  id: {}\n", VERIFY))
    assert (issue.code, issue.field) == ("output.from_required", "outputs.id")


@pytest.mark.parametrize(
    ("check", "code", "field"),
    [
        ("{ value: 已建立, equals: 已建立 }", "verify.constant_value", "verify[0].value"),
        ("{ value: '{{ facts.record }}' }", "one_of.none", "verify[0]"),
        (
            "{ value: '{{ facts.record }}', equals: a, contains: b }",
            "one_of.many",
            "verify[0].contains",
        ),
        ("{ value: '{{ facts.record }}', matches: '[' }", "regex.invalid", "verify[0].matches"),
        ("{ value: '{{ facts.record }}', notEmpty: false }", "choice", "verify[0].notEmpty"),
        (
            "{ value: '{{ facts.nope }}', notEmpty: true }",
            "template.unknown_fact",
            "verify[0].value",
        ),
        (
            "{ value: '{{ inputs.nope }}', notEmpty: true }",
            "template.undeclared_inputs",
            "verify[0].value",
        ),
    ],
)
def test_verify_rules(check: str, code: str, field: str) -> None:
    issue = only(contract("", f"verify:\n  - {check}\n"))
    assert (issue.code, issue.field) == (code, field)


# ---------------------------------------------------------------- facts 與 {{ }}


def test_facts_must_be_extracted_before_use() -> None:
    text = (
        HEADER
        + "steps:\n"
        + GOTO
        + "  - id: early\n    action: fill\n    target: { css: a }\n"
        + "    value: '{{ facts.record.status }}'\n"
        + EXTRACT
    )
    issue = only(text)

    assert (issue.code, issue.step, issue.field) == ("template.fact_not_yet", 2, "value")
    assert issue.message == "facts.record 要等後面的 extract 步驟才會產生"


def test_facts_are_not_available_in_browser_settings() -> None:
    text = HEADER + "browser: { baseUrl: '{{ facts.record }}' }\nsteps:\n" + GOTO + EXTRACT
    assert issues(text) == [("template.facts_unavailable", "browser.baseUrl")]


def test_duplicate_extract_names() -> None:
    issue = only(HEADER + "steps:\n" + GOTO + EXTRACT + EXTRACT.replace("id: read", "id: again"))
    assert (issue.code, issue.step, issue.field) == ("extract.duplicate_as", 3, "as")


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("'{{ params.x }}'", "template.renamed"),
        ("'{{ user }}'", "template.unknown_variable"),
        ("'{{ inputs.x | nofilter }}'", "template.syntax"),
        ("'{{ inputs.x ) }}'", "template.syntax"),
        ("'{{ inputs[\"y\"] }}'", "template.undeclared_inputs"),
    ],
)
def test_template_rules(value: str, code: str) -> None:
    text = (
        HEADER
        + "inputs:\n  x: {}\n"
        + "steps:\n"
        + f"  - {{ id: a, action: fill, target: {{ css: a }}, value: {value} }}\n"
    )
    assert [c for c, _ in issues(text)] == [code]


def test_jinja_filters_and_set_are_fine() -> None:
    text = (
        HEADER
        + "inputs:\n  x: {}\n"
        + "steps:\n"
        + "  - id: a\n    action: fill\n    target: { css: a }\n"
        + "    value: '{% set y = inputs.x | upper %}{{ y }}-{{ env.HOME | default(\"\") }}'\n"
    )
    assert validate_text(text).ok


# ---------------------------------------------------------------- 總期限、分類


def test_deadline_and_category() -> None:
    result = validate_text(HEADER + "category: 範例資料\ndeadline: 45000\nsteps:\n" + GOTO)

    assert result.scenario is not None
    assert (result.scenario.category, result.scenario.deadline) == ("範例資料", 45000)
    assert issues(HEADER + "deadline: 0\nsteps:\n" + GOTO) == [("greater_than", "deadline")]


# ---------------------------------------------------------------- Python 腳本逃生門

SCRIPT_BODY = "script: { automation: a.py, assertion: b.py }\n"
SCRIPT = (
    HEADER
    + "inputs:\n  title: {}\n"
    + "outputs:\n  recordId: { type: string }\n"
    + "script:\n  automation: automation.py\n  assertion: checks/assertion.py\n"
)


def test_script_scenario(tmp_path: Path) -> None:
    (tmp_path / "checks").mkdir()
    (tmp_path / "automation.py").write_text("", encoding="utf-8")
    (tmp_path / "checks" / "assertion.py").write_text("", encoding="utf-8")
    path = tmp_path / "scenario.yaml"
    path.write_text(SCRIPT, encoding="utf-8")

    result = validate_file(path)

    assert result.ok, result.issues
    assert result.scenario is not None
    assert result.scenario.script is not None
    assert result.scenario.steps is None


def test_script_files_must_exist(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(SCRIPT, encoding="utf-8")

    result = validate_file(path)

    assert [(i.code, i.field) for i in result.issues] == [
        ("script.missing", "script.automation"),
        ("script.missing", "script.assertion"),
    ]
    assert result.issues[0].position is not None
    assert result.issues[0].position.line == 9


@pytest.mark.parametrize(
    "script_path", ["../outside.py", "/etc/passwd.py", "automation.sh", "a/../b.py", ""]
)
def test_script_path_must_stay_inside(script_path: str) -> None:
    text = HEADER + f"script:\n  automation: '{script_path}'\n  assertion: assertion.py\n"
    codes = [c for c, _ in issues(text)]
    assert codes[0] in ("format.script_path", "empty_string")


@pytest.mark.parametrize(
    ("body", "code", "field"),
    [
        ("", "one_of.none", ""),
        (
            "steps:\n" + GOTO + "script: { automation: a.py, assertion: b.py }\n",
            "one_of.many",
            "script",
        ),
        (
            SCRIPT_BODY + "verify:\n  - { value: '{{ inputs.x }}', notEmpty: true }\n",
            "script.verify_not_allowed",
            "verify",
        ),
        (
            "outputs:\n  y: { from: '{{ inputs.x }}' }\n" + SCRIPT_BODY,
            "script.output_from_not_allowed",
            "outputs.y.from",
        ),
    ],
)
def test_body_rules(body: str, code: str, field: str) -> None:
    text = HEADER + "inputs:\n  x: {}\n" + body
    assert issues(text) == [(code, field)]
