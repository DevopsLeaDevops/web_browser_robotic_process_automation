"""場景 DSL：模型、YAML 載入與校驗。規格見 docs/design/dsl.html。

常用入口::

    from rpa_core.dsl import validate_file

    result = validate_file(Path("examples/login.yaml"))
    for issue in result.issues:
        print(issue.position, format_issue(issue))
"""

from rpa_core.dsl.issues import Issue, format_field, format_issue
from rpa_core.dsl.locators import ARIA_ROLES, STRATEGIES, Locator
from rpa_core.dsl.scenario import (
    SCHEMA_VERSION,
    BrowserConfig,
    Defaults,
    ParamSpec,
    Scenario,
    Viewport,
)
from rpa_core.dsl.steps import (
    ACTIONS,
    ClickStep,
    ExpectStep,
    ExtractField,
    ExtractStep,
    FillStep,
    GotoStep,
    PressStep,
    ScreenshotStep,
    SelectStep,
    Step,
    StepBase,
    WaitForStep,
)
from rpa_core.dsl.validation import (
    ValidationResult,
    scenario_json_schema,
    validate_data,
    validate_file,
    validate_text,
)
from rpa_core.dsl.yaml_loader import Position

__all__ = [
    "ACTIONS",
    "ARIA_ROLES",
    "SCHEMA_VERSION",
    "STRATEGIES",
    "BrowserConfig",
    "ClickStep",
    "Defaults",
    "ExpectStep",
    "ExtractField",
    "ExtractStep",
    "FillStep",
    "GotoStep",
    "Issue",
    "Locator",
    "ParamSpec",
    "Position",
    "PressStep",
    "Scenario",
    "ScreenshotStep",
    "SelectStep",
    "Step",
    "StepBase",
    "ValidationResult",
    "Viewport",
    "WaitForStep",
    "format_field",
    "format_issue",
    "scenario_json_schema",
    "validate_data",
    "validate_file",
    "validate_text",
]
