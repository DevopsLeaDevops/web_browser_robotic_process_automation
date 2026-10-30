"""DSL 的擴充：場景用到哪些、裝置缺哪些（M7a）。"""

from pathlib import Path

from rpa_core.dsl import validate_text
from rpa_core.dsl.features import FEATURES, data_features, missing_features, scenario_features

ROOT = Path(__file__).resolve().parents[4]

HEAD = """\
schemaVersion: 1
id: demo
name: 示範
steps:
"""


def features_of(steps: str) -> frozenset[str]:
    checked = validate_text(HEAD + steps)
    assert checked.scenario is not None, checked.issues
    return scenario_features(checked.scenario)


def test_scenarios_without_iframes_need_nothing() -> None:
    for path in sorted((ROOT / "scenarios" / "demo").glob("*.yaml")):
        checked = validate_text(path.read_text(encoding="utf-8"))
        assert checked.scenario is not None, path
        assert scenario_features(checked.scenario) == frozenset(), path


def test_frame_and_any_frame_are_found_anywhere() -> None:
    assert features_of(
        "  - id: a\n    action: click\n    target: { css: b, frame: { css: f } }\n"
    ) == {"frame"}
    assert features_of(
        "  - id: a\n    action: click\n    target: { text: b, anyFrame: true }\n"
    ) == {"anyFrame"}
    # 備用定位器、within、extract 的 fields 裡也算
    assert features_of(
        "  - id: a\n    action: click\n"
        "    target: { css: b, fallback: [{ css: c, frame: { css: f, anyFrame: true } }] }\n"
    ) == {"frame", "anyFrame"}
    assert features_of(
        "  - id: a\n    action: extract\n    as: row\n    target: { css: tr }\n"
        "    fields:\n      name: { target: { css: td, frame: { css: f } } }\n"
    ) == {"frame"}
    example = (ROOT / "scenarios" / "examples" / "iframe-form.yaml").read_text(encoding="utf-8")
    checked = validate_text(example)
    assert checked.scenario is not None
    assert scenario_features(checked.scenario) == {"frame"}


def test_tabs_are_found() -> None:
    """新分頁（M7b）：步驟的 popup 與 page。"""
    assert features_of(
        "  - id: a\n    action: click\n    target: { text: 明細 }\n    popup: items\n"
        "  - id: b\n    action: click\n    page: items\n    target: { text: 儲存 }\n"
    ) == {"page", "popup"}
    example = (ROOT / "scenarios" / "examples" / "popup-form.yaml").read_text(encoding="utf-8")
    checked = validate_text(example)
    assert checked.scenario is not None
    assert scenario_features(checked.scenario) == {"page", "popup"}
    dynamic = validate_text(example.replace("default: '455590002'", "default: '{{random:7:7}}'"))
    assert dynamic.scenario is not None
    assert scenario_features(dynamic.scenario) == {"page", "popup", "dynamicValues"}


def test_data_features_reads_raw_settings() -> None:
    """角色的登入檢查與自動登入步驟是原始的 dict。"""
    assert data_features({"check": {"testId": "me"}, "steps": []}) == frozenset()
    settings = {
        "check": {"text": "登出", "anyFrame": True},
        "steps": [
            {"id": "a", "action": "fill", "target": {"label": "帳號", "frame": {"css": "f"}}}
        ],
    }
    assert data_features(settings) == {"frame", "anyFrame"}
    # frame 不是定位器（例如入參的值）時不算
    assert data_features({"default": {"frame": "x"}, "anyFrame": "yes"}) == frozenset()


def test_missing_features() -> None:
    assert {
        "frame",
        "anyFrame",
        "page",
        "popup",
        "dynamicValues",
        "upload",
        "fileInputs",
        "pythonNodes",
        "jsonInputs",
        "fileOutputs",
        "download",
    } == FEATURES
    # M7a 之前的 App 沒有回報 features：一個都不懂
    assert missing_features({"frame"}, None) == ["frame"]
    assert missing_features({"anyFrame", "frame"}, "frame") == ["anyFrame", "frame"]
    assert missing_features({"frame"}, ["frame", "anyFrame"]) == []
    assert missing_features(set(), None) == []
