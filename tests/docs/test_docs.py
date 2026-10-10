"""文檔站檢查：頁面結構、導覽登記、連結、三種語言的對應與設計系統完整性。

規則見 docs/develop/writing-docs.html。只用標準函式庫，不需要瀏覽器。
簡中是否由繁中重新產生、英文是否跟上繁中，由 tests/i18n/test_generated.py 檢查。
"""

import hashlib
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote, urlsplit

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"
DESIGN_SYSTEM = DOCS / "design-system"
# 整包匯入、不翻譯也不改寫的外部交付物；以 MANIFEST.json 的雜湊確認沒有被改動
IMPORTED = (DESIGN_SYSTEM, DOCS / "prototypes" / "mvp")
NAV_FILE = DOCS / "assets" / "nav.js"
NAV_PREFIX = "window.DOCS_NAV = "
SKIP_SCHEMES = {"http", "https", "mailto", "data", "javascript"}
DEFAULT_LOCALE = "zh-Hant"
# 每種語言的根目錄：繁中在 docs/，其他語言在 docs/<語言>/，目錄結構相同
LANGUAGE_ROOTS = {"zh-Hant": DOCS, "zh-Hans": DOCS / "zh-Hans", "en": DOCS / "en"}

type Localized = dict[str, str]


class NavPage(TypedDict):
    id: str
    name: Localized
    href: str


class NavGroup(TypedDict):
    id: str
    caption: str
    name: Localized
    pages: list[NavPage]


class NavLanguage(TypedDict):
    code: str
    label: str
    short: str


class Nav(TypedDict):
    default: str
    languages: list[NavLanguage]
    subtitle: str
    text: dict[str, Localized]
    groups: list[NavGroup]


@dataclass
class Page:
    path: Path
    lang: str | None = None
    title: str = ""
    h1_count: int = 0
    body: dict[str, str | None] = field(default_factory=dict[str, str | None])
    ids: set[str] = field(default_factory=set[str])
    links: list[str] = field(default_factory=list[str])


