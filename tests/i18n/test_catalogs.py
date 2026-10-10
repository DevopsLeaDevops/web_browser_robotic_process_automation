"""訊息目錄的一致性檢查。

- 每個套件的 locales/ 都要有三種語言，鍵與佔位符完全相同。
- click 內建文字的翻譯（click.<語言>.json）：原文必須真的出現在目前安裝的 click 裡，
  佔位符也要相同，否則 click 代入參數時會出錯。
"""

import ast
import json
import string
from pathlib import Path
from typing import cast

import click
import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ("zh-Hant", "zh-Hans", "en")
CATALOG_DIRS = sorted(
    {
        p.parent
        for pattern in ("packages/*/src/*/locales/*.json", "apps/*/src/*/locales/*.json")
        for p in ROOT.glob(pattern)
    }
)
CLICK_CATALOGS = sorted(ROOT.glob("apps/*/src/*/locales/click.*.json"))


def _load(path: Path) -> dict[str, str]:
    return cast("dict[str, str]", json.loads(path.read_text(encoding="utf-8")))


def _placeholders(text: str) -> set[str]:
    return {
        f"{field}!{conversion}" if conversion else field
        for _, field, _, conversion in string.Formatter().parse(text)
        if field is not None
    }


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_catalogs_exist() -> None:
    assert CATALOG_DIRS, "找不到任何訊息目錄"


@pytest.mark.parametrize("locales_dir", CATALOG_DIRS, ids=_rel)
def test_every_locale_has_same_keys_and_placeholders(locales_dir: Path) -> None:
    catalogs = {loc: _load(locales_dir / f"{loc}.json") for loc in LOCALES}
    reference = catalogs["zh-Hant"]
    for locale, messages in catalogs.items():
        assert messages.keys() == reference.keys(), f"{locale}.json 的鍵與 zh-Hant.json 不同"
        for key, text in messages.items():
            assert text.strip(), f"{locale}.json 的 {key} 是空字串"
            assert _placeholders(text) == _placeholders(reference[key]), (
                f"{locale}.json 的 {key} 佔位符與繁中不同"
            )


def _click_msgids() -> set[str]:
    """從目前安裝的 click 原始碼找出所有 _("...") 與 ngettext("...", "...") 的原文。"""
    found: set[str] = set()
    for source in Path(click.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            count = {"_": 1, "ngettext": 2}.get(node.func.id, 0)
            for arg in node.args[:count]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    return found


def test_click_translations_exist() -> None:
    names = {p.name for p in CLICK_CATALOGS}
    assert names == {"click.zh-Hant.json", "click.zh-Hans.json"}


@pytest.mark.parametrize("catalog", CLICK_CATALOGS, ids=_rel)
def test_click_translations_match_click_source(catalog: Path) -> None:
    msgids = _click_msgids()
    for msgid, text in _load(catalog).items():
        assert msgid in msgids, f"click 已經沒有這段原文：{msgid!r}（click 改版後請更新翻譯）"
        assert _placeholders(text) == _placeholders(msgid), f"{msgid!r} 的翻譯佔位符不同"
