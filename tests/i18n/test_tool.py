"""tools/i18n.py 的單元測試：用假的轉換函式，不需要 OpenCC。"""

import json
from pathlib import Path

import pytest

import tools.i18n as tool

FAKE_WORDS = {"繁體": "简体", "檔案": "文件", "說明": "说明", "連結": "链接"}


def fake_convert(text: str) -> str:
    for old, new in FAKE_WORDS.items():
        text = text.replace(old, new)
    return text


def test_convert_html_converts_text_and_descriptive_attributes() -> None:
    html = '<p title="繁體說明">檔案</p><img alt="繁體" src="a.png">'

    assert convert_html(html) == '<p title="简体说明">文件</p><img alt="简体" src="a.png">'


def test_convert_html_protects_urls_and_identifiers() -> None:
    html = '<a href="檔案.html" id="檔案" class="繁體" data-page="檔案">連結</a>'

    expected = '<a href="檔案.html" id="檔案" class="繁體" data-page="檔案">链接</a>'
    assert convert_html(html) == expected


def test_convert_html_keeps_translate_no_blocks() -> None:
    html = '<p>檔案</p><pre class="source" translate="no">檔案\n繁體</pre><p>檔案</p>'

    expected = '<p>文件</p><pre class="source" translate="no">檔案\n繁體</pre><p>文件</p>'
    assert convert_html(html) == expected


def convert_html(html: str) -> str:
    return tool.convert_html(html, fake_convert)


DOCS = Path("/repo/docs")
PAGES = frozenset({DOCS / "index.html", DOCS / "develop" / "setup.html"})


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # 其他文檔頁面：各語言結構相同，維持原樣
        ("setup.html", "setup.html"),
        ("../index.html#faq", "../index.html#faq"),
        # 共用資源：從新位置多回一層
        ("../assets/docs.css", "../../assets/docs.css"),
        ("../design-system/assets/portal.css", "../../design-system/assets/portal.css"),
        ("../design-system/index.html#tokens", "../../design-system/index.html#tokens"),
        # 不是相對路徑的不動
        ("#faq", "#faq"),
        ("https://example.com/a.css", "https://example.com/a.css"),
        ("mailto:a@example.com", "mailto:a@example.com"),
    ],
)
def test_rebase_url(url: str, expected: str) -> None:
    source = DOCS / "develop" / "macos.html"
    target = DOCS / "zh-Hans" / "develop" / "macos.html"

    assert tool.rebase_url(url, source, target, PAGES) == expected


def test_localize_adds_simplified_after_traditional() -> None:
    data: tool.Json = {
        "title": {"zh-Hant": "繁體", "en": "Traditional"},
        "groups": [{"id": "a", "name": {"zh-Hant": "檔案", "zh-Hans": "舊的", "en": "Files"}}],
        "plain": "繁體",
    }

    assert tool.localize(data, fake_convert) == {
        "title": {"zh-Hant": "繁體", "zh-Hans": "简体", "en": "Traditional"},
        "groups": [{"id": "a", "name": {"zh-Hant": "檔案", "zh-Hans": "文件", "en": "Files"}}],
        # 不是語言物件的字串不轉換
        "plain": "繁體",
    }


def test_dump_json_keeps_short_objects_on_one_line() -> None:
    data: tool.Json = {
        "name": {"zh-Hant": "首頁", "zh-Hans": "首页", "en": "Home"},
        "pages": [{"id": "x" * 60, "href": "y" * 60}],
    }

    text = tool.dump_json(data)

    assert json.loads(text) == data
    assert '"name": {"zh-Hant": "首頁", "zh-Hans": "首页", "en": "Home"}' in text
    assert text.count("\n") > 2


def test_page_hash_is_short_and_stable(tmp_path: Path) -> None:
    page = tmp_path / "a.html"
    page.write_text("內容", encoding="utf-8")

    assert tool.page_hash(page) == tool.page_hash(page)
    assert tool.page_hash(page).startswith("sha256:")
    assert len(tool.page_hash(page)) == len("sha256:") + 16


def test_stamp_inserts_then_updates_source_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = tmp_path / "docs"
    (docs / "en").mkdir(parents=True)
    source = docs / "index.html"
    target = docs / "en" / "index.html"
    source.write_text("繁中第一版", encoding="utf-8")
    target.write_text(
        '<head>\n<meta name="viewport" content="width=device-width">\n</head>\n', encoding="utf-8"
    )
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "DOCS", docs)
    monkeypatch.setattr(tool, "LANGUAGE_DIRS", {"zh-Hans": docs / "zh-Hans", "en": docs / "en"})

    tool.stamp(target)
    first = target.read_text(encoding="utf-8")
    source.write_text("繁中第二版", encoding="utf-8")
    tool.stamp(target)
    second = target.read_text(encoding="utf-8")

    assert f'<meta name="translation-source" content="{tool.page_hash(source)}">' in second
    assert first.count("translation-source") == second.count("translation-source") == 1
    assert first != second
