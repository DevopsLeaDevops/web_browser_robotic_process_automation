"""Python 節點（ADR 0020）：script 的兩種模式、files、platforms、array／object 入參與擴充。"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import Scenario, validate_file, validate_text
from rpa_core.dsl.features import JSON_INPUTS, PYTHON_NODES, input_features, scenario_features
from rpa_core.dsl.files import FileValueError, file_values
from rpa_core.dsl.sources import scenario_digest, scenario_sources
from rpa_core.i18n import use_locale
from rpa_core.workflow import Workflow, check_workflow

HEADER = "schemaVersion: 1\nid: node\nname: Python 節點\n"
RUNTIME = "script:\n  runtime: '1'\n  automation: automation.py\n"
VERIFY = "verify:\n  - { value: '{{ facts.total }}', matches: '^[0-9]' }\n"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def issues(text: str) -> list[tuple[str, str]]:
    return [(i.code, i.field) for i in validate_text(text).issues]


def scenario(text: str) -> Scenario:
    result = validate_text(text)
    assert result.scenario is not None, result.issues
    return result.scenario


# ---------------------------------------------------------------- 運行環境模式


def test_runtime_node_without_outputs_needs_no_assertion() -> None:
    node = scenario(HEADER + RUNTIME)
    assert node.script is not None
    assert node.script.uses_runtime
    assert node.script.assertion is None


def test_runtime_node_with_verify_and_outputs_from_facts() -> None:
    text = HEADER + "outputs:\n  total: { type: number, from: '{{ facts.total }}' }\n" + RUNTIME
    node = scenario(text + VERIFY)
    assert node.verify is not None
    # 事實由腳本寫出：校驗時不知道有哪些，不報「沒有 extract」
    assert issues(text + VERIFY) == []


def test_runtime_node_with_assertion_like_before() -> None:
    text = (
        HEADER + "outputs:\n  total: { type: number }\n" + RUNTIME + "  assertion: assertion.py\n"
    )
    assert issues(text) == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "outputs:\n  total: { type: number }\n" + RUNTIME,
            [("script.assertion_or_verify", "outputs")],
        ),
        (
            "outputs:\n  total: { type: number }\n" + RUNTIME + VERIFY,
            [("output.from_required", "outputs.total")],
        ),
        (
            "outputs:\n  total: { type: number, from: '{{ facts.total }}' }\n"
            + RUNTIME
            + "  assertion: assertion.py\n",
            [("script.output_from_not_allowed", "outputs.total.from")],
        ),
        (
            RUNTIME + "  assertion: assertion.py\n" + VERIFY,
            [("script.assertion_and_verify", "verify")],
        ),
        (
            "browser: { engine: firefox }\n" + RUNTIME,
            [("script.runtime_no_browser", "browser")],
        ),
        ("login: { role: clerk }\n" + RUNTIME, [("script.runtime_no_browser", "login")]),
        (RUNTIME.replace("'1'", "'2'"), [("choice", "script.runtime")]),
    ],
)
def test_runtime_node_rules(body: str, expected: list[tuple[str, str]]) -> None:
    found = issues(HEADER + body)
    assert found[: len(expected)] == expected, found


def test_runtime_message_names_the_field() -> None:
    result = validate_text(HEADER + "browser: { engine: firefox }\n" + RUNTIME)
    assert "不能寫 browser" in result.issues[0].message


# ---------------------------------------------------------------- 相容模式


def test_compatible_node_still_needs_assertion() -> None:
    found = issues(HEADER + "script: { automation: a.py }\n")
    assert found == [("script.assertion_required", "script")]


def test_compatible_node_cannot_use_verify() -> None:
    text = HEADER + "script: { automation: a.py, assertion: b.py }\n" + VERIFY
    assert ("script.verify_not_allowed", "verify") in issues(text)


def test_existing_script_scenarios_keep_their_digest(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[4] / "scenarios" / "demo" / "ba-001-script"
    result = validate_file(demo / "scenario.yaml")
    assert result.scenario is not None
    assert scenario_sources(demo / "scenario.yaml", result.scenario) == [
        "scenario.yaml",
        "automation.py",
        "assertion.py",
    ]
    assert scenario_features(result.scenario) == frozenset()


# ---------------------------------------------------------------- files、platforms


def test_files_are_part_of_the_version(tmp_path: Path) -> None:
    (tmp_path / "automation.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "query.sql").write_text("select 1;\n", encoding="utf-8")
    path = tmp_path / "scenario.yaml"
    path.write_text(
        HEADER + RUNTIME + "  files: [lib/helpers.py, query.sql]\n  platforms: [windows, linux]\n",
        encoding="utf-8",
    )
    result = validate_file(path)
    assert result.scenario is not None, result.issues
    assert scenario_sources(path, result.scenario) == [
        "scenario.yaml",
        "automation.py",
        "lib/helpers.py",
        "query.sql",
    ]
    before = scenario_digest(path, result.scenario)
    (tmp_path / "query.sql").write_text("select 2;\n", encoding="utf-8")
    assert scenario_digest(path, result.scenario) != before


def test_listed_files_must_exist(tmp_path: Path) -> None:
    (tmp_path / "automation.py").write_text("", encoding="utf-8")
    path = tmp_path / "scenario.yaml"
    path.write_text(HEADER + RUNTIME + "  files: [helpers.py]\n", encoding="utf-8")
    result = validate_file(path)
    assert [(i.code, i.field) for i in result.issues] == [
        ("script.file_missing", "script.files[0]")
    ]


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ("[../x.py]", "format.script_file"),
        ("[/etc/passwd]", "format.script_file"),
        ("[files/template.xlsx]", "script.file_in_attachments"),
        ("[a.json, a.json]", "script.file_duplicate"),
        ("[automation.py]", "script.file_duplicate"),
    ],
)
def test_bad_files(files: str, code: str) -> None:
    found = issues(HEADER + RUNTIME + f"  files: {files}\n")
    assert found, files
    assert found[0][0] == code, found


def test_platforms() -> None:
    assert issues(HEADER + RUNTIME + "  platforms: [macos]\n") == []
    assert issues(HEADER + RUNTIME + "  platforms: [macos, macos]\n")[0][0] == (
        "script.platform_duplicate"
    )
    assert issues(HEADER + RUNTIME + "  platforms: [android]\n")[0][0] == "choice"


# ---------------------------------------------------------------- array／object 入參


def test_array_and_object_inputs() -> None:
    node = scenario(
        HEADER
        + "inputs:\n"
        + "  months: { type: array, default: ['2026-09', '2026-10'] }\n"
        + "  options: { type: object, default: { sheet: 銷售 } }\n"
        + RUNTIME
    )
    assert node.inputs["months"].check_value(["2026-10"]) == []
    assert node.inputs["months"].check_value({"a": 1}) == ["type: array"]
    assert node.inputs["options"].check_value({"sheet": "x"}) == []
    assert node.inputs["options"].check_value([1]) == ["type: object"]


def test_dsl_steps_can_use_object_inputs() -> None:
    text = (
        HEADER
        + "inputs:\n  record: { type: object }\n"
        + "steps:\n"
        + "  - { id: open, action: goto, url: 'https://example.test/{{ inputs.record.id }}' }\n"
    )
    assert issues(text) == []


# ---------------------------------------------------------------- 擴充與組合場景


def test_features_of_python_nodes() -> None:
    assert scenario_features(scenario(HEADER + RUNTIME)) == {PYTHON_NODES}
    plain = scenario(
        HEADER + "inputs:\n  x: { type: object }\nscript: { automation: a.py, assertion: b.py }\n"
    )
    assert scenario_features(plain) == {JSON_INPUTS}


def test_browser_and_python_nodes_in_one_composite() -> None:
    web = scenario(
        "schemaVersion: 1\nid: web\nname: 網頁\n"
        "outputs:\n  rows: { type: array, from: '{{ facts.rows }}' }\n"
        "steps:\n"
        "  - { id: open, action: goto, url: https://example.test/ }\n"
        "  - id: read\n    action: extract\n    target: { css: table }\n    as: rows\n"
        "    fields:\n      first: { target: { css: td } }\n"
        "verify:\n  - { value: '{{ facts.rows }}', notEmpty: true }\n"
    )
    node = scenario(
        HEADER
        + "inputs:\n  rows: { type: array }\n"
        + "outputs:\n  summary: { type: object, from: '{{ facts.summary }}' }\n"
        + RUNTIME
        + VERIFY
    )
    workflow = Workflow.model_validate(
        {
            "version": 2,
            "mode": "dag",
            "nodes": [
                {"id": "web", "sceneId": "web", "revision": 1},
                {"id": "py", "sceneId": "node", "revision": 1, "inputs": {"rows": {"auto": True}}},
            ],
            "edges": [{"source": "web", "target": "py"}],
        }
    )
    assert check_workflow(workflow, {"web": web, "py": node}) == []


# ---------------------------------------------------------------- 檔案：download 步驟與 file 出參


DOWNLOAD = """\
schemaVersion: 1
id: dl
name: 下載
outputs:
  report: { type: file, from: '{{ facts.report }}' }
