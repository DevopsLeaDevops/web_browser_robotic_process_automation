"""M7c：檔案入參、upload 步驟、場景附件。"""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import Issue, UploadStep, format_issue, validate_file, validate_text
from rpa_core.dsl.contract import spec_json_schema
from rpa_core.dsl.features import FILE_INPUTS, UPLOAD, input_features, scenario_features
from rpa_core.dsl.files import (
    FileMeta,
    FileValue,
    FileValueError,
    accept_rule_ok,
    accepts,
    attachment_names,
    clean_name,
    file_meta,
    file_values,
    format_size,
    inside_folders,
    parse_size,
    uploaded_ids,
)
from rpa_core.dsl.sources import attachment_files, scenario_digest, scenario_sources
from rpa_core.i18n import use_locale

FILE_ID = "0123456789abcdef0123456789abcdef"
HEADER = "schemaVersion: 1\nid: demo\nname: 示範\n"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def issues_of(text: str) -> list[Issue]:
    result = validate_text(text)
    assert result.scenario is None, "應該有問題"
    return list(result.issues)


def messages(text: str) -> list[str]:
    return [format_issue(issue) for issue in issues_of(text)]


def upload_scene(inputs: str, step: str) -> str:
    return (
        HEADER
        + "inputs:\n"
        + inputs
        + "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n"
        + step
    )


# ---------------------------------------------------------------- 值的寫法


def test_three_kinds_of_file_values() -> None:
    upload = {"file": FILE_ID, "name": "訂單匯入.xlsx", "size": 20, "sha256": "a" * 64}
    assert file_values(upload, multiple=False) == [
        FileValue("upload", FILE_ID, "訂單匯入.xlsx", 20, "a" * 64)
    ]
    assert file_values("files/orders.xlsx", multiple=False) == [
        FileValue("attachment", "files/orders.xlsx")
    ]
    named = {"attachment": "files/orders.xlsx", "name": "訂單範本.xlsx"}
    assert file_values(named, multiple=False)[0].display_name == "訂單範本.xlsx"
    path = {"path": "D:\\共用\\orders-{{today}}.xlsx"}
    assert file_values(path, multiple=False) == [FileValue("path", path["path"])]
    assert file_values(path, multiple=False)[0].display_name == "orders-{{today}}.xlsx"
    # 寫回 JSON 時保留原本的寫法
    for value in (upload, "files/orders.xlsx", named, path):
        assert file_values(value, multiple=False)[0].to_json() == value


def test_multiple_values_are_lists() -> None:
    values = file_values(["files/a.png", {"file": FILE_ID, "name": "b.png"}], multiple=True)
    assert [item.source for item in values] == ["attachment", "upload"]
    assert file_values([], multiple=True) == []
    with pytest.raises(FileValueError) as single:
        file_values(["files/a.png"], multiple=False)
    assert single.value.code == "not_multiple"
    with pytest.raises(FileValueError) as listed:
        file_values("files/a.png", multiple=True)
    assert listed.value.code == "multiple_list"
    with pytest.raises(FileValueError) as many:
        file_values(["files/a.png"] * 101, multiple=True)
    assert many.value.code == "too_many"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("訂單.xlsx", "attachment_path"),
        ("files/../secret.txt", "attachment_path"),
        ("files/a/b.png", "attachment_path"),
        ({"file": "abc", "name": "a"}, "id"),
        ({"file": FILE_ID, "name": ""}, "name"),
        ({"file": FILE_ID, "extra": 1}, "shape"),
        ({"path": " "}, "path"),
        ({"attachment": "C:/x.xlsx"}, "attachment_path"),
        (12, "shape"),
        ({}, "shape"),
    ],
)
def test_wrong_file_values(value: object, code: str) -> None:
    with pytest.raises(FileValueError) as error:
        file_values(value, multiple=False)
    assert error.value.code == code
    assert error.value.message


def test_references_in_a_set_of_inputs() -> None:
    other = "f" * 32
    values: list[object] = [
        {"file": FILE_ID, "name": "a"},
        [{"file": other, "name": "b"}, "files/x.png"],
        {"attachment": "files/y.png"},
        "普通的文字",
        {"file": FILE_ID, "name": "again"},
    ]
    assert uploaded_ids(values) == [FILE_ID, other]
    assert attachment_names(values) == ["files/x.png", "files/y.png"]


def test_clean_name() -> None:
    assert clean_name("訂單匯入.xlsx") == "訂單匯入.xlsx"
    assert clean_name("C:\\Users\\me\\報表.xlsx") == "報表.xlsx"
    assert clean_name("../../etc/passwd") == "passwd"
    assert clean_name('a<b>:"c|d?*.txt') == "a_b___c_d__.txt"
    assert clean_name("CON.txt") == "_CON.txt"
    assert clean_name("nul") == "_nul"
    assert clean_name("結尾. ") == "結尾"
    assert clean_name("..") == "file"
    # macOS 的組字方式（NFD）轉成 NFC
    assert clean_name("ブ.png") == "ブ.png"
    long = "長" * 100 + ".xlsx"
    cleaned = clean_name(long)
    assert len(cleaned.encode()) <= 200
    assert cleaned.endswith(".xlsx")


