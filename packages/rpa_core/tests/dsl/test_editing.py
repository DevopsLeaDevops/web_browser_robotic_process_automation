"""改寫場景檔的入參、出參段落（表單編輯），以及產生 YAML 片段。"""

from pathlib import Path
from textwrap import dedent

import pytest

from rpa_core.dsl import validate_text
from rpa_core.dsl.editing import find_block, rename_input, replace_contract
from rpa_core.dsl.yaml_loader import load_yaml
from rpa_core.dsl.yaml_writer import block, flow, scalar

ROOT = Path(__file__).resolve().parents[4]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"


@pytest.mark.parametrize(
    "value",
    [
        "建立紀錄",
        "true",
        "123",
        "1.5",
        "null",
        "",
        " 前後有空白 ",
        "a: b",
        "# 註解",
        "{{ inputs.title }}",
        "#record-id",
        "^DEMO-[A-Z0-9]+$",
        "\\S",
        "line\nbreak",
        "「全形」",
        "- 開頭是減號",
        "http://127.0.0.1:8765",
    ],
)
def test_scalar_reads_back_as_the_same_string(value: str) -> None:
    data, _ = load_yaml(f"key: {scalar(value)}\nflow: {{ a: {scalar(value)} }}\n")
    assert data == {"key": value, "flow": {"a": value}}


def test_scalar_writes_plain_text_when_it_can() -> None:
    assert scalar("建立紀錄") == "建立紀錄"
    assert scalar("true") == '"true"'
    assert scalar(True) == "true"
    assert scalar(12) == "12"
    assert scalar(None) == "null"


def test_block_and_flow() -> None:
    lines = block(
        {
            "steps": [{"id": "a", "action": "click", "target": {"role": "button", "name": "OK"}}],
            "inputs": {"title": {"type": "string", "enum": ["a", "b"]}},
            "empty": {},
        },
        flow_keys=frozenset({"target"}),
    )
    assert lines == [
        "steps:",
        "  - id: a",
        "    action: click",
        "    target: { role: button, name: OK }",
        "inputs:",
        "  title:",
        "    type: string",
        "    enum: [a, b]",
        "empty: {}",
    ]
    assert flow({}) == "{}"


SCENARIO = """\
# 開頭的註解
schemaVersion: 1
id: demo
name: 示範

# 入參說明
inputs:
  title:
    type: string
    default: 舊的
  # 中間的註解
  count:
    type: integer

# 步驟的說明
steps:
  - id: fill
    action: fill
    target: { label: 標題 }
    value: '{{ inputs.title }}'
  - id: fill-again
    action: fill
    target: { label: 標題 }
    value: '{{ inputs["title"] }} / {{ inputs.titles }}'
"""


def test_find_block_keeps_comments_of_the_next_section_outside() -> None:
    lines = SCENARIO.splitlines()
    start, end = find_block(lines, "inputs") or (0, 0)
    assert lines[start] == "inputs:"
    assert lines[end - 1] == "    type: integer"
    assert find_block(lines, "outputs") is None


def test_replace_contract_only_changes_the_two_sections() -> None:
    text = replace_contract(
        SCENARIO,
        inputs={
            "headline": {"type": "string", "default": "新的", "minLength": 1},
            "count": {"type": "integer", "minimum": 0},
        },
        outputs={"result": {"type": "string", "from": "{{ inputs.headline }}"}},
        renames={"title": "headline"},
    )

    assert text.startswith("# 開頭的註解\nschemaVersion: 1\n")
    assert (
        "# 入參說明\ninputs:\n  headline:\n    type: string\n    default: 新的\n    minLength: 1\n"
        in text
    )
    assert "  count:\n    type: integer\n    minimum: 0\n\noutputs:\n  result:\n" in text
    assert "# 步驟的說明\nsteps:" in text
    assert "value: '{{ inputs.headline }}'" in text
    # 名稱只是開頭相同的引用（titles）不會被改
    assert """value: '{{ inputs["headline"] }} / {{ inputs.titles }}'""" in text
    assert "中間的註解" not in text


def test_removing_all_inputs_drops_the_section() -> None:
    text = replace_contract(SCENARIO.replace("{{ inputs.title }}", "x"), inputs={}, outputs={})
    assert "inputs:" not in text
    assert "\n\n\n" not in text


