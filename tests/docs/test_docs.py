"""文檔站檢查：頁面結構、導覽登記、連結與設計系統完整性。

規則見 docs/develop/writing-docs.html。只用標準函式庫，不需要瀏覽器。
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
NAV_FILE = DOCS / "assets" / "nav.js"
NAV_PREFIX = "window.DOCS_NAV = "
SKIP_SCHEMES = {"http", "https", "mailto", "data", "javascript"}


class NavPage(TypedDict):
    id: str
    name: str
    href: str


class NavGroup(TypedDict):
    id: str
    name: str
    en: str
    pages: list[NavPage]


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


def _load_nav() -> list[NavGroup]:
    text = NAV_FILE.read_text(encoding="utf-8")
    start = text.index(NAV_PREFIX) + len(NAV_PREFIX)
    end = text.rindex("}") + 1
    groups: list[NavGroup] = json.loads(text[start:end])["groups"]
    return groups


def _doc_paths() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.html") if DESIGN_SYSTEM not in p.parents)


PAGES = {path: _parse(path) for path in _doc_paths()}
NAV = _load_nav()
NAV_PAGES = {page["id"]: page for group in NAV for page in group["pages"]}


def _rel(path: Path) -> str:
    return path.relative_to(DOCS).as_posix()


@pytest.mark.parametrize("path", list(PAGES), ids=_rel)
def test_page_structure(path: Path) -> None:
    page = PAGES[path]
    assert page.lang == "zh-Hant", "html 需標註 lang=zh-Hant"
    assert page.title.strip(), "缺少 <title>"
    assert page.h1_count == 1, f"每頁只能有一個 h1，實際 {page.h1_count} 個"
    assert "main" in page.ids, '內容需放在 <main id="main">'

    depth = len(path.relative_to(DOCS).parts) - 1
    assert page.body.get("data-root", "") == "../" * depth, "data-root 與目錄深度不符"

    page_id = page.body.get("data-page")
    assert page_id in NAV_PAGES, f"data-page={page_id!r} 沒有在 nav.js 登記"
    assert NAV_PAGES[page_id]["href"] == _rel(path), "nav.js 登記的路徑與檔案位置不符"


@pytest.mark.parametrize("path", list(PAGES), ids=_rel)
def test_links_resolve(path: Path) -> None:
    broken: list[str] = []
    for link in PAGES[path].links:
        parts = urlsplit(link)
        if parts.scheme in SKIP_SCHEMES:
            continue
        target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not target.exists():
            broken.append(f"{link}（檔案不存在）")
        elif parts.fragment and target in PAGES and parts.fragment not in PAGES[target].ids:
            broken.append(f"{link}（找不到錨點）")
    assert not broken, "失效連結：\n" + "\n".join(broken)


def test_nav_is_complete_and_unique() -> None:
    ids = [page["id"] for group in NAV for page in group["pages"]]
    assert len(ids) == len(set(ids)), "nav.js 中有重複的頁面 id"

    registered = {(DOCS / page["href"]).resolve() for page in NAV_PAGES.values()}
    missing = [p["href"] for p in NAV_PAGES.values() if not (DOCS / p["href"]).exists()]
    assert not missing, f"nav.js 登記了不存在的頁面：{missing}"

    unregistered = [_rel(p) for p in PAGES if p.resolve() not in registered]
    assert not unregistered, f"頁面沒有在 nav.js 登記：{unregistered}"


def test_design_system_matches_manifest() -> None:
    manifest = json.loads((DESIGN_SYSTEM / "MANIFEST.json").read_text(encoding="utf-8"))
    changed = [
        entry["path"]
        for entry in manifest["files"]
        if hashlib.sha256((DESIGN_SYSTEM / entry["path"]).read_bytes()).hexdigest()
        != entry["sha256"]
    ]
    assert not changed, f"設計系統檔案被修改（應整包替換，不直接改）：{changed}"
