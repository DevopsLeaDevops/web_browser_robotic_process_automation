"""執行時的場景契約：入參校驗、獨立斷言、出參轉型與校驗（ADR 0009）。

這裡都是純 Python，不碰瀏覽器；在父程序執行，所以入參錯誤時根本不會啟動瀏覽器。
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from rpa_core.dsl import InputSpec, OutputSpec, Scenario
from rpa_runner.i18n import t
from rpa_runner.templates import Context, TemplateEvaluationError, render, render_native

__all__ = [
    "CheckResult",
    "Problem",
    "build_outputs",
    "check_inputs",
    "parse_cli_value",
    "run_verify",
]

_INTEGER: Final = re.compile(r"[-+]?\d+")
_NUMBER: Final = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True, slots=True)
class Problem:
    """入參或出參的一個問題；message 已是目前語言的文字。"""

    name: str
    message: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    """一條獨立斷言的結果。"""

    name: str
    comparison: Literal["equals", "contains", "matches", "notEmpty"]
    actual: str
    expected: str | None
    passed: bool
    error: str | None = None


def parse_cli_value(spec: InputSpec, text: str) -> object:
    """命令列 ``-i 名稱=值`` 的文字依入參型別轉換；轉不了就原樣回傳，交給校驗回報。"""
    match spec.type:
        case "integer" if _INTEGER.fullmatch(text.strip()):
            return int(text)
        case "number" if _NUMBER.fullmatch(text.strip()):
            number = float(text)
            return (
                int(number) if number.is_integer() and _INTEGER.fullmatch(text.strip()) else number
            )
        case "boolean" if text.strip().lower() in ("true", "false"):
            return text.strip().lower() == "true"
        case _:
            return text


def check_inputs(
    scenario: Scenario, values: Mapping[str, object]
) -> tuple[dict[str, object], list[Problem]]:
    """補上預設值並校驗入參；回傳 (完整入參, 問題)。"""
    problems: list[Problem] = []
    resolved: dict[str, object] = {}
    for name in values:
        if name not in scenario.inputs:
            problems.append(Problem(name, t("contract.input_unknown", name=name)))
    for name, spec in scenario.inputs.items():
        if name in values:
            value = values[name]
        elif spec.default is not None:
            value = spec.default
        else:
            problems.append(Problem(name, t("contract.input_missing", name=name)))
            continue
        for rule in spec.violations(value):
            problems.append(Problem(name, t("contract.input_invalid", name=name, rule=rule)))
        resolved[name] = value
    return resolved, problems


def run_verify(scenario: Scenario, context: Context) -> list[CheckResult]:
    """依序執行 verify 的每一條規則；某一條出錯（例如引用不存在的事實）只讓那一條失敗。"""
    results: list[CheckResult] = []
    for index, check in enumerate(scenario.verify or (), start=1):
        name = check.name or t("contract.check_name", number=index)
        comparison: Literal["equals", "contains", "matches", "notEmpty"]
        if check.equals is not None:
            comparison, raw = "equals", check.equals
        elif check.contains is not None:
            comparison, raw = "contains", check.contains
        elif check.matches is not None:
            comparison, raw = "matches", check.matches
        else:
            comparison, raw = "notEmpty", None
        try:
            actual = render(check.value, context)
            expected = render(raw, context) if raw is not None else None
        except TemplateEvaluationError as error:
            results.append(CheckResult(name, comparison, "", None, False, str(error)))
            continue
        match comparison:
            case "equals":
                passed = actual == expected
            case "contains":
                passed = expected is not None and expected in actual
            case "matches":
                passed = expected is not None and re.search(expected, actual) is not None
            case "notEmpty":
                passed = actual.strip() != ""
        results.append(CheckResult(name, comparison, actual, expected, passed))
    return results


def _convert(spec: OutputSpec, value: object) -> object:
    """依出參型別轉換：文字轉成數字或布林；清單與物件要原本就是那個型別。"""
    match spec.type:
        case "string":
            if isinstance(value, dict | list):
                return json.dumps(value, ensure_ascii=False)
            return value if isinstance(value, str) else str(value)
        case "integer" if isinstance(value, str) and _INTEGER.fullmatch(value.strip()):
            return int(value)
        case "number" if isinstance(value, str) and _NUMBER.fullmatch(value.strip()):
            return float(value)
        case "boolean" if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        case _:
            return value


def build_outputs(scenario: Scenario, context: Context) -> tuple[dict[str, object], list[Problem]]:
    """從 facts 取出出參、轉型並校驗；回傳 (出參, 問題)。"""
    outputs: dict[str, object] = {}
    problems: list[Problem] = []
    for name, spec in scenario.outputs.items():
        if spec.from_ is None:  # pragma: no cover - 校驗已保證 DSL 場景都有 from
            continue
        try:
            value = _convert(spec, render_native(spec.from_, context))
        except TemplateEvaluationError as error:
            problems.append(Problem(name, t("contract.output_error", name=name, detail=str(error))))
            continue
        for rule in spec.violations(value):
            problems.append(Problem(name, t("contract.output_invalid", name=name, rule=rule)))
        outputs[name] = value
    return outputs, problems


def check_candidate_outputs(scenario: Scenario, candidate: Mapping[str, object]) -> list[Problem]:
    """Python 腳本場景：assertion.py 寫出的候選出參要符合 outputs 宣告。"""
    problems: list[Problem] = []
    for name in candidate:
        if name not in scenario.outputs:
            problems.append(Problem(name, t("contract.output_unknown", name=name)))
    for name, spec in scenario.outputs.items():
        if name not in candidate:
            problems.append(Problem(name, t("contract.output_missing", name=name)))
            continue
        for rule in spec.violations(candidate[name]):
            problems.append(Problem(name, t("contract.output_invalid", name=name, rule=rule)))
    return problems