def test_sizes() -> None:
    assert parse_size("20MB") == 20 * 1024 * 1024
    assert parse_size(" 1.5 kb ") == 1536
    assert parse_size("512B") == 512
    for wrong in ("20", "MB", "20 TB", "-1MB"):
        with pytest.raises(FileValueError) as error:
            parse_size(wrong)
        assert error.value.code == "size_format"
    with pytest.raises(FileValueError) as error:
        parse_size("2GB")
    assert error.value.code == "size_range"
    assert format_size(20 * 1024 * 1024) == "20 MB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(10) == "10 B"


def test_accept_rules() -> None:
    assert accept_rule_ok(".xlsx")
    assert accept_rule_ok("image/*")
    assert accept_rule_ok("application/vnd.ms-excel")
    assert not accept_rule_ok("xlsx")
    assert not accept_rule_ok("image/")
    assert accepts([".xlsx", ".xls"], "訂單.XLSX")
    assert not accepts([".xlsx"], "商品.png")
    assert accepts(["image/*"], "商品.png")
    assert accepts(["image/png"], "商品.png")
    assert not accepts(["image/*"], "訂單.xlsx")
    assert accepts(None, "anything")


def test_file_meta_and_allowed_folders(tmp_path: Path) -> None:
    allowed = tmp_path / "share"
    allowed.mkdir()
    inside = allowed / "a.txt"
    inside.write_bytes(b"hello")
    outside = tmp_path / "b.txt"
    outside.write_bytes(b"x")
    assert file_meta(inside, "a.txt") == FileMeta("a.txt", 5, hashlib.sha256(b"hello").hexdigest())
    assert inside_folders(inside, [allowed])
    assert not inside_folders(outside, [allowed])
    assert not inside_folders(allowed / "missing.txt", [allowed])
    # 符號連結指到外面：以解開之後的位置判斷
    link = allowed / "link.txt"
    link.symlink_to(outside)
    assert not inside_folders(link, [allowed])
    assert not inside_folders(inside, [])


# ---------------------------------------------------------------- 入參


def test_file_input_fields() -> None:
    text = upload_scene(
        "  orderFile: { type: file, accept: [.xlsx, .xls], maxSize: 20MB, description: 訂單 }\n"
        "  photos: { type: file, multiple: true, accept: [image/*], default: [files/a.png] }\n"
        "  daily: { type: file, default: { path: 'D:\\share\\{{today}}.xlsx' } }\n",
        "  - { id: up, action: upload, target: { label: 匯入檔案 },"
        ' files: "{{ inputs.orderFile }}" }\n',
    )
    result = validate_text(text)
    assert result.scenario is not None, [format_issue(i) for i in result.issues]
    spec = result.scenario.inputs["orderFile"]
    assert spec.type == "file"
    assert spec.max_bytes == 20 * 1024 * 1024
    assert spec.multiple is None
    assert result.scenario.inputs["photos"].multiple is True
    schema = spec_json_schema(spec)
    assert "type" not in schema
    assert schema["x-rpa-file"] == {
        "multiple": False,
        "accept": [".xlsx", ".xls"],
        "maxSize": "20MB",
    }
    assert spec.check_value({"file": FILE_ID, "name": "a.xlsx"}) == []
    assert spec.check_value(["files/a.png"]) == [
        "這個入參一次只能有一個檔案；要多個檔案請在入參加上 multiple: true"
    ]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("{ type: string, accept: [.xlsx] }", "accept 不適用於 type: string"),
        ("{ type: integer, multiple: true }", "multiple 不適用於 type: integer"),
        ("{ type: file, enum: [a] }", "enum 不適用於 type: file"),
        ("{ type: file, minLength: 1 }", "minLength 不適用於 type: file"),
        ("{ type: file, accept: [xlsx] }", "xlsx 不是 accept 的寫法"),
        ("{ type: file, maxSize: 20 MiB }", "maxSize 寫錯了：20 MiB 不是大小的寫法"),
        ("{ type: file, maxSize: 20 }", "必須是字串"),
        ("{ type: file, default: 訂單.xlsx }", "不是場景附件的路徑"),
        (f"{{ type: file, default: {{ file: {FILE_ID}, name: a }} }}", "預設值不能是上傳檔"),
        ("{ type: file, default: { path: 'x-{{tody}}' } }", "tody"),
    ],
)
def test_file_input_rules(spec: str, expected: str) -> None:
    text = (
        HEADER + f"inputs:\n  f: {spec}\nsteps:\n  - {{ id: a, action: goto, url: about:blank }}\n"
    )
    found = messages(text)
    assert any(expected in message for message in found), found


# ---------------------------------------------------------------- upload 步驟


