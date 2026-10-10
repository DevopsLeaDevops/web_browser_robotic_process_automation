import math
from typing import cast

import pytest

from rpa_core.dsl.yaml_loader import MAX_NODES, Position, YamlLoadError, load_yaml


def test_scalars_follow_yaml_1_2_core_schema() -> None:
    data, _ = load_yaml(
        "a: yes\n"
        "b: on\n"
        "c: 2026-09-01\n"
        "d: 0123\n"
        "e: 0o17\n"
        "f: 0x1F\n"
        "g: 1.5e3\n"
        "h: -.inf\n"
        "i: ~\n"
        "j:\n"
        "k: True\n"
        "l: '1'\n"
        "m: 12:30\n"
    )

    assert data == {
        "a": "yes",  # YAML 1.1 會變成 True
        "b": "on",
        "c": "2026-09-01",  # YAML 1.1 會變成日期
        "d": 123,
        "e": 15,
        "f": 31,
        "g": 1500.0,
        "h": -math.inf,
        "i": None,
        "j": None,
        "k": True,
        "l": "1",
        "m": "12:30",  # YAML 1.1 會變成 750（六十進位）
    }


def test_nan() -> None:
    data, _ = load_yaml("x: .nan\n")
    assert isinstance(data, dict)
    value = cast("dict[str, object]", data)["x"]
    assert isinstance(value, float)
    assert math.isnan(value)


def test_explicit_str_tag_keeps_text() -> None:
    data, _ = load_yaml("x: !!str 123\n")
    assert data == {"x": "123"}


def test_positions_are_one_based() -> None:
    _, source = load_yaml("steps:\n  - id: a\n    action: goto\n")

    assert source.locate(("steps", 0, "action")) == Position(3, 13)
    assert source.locate_key(("steps", 0, "action")) == Position(3, 5)
    # 不存在的路徑往上找最近的祖先：步驟本身的開頭
    assert source.locate(("steps", 0, "url")) == Position(2, 5)
    assert source.locate_key(("steps", 0, "url")) == Position(2, 5)


def test_positions_count_characters_not_bytes() -> None:
    _, source = load_yaml("名稱: 登入\n帳號: x\n")
    assert source.locate(("名稱",)) == Position(1, 5)


def test_aliases_are_expanded() -> None:
    data, _ = load_yaml("base: &b { k: 1 }\nuse: *b\n")
    assert data == {"base": {"k": 1}, "use": {"k": 1}}


def test_merge_key_is_an_ordinary_key() -> None:
    # 不支援 YAML 1.1 的 << 合併；當作普通的鍵，校驗時會被當成不認得的欄位
    data, _ = load_yaml("a: &x { k: 1 }\nb:\n  <<: *x\n")
    assert data == {"a": {"k": 1}, "b": {"<<": {"k": 1}}}


@pytest.mark.parametrize(
    ("text", "code", "position"),
    [
        ("a: 1\na: 2\n", "duplicate_key", Position(2, 1)),
        ("x:\n  a: 1\n  b: 2\n  a: 3\n", "duplicate_key", Position(4, 3)),
        ("1: x\n", "key_not_string", Position(1, 1)),
        ("true: x\n", "key_not_string", Position(1, 1)),
        ("? [a]\n: 1\n", "key_not_string", Position(1, 3)),
        ("a: !!python/object:os.system x\n", "unsupported_tag", Position(1, 4)),
        ("a: !!binary aGk=\n", "unsupported_tag", Position(1, 4)),
        ("a: !custom x\n", "unsupported_tag", Position(1, 4)),
        ("a: !!set { x }\n", "unsupported_tag", Position(1, 4)),
        ("a: !!int abc\n", "invalid_scalar", Position(1, 4)),
        ("", "empty", Position(1, 1)),
        ("# 只有註解\n", "empty", Position(1, 1)),
        ("a: [\n", "syntax", Position(2, 1)),
        ("a: b: c\n", "syntax", Position(1, 5)),
        ("--- a\n--- b\n", "syntax", Position(2, 1)),
        ("x: &a [*a]\n", "recursive", Position(1, 4)),
    ],
)
def test_errors_have_code_and_position(text: str, code: str, position: Position) -> None:
    with pytest.raises(YamlLoadError) as caught:
        load_yaml(text)

    assert caught.value.code == code
    assert caught.value.position == position


def test_duplicate_key_reports_first_line() -> None:
    with pytest.raises(YamlLoadError) as caught:
        load_yaml("steps:\n  - id: a\n    id: b\n")

    assert caught.value.path == ("steps", 0, "id")
    assert caught.value.params == {"key": "id", "line": 2}


def test_alias_bomb_is_rejected() -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    for level in range(1, 7):
        refs = ", ".join([f"*a{level - 1}"] * 10)
        lines.append(f"a{level}: &a{level} [{refs}]")

    with pytest.raises(YamlLoadError) as caught:
        load_yaml("\n".join(lines) + "\n")

    assert caught.value.code == "too_large"
    assert caught.value.params == {"limit": MAX_NODES}