browser: { baseUrl: http://127.0.0.1:8765 }
steps:
  - { id: open, action: goto, url: /download }
  - id: export
    action: download
    target: { role: button, name: 匯出 CSV }
    as: report
    fileName: '銷售-{{ facts.month }}.csv'
  - { id: month, action: extract, target: { css: h1 }, as: month }
verify:
  - { value: '{{ facts.report.name }}', notEmpty: true }
"""


def test_download_step_produces_a_fact_for_file_outputs() -> None:
    checked = validate_text(DOWNLOAD.replace("    fileName: '銷售-{{ facts.month }}.csv'\n", ""))
    assert checked.ok, checked.issues
    assert checked.scenario is not None
    assert scenario_features(checked.scenario) == {"download", "fileOutputs"}
    # fileName 只能用前面步驟產生的事實；download 與 extract 的 as 不能重複
    later = validate_text(DOWNLOAD)
    assert [issue.code for issue in later.issues] == ["template.fact_not_yet"]
    twice = validate_text(DOWNLOAD.replace("as: month", "as: report"))
    assert "extract.duplicate_as" in [issue.code for issue in twice.issues]


def test_file_outputs_need_the_runtime_in_python_nodes() -> None:
    compatible = validate_text(
        "schemaVersion: 1\nid: s\nname: s\noutputs:\n  f: { type: file }\n"
        "script: { automation: a.py, assertion: b.py }\n"
    )
    assert [issue.code for issue in compatible.issues] == ["script.file_output"]
    runtime = validate_text(
        "schemaVersion: 1\nid: s\nname: s\noutputs:\n  f: { type: file }\n"
        "script: { runtime: '1', automation: a.py, assertion: b.py }\n"
    )
    assert runtime.ok, runtime.issues


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        (
            {"workspace": "downloads/報表.csv", "name": "報表.csv", "size": 3, "sha256": "a" * 64},
            True,
        ),
        ({"workspace": ".outputs/run-1/x.xlsx"}, True),
        ({"workspace": "../x.csv"}, False),
        ({"workspace": "/etc/passwd"}, False),
        ({"workspace": "C:/x.csv"}, False),
        ({"workspace": "a\\b.csv"}, False),
        ({"workspace": "a.csv", "path": "/x"}, False),
    ],
)
def test_workspace_file_values(value: dict[str, object], ok: bool) -> None:
    """上游節點產出的檔案（ADR 0020）：共用工作資料夾裡的相對路徑。"""
    if not ok:
        with pytest.raises(FileValueError):
            file_values(value, multiple=False)
        return
    [item] = file_values(value, multiple=False)
    assert item.source == "workspace"
    assert item.to_json() == value
    assert input_features({"report": value}) == {"fileOutputs"}