def test_upload_step_modes() -> None:
    inputs = "  a: { type: file }\n  b: { type: file, multiple: true }\n"
    text = upload_scene(
        inputs,
        '  - { id: t, action: upload, target: { css: "input[type=file]" },'
        ' files: "{{ inputs.a }}" }\n'
        "  - { id: g, action: upload, trigger: { role: button, name: 選擇圖片 },"
        ' files: ["{{inputs.a}}", "{{ inputs.b }}"] }\n'
        '  - { id: d, action: upload, dropzone: { text: 拖到這裡 }, files: "{{ inputs.b }}" }\n'
        "  - { id: c, action: upload, target: { css: input }, files: [] }\n",
    )
    result = validate_text(text)
    assert result.scenario is not None, [format_issue(i) for i in result.issues]
    steps = [step for step in result.scenario.steps or () if isinstance(step, UploadStep)]
    assert [step.files for step in steps] == [
        ["{{ inputs.a }}"],
        ["{{inputs.a}}", "{{ inputs.b }}"],
        ["{{ inputs.b }}"],
        [],
    ]
    assert scenario_features(result.scenario) >= {UPLOAD, FILE_INPUTS}


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            '{ id: u, action: upload, files: "{{ inputs.a }}" }',
            "要指定其中一個欄位：target, trigger, dropzone",
        ),
        (
            "{ id: u, action: upload, target: { css: x }, trigger: { css: y },"
            ' files: "{{ inputs.a }}" }',
            "只能指定其中一個欄位",
        ),
        ("{ id: u, action: upload, target: { css: x }, files: 訂單.xlsx }", "要寫成"),
        (
            '{ id: u, action: upload, target: { css: x }, files: "{{ inputs.a }}.xlsx" }',
            "要寫成",
        ),
        ("{ id: u, action: upload, trigger: { css: x }, files: [] }", "只能搭配 target"),
        ('{ id: u, action: upload, target: { css: x }, files: "{{ inputs.n }}" }', "type: string"),
        (
            '{ id: u, action: upload, target: { css: x }, files: "{{ inputs.zz }}" }',
            "沒有宣告的入參 zz",
        ),
        (
            '{ id: u, action: upload, target: { css: x }, files: "{{ inputs.a }}", popup: p }',
            "popup",
        ),
    ],
)
def test_upload_step_rules(step: str, expected: str) -> None:
    text = upload_scene("  a: { type: file }\n  n: { type: string }\n", f"  - {step}\n")
    found = messages(text)
    assert any(expected in message for message in found), found


def test_compatible_python_nodes_cannot_have_file_inputs() -> None:
    text = (
        HEADER
        + "inputs:\n  f: { type: file }\n"
        + "script: { automation: automation.py, assertion: assertion.py }\n"
    )
    assert any("沒有 runtime 的 Python 節點不能有檔案入參（f）" in m for m in messages(text))


def test_runtime_python_nodes_can_have_file_inputs() -> None:
    text = (
        HEADER
        + "inputs:\n  f: { type: file }\n"
        + "script: { runtime: '1', automation: automation.py }\n"
    )
    assert validate_text(text).ok


def test_input_features_for_file_values() -> None:
    assert FILE_INPUTS in input_features({"a": {"file": FILE_ID, "name": "a"}})
    assert FILE_INPUTS in input_features({"a": ["files/x.png"]})
    assert FILE_INPUTS not in input_features({"a": "text"})


# ---------------------------------------------------------------- 場景附件


def write_scene(folder: Path, defaults: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "scenario.yaml"
    path.write_text(
        upload_scene(
            f"  f: {{ type: file{defaults} }}\n",
            '  - { id: u, action: upload, target: { css: input }, files: "{{ inputs.f }}" }\n',
        ),
        encoding="utf-8",
    )
    return path


def test_attachments_are_part_of_the_scene(tmp_path: Path) -> None:
    path = write_scene(tmp_path / "scene", ", default: files/b.xlsx")
    scenario = validate_file(path).scenario
    assert scenario is not None
    without = scenario_digest(path, scenario)
    assert scenario_sources(path, scenario) == ["scenario.yaml"]
    files = path.parent / "files"
    files.mkdir()
    (files / "b.xlsx").write_bytes(b"b")
    (files / "a.png").write_bytes(b"a")
    (files / "nested").mkdir()
    assert attachment_files(path.parent) == ["files/a.png", "files/b.xlsx"]
    assert scenario_sources(path, scenario) == ["scenario.yaml", "files/a.png", "files/b.xlsx"]
    with_files = scenario_digest(path, scenario)
    assert with_files != without
    (files / "a.png").write_bytes(b"changed")
    assert scenario_digest(path, scenario) != with_files


def test_digest_without_attachments_is_unchanged(tmp_path: Path) -> None:
    """沒有附件的場景雜湊和 M7c 之前相同（既有的驗證與發布紀錄要對得上）。"""
    path = write_scene(tmp_path / "scene")
    scenario = validate_file(path).scenario
    assert scenario is not None
    content = path.read_bytes()
    expected = hashlib.sha256(b"scenario.yaml\0" + content + b"\0").hexdigest()
    assert scenario_digest(path, scenario) == expected
