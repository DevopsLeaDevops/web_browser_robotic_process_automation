"""載入與校驗場景的入口：YAML 文字或檔案 → 場景模型與所有問題。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from rpa_core.dsl.checks import CrossIssue
from rpa_core.dsl.contract import spec_json_schema
from rpa_core.dsl.fields import catalog
from rpa_core.dsl.issues import (
    Issue,
    issue_from_cross,
    issue_from_yaml_error,
    issues_from_validation_error,
)
from rpa_core.dsl.scenario import CROSS_ISSUES_CONTEXT, Scenario
from rpa_core.dsl.yaml_loader import Position, SourceMap, YamlLoadError, load_yaml

__all__ = [
    "JSON_SCHEMA_DIALECT",
    "ValidationResult",
    "inputs_json_schema",
    "outputs_json_schema",
    "scenario_json_schema",
    "validate_data",
    "validate_file",
    "validate_text",
]

JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """校驗結果：沒有問題時 scenario 是載入好的場景，否則為 None。"""

    scenario: Scenario | None
    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_data(
    data: object, source: SourceMap | None = None, base_dir: Path | None = None
) -> ValidationResult:
    """校驗已經轉成 Python 資料的場景（例如從 JSON 讀出來的）。

    ``source`` 是 YAML 的位置對照；有的話每個問題都會帶上行號與列號。
    ``base_dir`` 是場景檔所在的資料夾；有的話會檢查 Python 腳本場景的腳本檔是否存在。
    """
    cross: list[CrossIssue] = []
    try:
        scenario = Scenario.model_validate(data, context={CROSS_ISSUES_CONTEXT: cross})
    except ValidationError as error:
        return ValidationResult(None, tuple(issues_from_validation_error(error, data, source)))
    if base_dir is not None and scenario.script is not None:
        for key in ("automation", "assertion"):
            script = getattr(scenario.script, key)
            if not (base_dir / script).is_file():
                cross.append(CrossIssue(("script", key), "script.missing", {"value": script}))
    issues = tuple(
        sorted(
            (issue_from_cross(issue, data, source) for issue in cross),
            key=lambda issue: issue.position or Position(0, 0),
        )
    )
    return ValidationResult(None if issues else scenario, issues)


def validate_text(text: str, base_dir: Path | None = None) -> ValidationResult:
    """校驗 YAML 文字；``base_dir`` 見 validate_data。"""
    try:
        data, source = load_yaml(text)
    except YamlLoadError as error:
        return ValidationResult(None, (issue_from_yaml_error(error),))
    return validate_data(data, source, base_dir)


def validate_file(path: Path) -> ValidationResult:
    """校驗 YAML 檔案（UTF-8，可以有 BOM）。"""
    try:
        raw = path.read_bytes()
    except OSError as error:
        return _file_issue("file.unreadable", detail=error.strerror or str(error))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        line = raw[: error.start].count(b"\n") + 1
        return _file_issue("file.encoding", line=line)
    return validate_text(text, path.parent)


def _file_issue(code: str, *, line: int = 1, **params: object) -> ValidationResult:
    message = catalog(f"dsl.{code}", **params)
    return ValidationResult(None, (Issue(code, message, (), Position(line, 1)),))


def inputs_json_schema(scenario: Scenario) -> dict[str, object]:
    """這個場景入參的 JSON Schema：沒有預設值的入參是必填，不接受未宣告的參數。"""
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": scenario.name,
        "type": "object",
        "additionalProperties": False,
        "required": [name for name, spec in scenario.inputs.items() if spec.default is None],
        "properties": {name: spec_json_schema(spec) for name, spec in scenario.inputs.items()},
    }


def outputs_json_schema(scenario: Scenario) -> dict[str, object]:
    """這個場景出參的 JSON Schema：所有出參都是必填。"""
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": scenario.name,
        "type": "object",
        "additionalProperties": False,
        "required": list(scenario.outputs),
        "properties": {name: spec_json_schema(spec) for name, spec in scenario.outputs.items()},
    }


def scenario_json_schema() -> dict[str, Any]:
    """場景的 JSON Schema（draft 2020-12），給編輯器自動補全、AI 生成與前端使用。"""
    schema = Scenario.model_json_schema(by_alias=True, mode="validation")
    return {"$schema": JSON_SCHEMA_DIALECT, **schema}