class _PageParser(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__()
        self.page = page
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "html":
            self.page.lang = attr.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.page.h1_count += 1
        elif tag == "body":
            self.page.body = attr
        if (element_id := attr.get("id")) is not None:
            self.page.ids.add(element_id)
        for name in ("href", "src"):
            if (value := attr.get(name)) is not None:
                self.page.links.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page.title += data


def _parse(path: Path) -> Page:
    page = Page(path)
    _PageParser(page).feed(path.read_text(encoding="utf-8"))
    return page


def _load_nav() -> Nav:
    text = NAV_FILE.read_text(encoding="utf-8")
    start = text.index(NAV_PREFIX) + len(NAV_PREFIX)
    end = text.rindex("}") + 1
    nav: Nav = json.loads(text[start:end])
    return nav


def _locale_of(path: Path) -> str:
    for locale, root in LANGUAGE_ROOTS.items():
        if locale != DEFAULT_LOCALE and root in path.parents:
            return locale
    return DEFAULT_LOCALE


def _doc_paths() -> list[Path]:
    return sorted(
        p for p in DOCS.rglob("*.html") if not any(root in p.parents for root in IMPORTED)
    )


PAGES = {path: _parse(path) for path in _doc_paths()}
NAV = _load_nav()
NAV_PAGES = {page["id"]: page for group in NAV["groups"] for page in group["pages"]}
LOCALES = [language["code"] for language in NAV["languages"]]


def _rel(path: Path) -> str:
    return path.relative_to(DOCS).as_posix()


def _rel_to_language_root(path: Path) -> str:
    return path.relative_to(LANGUAGE_ROOTS[_locale_of(path)]).as_posix()


def _pages_of(locale: str) -> set[str]:
    return {_rel_to_language_root(p) for p in PAGES if _locale_of(p) == locale}


@pytest.mark.parametrize("path", list(PAGES), ids=_rel)
def test_page_structure(path: Path) -> None:
    page = PAGES[path]
    locale = _locale_of(path)
    assert page.lang == locale, f"html 需標註 lang={locale}"
    assert page.title.strip(), "缺少 <title>"
    assert page.h1_count == 1, f"每頁只能有一個 h1，實際 {page.h1_count} 個"
    assert "main" in page.ids, '內容需放在 <main id="main">'

    rel = _rel_to_language_root(path)
    depth = rel.count("/")
    assert page.body.get("data-root", "") == "../" * depth, "data-root 需回到該語言的根目錄"

    page_id = page.body.get("data-page")
    assert page_id in NAV_PAGES, f"data-page={page_id!r} 沒有在 nav.js 登記"
    assert NAV_PAGES[page_id]["href"] == rel, "nav.js 登記的路徑與檔案位置不符"


@pytest.mark.parametrize("path", list(PAGES), ids=_rel)
def test_links_resolve(path: Path) -> None:
    locale = _locale_of(path)
    broken: list[str] = []
    for link in PAGES[path].links:
        parts = urlsplit(link)
        if parts.scheme in SKIP_SCHEMES:
            continue
        target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not target.exists():
            broken.append(f"{link}（檔案不存在）")
        elif target in PAGES and _locale_of(target) != locale:
            broken.append(f"{link}（連到其他語言的頁面；語言切換由頁首處理）")
        elif parts.fragment and target in PAGES and parts.fragment not in PAGES[target].ids:
            broken.append(f"{link}（找不到錨點）")
    assert not broken, "失效連結：\n" + "\n".join(broken)


@pytest.mark.parametrize("locale", ["zh-Hans", "en"])
def test_every_language_has_the_same_pages(locale: str) -> None:
    source = _pages_of(DEFAULT_LOCALE)
    other = _pages_of(locale)
    assert source - other == set(), f"{locale} 缺少這些頁面"
    assert other - source == set(), f"{locale} 多出繁中沒有的頁面"


@pytest.mark.parametrize("path", [p for p in PAGES if _locale_of(p) != DEFAULT_LOCALE], ids=_rel)
def test_translated_page_keeps_anchors(path: Path) -> None:
    """各語言的錨點相同，切換語言時才能停在同一段落，跨頁連結的 #錨點 也才有效。"""
    source = DOCS / _rel_to_language_root(path)
    if source in PAGES:
        assert PAGES[path].ids == PAGES[source].ids, "錨點（id）與繁中版不同"


def test_nav_is_complete_and_unique() -> None:
    ids = [page["id"] for group in NAV["groups"] for page in group["pages"]]
    assert len(ids) == len(set(ids)), "nav.js 中有重複的頁面 id"

    missing = [p["href"] for p in NAV_PAGES.values() if not (DOCS / p["href"]).exists()]
    assert not missing, f"nav.js 登記了不存在的頁面：{missing}"

    registered = {page["href"] for page in NAV_PAGES.values()}
    unregistered = sorted(_pages_of(DEFAULT_LOCALE) - registered)
    assert not unregistered, f"頁面沒有在 nav.js 登記：{unregistered}"


def test_nav_text_is_complete_in_every_language() -> None:
    assert NAV["default"] == DEFAULT_LOCALE
    assert sorted(LOCALES) == sorted(LANGUAGE_ROOTS)
    names: list[Localized] = list(NAV["text"].values())
    for group in NAV["groups"]:
        names.append(group["name"])
        names.extend(page["name"] for page in group["pages"])
    incomplete = [n for n in names if sorted(n) != sorted(LOCALES) or not all(n.values())]
    assert not incomplete, f"nav.js 這些名稱缺少某種語言：{incomplete}"


@pytest.mark.parametrize("root", IMPORTED, ids=lambda p: p.relative_to(DOCS).as_posix())
def test_imported_package_matches_manifest(root: Path) -> None:
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    listed = {entry["path"] for entry in manifest["files"]}
    changed = [
        entry["path"]
        for entry in manifest["files"]
        if hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]
    ]
    assert not changed, f"檔案被修改（應整包替換，不直接改）：{changed}"
    extra = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    )
    assert set(extra) <= listed, f"多出 MANIFEST.json 沒有列出的檔案：{sorted(set(extra) - listed)}"
