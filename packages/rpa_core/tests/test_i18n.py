import sys
from pathlib import Path

import pytest

from rpa_core.i18n import (
    DEFAULT_LOCALE,
    LOCALES,
    NATIVE_NAMES,
    Catalog,
    get_locale,
    parse_locale,
    use_locale,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("zh-Hant", "zh-Hant"),
        ("zh-hant", "zh-Hant"),
        ("zh_TW", "zh-Hant"),
        ("zh-TW.UTF-8", "zh-Hant"),
        ("zh-HK", "zh-Hant"),
        ("zh-Hant-TW", "zh-Hant"),
        ("zh-Hans", "zh-Hans"),
        ("zh_CN", "zh-Hans"),
        ("zh-SG", "zh-Hans"),
        ("en", "en"),
        ("EN-us", "en"),
        ("en_GB.UTF-8", "en"),
        # 只寫 zh 無法判斷繁簡
        ("zh", None),
        ("fr", None),
        ("", None),
        ("  ", None),
    ],
)
def test_parse_locale(value: str, expected: str | None) -> None:
    assert parse_locale(value) == expected


def test_default_is_traditional_chinese() -> None:
    assert DEFAULT_LOCALE == "zh-Hant"
    assert get_locale() == "zh-Hant"
    assert set(NATIVE_NAMES) == set(LOCALES)


def test_use_locale_restores_previous_locale() -> None:
    with use_locale("en"):
        assert get_locale() == "en"
        with use_locale("zh-Hans"):
            assert get_locale() == "zh-Hans"
        assert get_locale() == "en"
    assert get_locale() == DEFAULT_LOCALE


@pytest.fixture
def demo_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Catalog:
    """在暫存目錄建立一個只有繁中與英文的假套件。"""
    locales = tmp_path / "demo_pkg" / "locales"
    locales.mkdir(parents=True)
    (tmp_path / "demo_pkg" / "__init__.py").write_text("", encoding="utf-8")
    (locales / "zh-Hant.json").write_text(
        '{"greet": "你好，{name}", "only.hant": "只有繁中", "braces": "{{字面}}"}',
        encoding="utf-8",
    )
    (locales / "en.json").write_text('{"greet": "Hello, {name}"}', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    # 每個測試的暫存目錄不同，要讓 Python 重新匯入，不能沿用上一個測試的 demo_pkg
    monkeypatch.delitem(sys.modules, "demo_pkg", raising=False)
    return Catalog("demo_pkg")


def test_catalog_formats_message_in_current_locale(demo_catalog: Catalog) -> None:
    assert demo_catalog("greet", name="Ann") == "你好，Ann"
    with use_locale("en"):
        assert demo_catalog("greet", name="Ann") == "Hello, Ann"


def test_catalog_falls_back_to_default_locale(demo_catalog: Catalog) -> None:
    with use_locale("en"):
        assert demo_catalog("only.hant") == "只有繁中"


def test_catalog_keeps_escaped_braces(demo_catalog: Catalog) -> None:
    assert demo_catalog("braces") == "{字面}"


def test_catalog_rejects_unknown_key(demo_catalog: Catalog) -> None:
    with pytest.raises(KeyError, match="missing"):
        demo_catalog("missing")