def test_adding_sections_to_a_scenario_without_them() -> None:
    plain = (
        "schemaVersion: 1\nid: demo\nname: 示範\n\n"
        "steps:\n  - id: open\n    action: goto\n    url: https://example.com/\n"
    )
    text = replace_contract(plain, inputs={"q": {"type": "string", "default": "x"}}, outputs={})
    assert text == (
        "schemaVersion: 1\nid: demo\nname: 示範\n\ninputs:\n  q:\n    type: string\n"
        "    default: x\n\nsteps:\n  - id: open\n    action: goto\n    url: https://example.com/\n"
    )
    assert validate_text(text).ok


def test_round_trip_of_a_real_scenario_keeps_it_valid() -> None:
    original = BA_001.read_text(encoding="utf-8")
    scenario = validate_text(original).scenario
    assert scenario is not None
    inputs = {
        name: spec.model_dump(mode="json", by_alias=True, exclude_none=True)
        for name, spec in scenario.inputs.items()
    }
    outputs = {
        name: spec.model_dump(mode="json", by_alias=True, exclude_none=True)
        for name, spec in scenario.outputs.items()
    }
    text = replace_contract(original, inputs=inputs, outputs=outputs)
    again = validate_text(text).scenario
    assert again is not None
    assert again.inputs == scenario.inputs
    assert again.outputs == scenario.outputs
    assert again.steps == scenario.steps
    # 段落以外的內容完全相同
    assert text.split("inputs:")[0] == original.split("inputs:")[0]
    assert text.split("\nbrowser:")[1] == original.split("\nbrowser:")[1]


def test_crlf_files_keep_their_line_endings() -> None:
    text = replace_contract(SCENARIO.replace("\n", "\r\n"), inputs={}, outputs={}, renames={})
    assert "\r\n" in text
    assert "\n" not in text.replace("\r\n", "")


def test_rename_input() -> None:
    assert rename_input("{{ inputs.a }} {{ inputs.ab }} {{ facts.inputs.a }}", "a", "b") == (
        "{{ inputs.b }} {{ inputs.ab }} {{ facts.inputs.a }}"
    )
    assert rename_input("{{ inputs['a'] }}", "a", "b") == "{{ inputs['b'] }}"


SECTIONS = dedent(
    """\
    schemaVersion: 1
    id: demo
    name: 範例

    steps:
    - id: open  # 第一欄開始的清單也是 steps 的內容
      action: goto
      url: https://example.com/

    # 斷言的說明
    verify:
      - value: "{{ facts.x }}"
        notEmpty: true
    """
)


def test_section_text_and_replace_section() -> None:
    from rpa_core.dsl.editing import replace_section, section_text

    steps = section_text(SECTIONS, "steps")
    assert steps.splitlines()[0] == "steps:"
    assert steps.splitlines()[-1] == "  url: https://example.com/"
    assert section_text(SECTIONS, "inputs") == ""

    verify = 'verify:\n  - value: "{{ facts.y }}"\n    equals: a'
    replaced = replace_section(SECTIONS, "verify", verify)
    assert "# 斷言的說明" in replaced  # 段落前的註解保留
    assert "facts.x" not in replaced
    assert "facts.y" in replaced
    assert replaced.startswith(SECTIONS.split("verify:")[0])

    added = replace_section(SECTIONS, "inputs", "inputs:\n  q: { type: string }")
    assert added.index("inputs:") < added.index("steps:")
    removed = replace_section(added, "inputs", "")
    assert removed == SECTIONS


def test_append_items_follows_the_existing_indentation() -> None:
    from rpa_core.dsl.editing import append_items

    item = ["  - id: next", "    action: goto", "    url: https://example.com/next"]
    appended = append_items(SECTIONS, "steps", item, whole=["steps:", *item])
    assert "\n- id: next\n  action: goto\n" in appended
    assert appended.index("- id: next") < appended.index("# 斷言的說明")

    flow = "schemaVersion: 1\nsecrets: [A]\n"
    assert append_items(flow, "secrets", ["  - B"], whole=["secrets:", "  - A", "  - B"]) == (
        "schemaVersion: 1\nsecrets:\n  - A\n  - B\n"
    )
