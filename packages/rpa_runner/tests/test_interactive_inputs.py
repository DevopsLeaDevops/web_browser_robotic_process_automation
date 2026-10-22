"""互動子程序在開瀏覽器的裝置求值；重載保留先前解析的字面文字。"""

import argparse
import json
from datetime import datetime, tzinfo
from pathlib import Path

import pytest

from rpa_core.dsl.dynamic import escape
from rpa_runner import contract, debug, record


class RecorderTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "RecorderTime":
        return cls(2035, 1, 2, 3, 4, 5, tzinfo=tz)


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(contract, "datetime", RecorderTime)
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text(
        "schemaVersion: 1\nid: interactive\nname: 互動入參\n"
        "inputs:\n"
        "  title: { default: '{{today}}' }\n"
        "  tomorrow: { default: '{{today+1}}' }\n"
        "  quantity: { type: integer, default: '{{random:7:7}}' }\n"
        "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n",
        encoding="utf-8",
    )
    inputs = tmp_path / "input.json"
    inputs.write_text("{}", encoding="utf-8")
    return scenario, inputs


@pytest.mark.parametrize("module", ["debug", "record"])
def test_inputs_use_the_recorders_clock_and_evaluate_once(
    files: tuple[Path, Path], module: str
) -> None:
    scenario, inputs = files
    if module == "debug":
        _, resolved = debug._Session._load(scenario, inputs)  # pyright: ignore[reportPrivateUsage]
    else:
        _, resolved = record._load(  # pyright: ignore[reportPrivateUsage]
            argparse.Namespace(scenario=str(scenario), input=str(inputs))
        )
        assert json.loads(inputs.read_text(encoding="utf-8")) == {}
    assert resolved == {"title": "2035-01-02", "tomorrow": "2035-01-03", "quantity": 7}


def test_debug_reload_preserves_literals_and_existing_values(files: tuple[Path, Path]) -> None:
    scenario, inputs = files
    inputs.write_text(json.dumps({"title": escape("{{today}}"), "quantity": 9}), encoding="utf-8")
    session = object.__new__(debug._Session)  # pyright: ignore[reportPrivateUsage]
    existing: dict[str, object] = {"title": "{{today}}", "quantity": 9}
    session.inputs = existing
    first = session.load(str(scenario), str(inputs))
    expected = {"title": "{{today}}", "tomorrow": "2035-01-03", "quantity": 9}
    assert first["inputs"] == expected
    inputs.write_text(
        json.dumps({name: escape(value) for name, value in expected.items()}), encoding="utf-8"
    )
    assert session.load(str(scenario), str(inputs))["inputs"] == expected


def test_debug_reload_checks_new_dynamic_defaults(files: tuple[Path, Path]) -> None:
    scenario, inputs = files
    scenario.write_text(
        scenario.read_text().replace(
            "type: integer, default: '{{random:7:7}}'",
            "type: integer, minimum: 10, default: '{{random:7:7}}'",
        ),
        encoding="utf-8",
    )
    session = object.__new__(debug._Session)  # pyright: ignore[reportPrivateUsage]
    existing: dict[str, object] = {"title": "原本的值"}
    session.inputs = existing
    with pytest.raises(ValueError, match="minimum: 10"):
        session.load(str(scenario), str(inputs))
    assert session.inputs == {"title": "原本的值"}


@pytest.mark.parametrize("module", ["debug", "record"])
def test_interactive_start_rejects_invalid_inputs(files: tuple[Path, Path], module: str) -> None:
    scenario, inputs = files
    inputs.write_text('{"quantity": "invalid"}', encoding="utf-8")
    if module == "debug":
        with pytest.raises(ValueError, match="quantity"):
            debug._Session._load(scenario, inputs)  # pyright: ignore[reportPrivateUsage]
    else:
        with pytest.raises(ValueError, match="quantity"):
            record._load(  # pyright: ignore[reportPrivateUsage]
                argparse.Namespace(scenario=str(scenario), input=str(inputs))
            )
