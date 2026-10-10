"""模型本身：預設值、欄位名稱、JSON 往返與 JSON Schema。"""

import json
from typing import cast

import pytest
from pydantic import ValidationError

from rpa_core.dsl import (
    ACTIONS,
    SCHEMA_VERSION,
    STRATEGIES,
    ClickStep,
    ExtractStep,
    Locator,
    Scenario,
    ScreenshotStep,
    WaitForStep,
    scenario_json_schema,
    validate_text,
)

TEXT = """\
schemaVersion: 1
id: demo
name: 示範
params:
  month: { type: string, default: "2026-09" }
secrets: [PASSWORD]
browser: { baseUrl: https://example.test, viewport: { width: 1280, height: 800 } }
defaults: { timeout: 5000 }
steps:
  - { id: open, action: goto, url: /login }
  - { id: pick, action: select, target: { label: 月份 }, option: "{{ params.month }}" }
  - { id: go, action: click, target: { role: button, name: 查詢, exact: true } }
  - { id: wait, action: waitFor, target: { testId: result } }
  - { id: rows, action: extract, target: { css: tr }, as: rows, multiple: true,
      fields: { no: { target: { css: td } }, link: { get: attribute, attribute: href } } }
  - { id: shot, action: screenshot, fullPage: true }
"""


def load() -> Scenario:
    result = validate_text(TEXT)
    assert result.scenario is not None, result.issues
    return result.scenario


def test_defaults() -> None:
    scenario = load()

    assert scenario.schema_version == SCHEMA_VERSION
    assert scenario.browser.engine == "chromium"
    assert scenario.browser.headless is True
    click = scenario.steps[2]
    assert isinstance(click, ClickStep)
    assert (click.button, click.click_count, click.modifiers) == ("left", 1, None)
    wait = scenario.steps[3]
    assert isinstance(wait, WaitForStep)
    assert (wait.state, wait.match) == ("visible", "contains")
    shot = scenario.steps[5]
    assert isinstance(shot, ScreenshotStep)
    assert shot.file is None


def test_extract_as_is_aliased() -> None:
    step = load().steps[4]

    assert isinstance(step, ExtractStep)
    assert step.as_ == "rows"
    assert step.fields is not None
    assert step.fields["link"].get == "attribute"


def test_locator_strategy() -> None:
    click = load().steps[2]
    assert isinstance(click, ClickStep)
    assert click.target.strategy == "role"


def test_models_are_frozen() -> None:
    scenario = load()
    with pytest.raises(ValidationError):
        scenario.name = "改名"  # pyright: ignore[reportAttributeAccessIssue]


def test_dump_uses_dsl_field_names() -> None:
    data = load().model_dump(mode="json", exclude_unset=True)

    assert data["schemaVersion"] == 1
    assert data["browser"]["baseUrl"] == "https://example.test"
    assert data["steps"][4]["as"] == "rows"
    assert data["steps"][5] == {"id": "shot", "action": "screenshot", "fullPage": True}
    # 單一字串的 option 載入後一律是清單
    assert data["steps"][1]["option"] == ["{{ params.month }}"]


def test_json_round_trip() -> None:
    scenario = load()
    again = Scenario.model_validate_json(scenario.model_dump_json(exclude_unset=True))

    assert again == scenario


def test_python_attribute_names_are_not_accepted() -> None:
    with pytest.raises(ValidationError):
        Locator.model_validate({"test_id": "x"})
    assert Locator.model_validate({"testId": "x"}).test_id == "x"


def test_strategies_match_locator_fields() -> None:
    aliases = {info.alias for info in Locator.model_fields.values()}
    assert set(STRATEGIES) <= aliases


def test_json_schema_lists_every_action() -> None:
    schema = scenario_json_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    defs = cast("dict[str, dict[str, object]]", schema["$defs"])
    steps = cast("dict[str, object]", cast("dict[str, object]", schema["properties"])["steps"])
    items = cast("dict[str, object]", steps["items"])
    discriminator = cast("dict[str, object]", items["discriminator"])
    mapping = cast("dict[str, str]", discriminator["mapping"])
    assert sorted(mapping) == sorted(ACTIONS)
    for action, ref in mapping.items():
        model = defs[ref.removeprefix("#/$defs/")]
        properties = cast("dict[str, dict[str, object]]", model["properties"])
        assert properties["action"]["const"] == action


def test_json_schema_option_accepts_string_or_list() -> None:
    schema = json.dumps(scenario_json_schema()["$defs"])
    select = json.loads(schema)["SelectStep"]["properties"]["option"]

    assert {"type": "string"} in select["anyOf"]
