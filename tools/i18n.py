"""多語言同步工具：從繁中產生簡中，並檢查英文翻譯有沒有跟上繁中。

決策背景見 docs/adr/0007-i18n.html，日常用法見 docs/develop/writing-docs.html。

    uv run python tools/i18n.py sync           從繁中重新產生全部簡中檔案
    uv run python tools/i18n.py check          只檢查不寫入（pytest 也會跑同樣的檢查）
    uv run python tools/i18n.py stamp 檔案...   英文頁翻譯更新後，記下它對照的繁中版本
    uv run python tools/i18n.py stamp --all    為全部英文頁重新記錄（確定都已翻譯完才用）

產生的檔案（都會提交，請勿直接修改）：

    docs/**/*.html 的繁中頁面        → docs/zh-Hans/ 下相同路徑
    docs/assets/nav.js 的 "zh-Hant"  → 同一個物件的 "zh-Hans"
    **/locales/*zh-Hant.json         → 同目錄的 *zh-Hans.json

簡中用 OpenCC 的 tw2sp 設定轉換：繁體轉簡體，並把台灣用語換成大陸用語（檔案→文件）。
轉換結果不理想的詞，加在 tools/zh-Hans-overrides.json。
HTML 中標了 translate="no" 的元素保留原文，例如程式實際印出的繁中訊息。
"""

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from functools import cache
from pathlib import Path
from typing import Final, Protocol, cast
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT: Final = Path(__file__).resolve().parent.parent
DOCS: Final = ROOT / "docs"
NAV_FILE: Final = DOCS / "assets" / "nav.js"
NAV_PREFIX: Final = "window.DOCS_NAV = "
OVERRIDES_FILE: Final = ROOT / "tools" / "zh-Hans-overrides.json"
OPENCC_CONFIG: Final = "tw2sp.json"

SOURCE: Final = "zh-Hant"
GENERATED: Final = "zh-Hans"
TRANSLATED: Final = "en"
LANGUAGE_DIRS: Final = {GENERATED: DOCS / GENERATED, TRANSLATED: DOCS / TRANSLATED}
SOURCE_META: Final = "translation-source"

type Convert = Callable[[str], str]


class _OpenCC(Protocol):
    def convert(self, text: str) -> str: ...


type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


# ------------------------------------------------------------ 轉換


@cache
def opencc_converter() -> Convert:
    """OpenCC 繁轉簡（台灣用語→大陸用語），再套用 zh-Hans-overrides.json 的修正。"""
    try:
        # 只有產生簡中時才需要，放在這裡讓 stamp 不依賴它；opencc 沒有型別標註，以 Protocol 描述
        module = importlib.import_module("opencc")
    except ImportError:  # pragma: no cover
        sys.exit("需要 OpenCC：先執行 uv sync 安裝開發依賴。")
    factory = cast("Callable[[str], _OpenCC]", vars(module)["OpenCC"])
    converter = factory(OPENCC_CONFIG)
    overrides = load_overrides()

    def convert(text: str) -> str:
        result = converter.convert(text)
        for old, new in overrides:
            result = result.replace(old, new)
        return result

    return convert


def load_overrides() -> list[tuple[str, str]]:
    data = cast("dict[str, Json]", json.loads(OVERRIDES_FILE.read_text(encoding="utf-8")))
    pairs = cast("list[list[str]]", data["replace"])
    return [(old, new) for old, new in pairs]


# 轉換時要保護的屬性：網址、識別字等，不能被換字。title、aria-label、alt 等說明文字照常轉換。
_PROTECTED_ATTR: Final = re.compile(
    r"\b(?:href|src|id|class|for|lang|hreflang|name|content|data-[\w-]+"
    r'|aria-(?:controls|describedby|labelledby))="[^"]*"'
)
# translate="no" 的元素整段保留原文；元素內不能再巢狀同名元素。
_NO_TRANSLATE: Final = re.compile(
    r'<(?P<tag>[a-zA-Z][\w-]*)\b[^>]*\btranslate="no"[^>]*>.*?</(?P=tag)>', re.DOTALL
)
# 用 Unicode 私用區字元當佔位符，OpenCC 不會轉換它們。
_PLACEHOLDER: Final = re.compile("(\\d+)")


def convert_html(html: str, convert: Convert) -> str:
    """轉換 HTML 中的文字，保留網址、識別字與 translate="no" 的區塊。"""
    saved: list[str] = []

    def mask(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"{len(saved) - 1}"

    masked = _PROTECTED_ATTR.sub(mask, _NO_TRANSLATE.sub(mask, html))
    return _PLACEHOLDER.sub(lambda m: saved[int(m.group(1))], convert(masked))


def rebase_url(url: str, source: Path, target: Path, pages: frozenset[Path]) -> str:
    """把來源頁面裡的相對網址改成在目標位置也能用的網址。

    指向其他文檔頁面的連結維持原樣（各語言目錄結構相同，會連到同語言的那一頁）；
    指向共用資源（樣式、腳本、設計系統）的連結改成從新位置出發的相對路徑。
    """
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/"):
        return url
    resolved = Path(os.path.normpath(source.parent / unquote(parts.path)))
    if resolved in pages:
        return url
    relative = Path(os.path.relpath(resolved, target.parent)).as_posix()
    if "%" in parts.path:
        relative = quote(relative)
    return urlunsplit(("", "", relative, parts.query, parts.fragment))


def _rebase_links(html: str, source: Path, target: Path, pages: frozenset[Path]) -> str:
    def replace(match: re.Match[str]) -> str:
        url = rebase_url(match.group(2), source, target, pages)
        return f'{match.group(1)}="{url}"'

    return re.sub(r'\b(href|src)="([^"]*)"', replace, html)


# ------------------------------------------------------------ 文檔頁面


def source_pages() -> list[Path]:
    """繁中頁面：docs/ 下的 HTML，不含設計系統、MVP 原型與其他語言目錄。"""
    excluded = (DOCS / "design-system", DOCS / "prototypes", *LANGUAGE_DIRS.values())
    return sorted(p for p in DOCS.rglob("*.html") if not any(d in p.parents for d in excluded))


def counterpart(source: Path, locale: str) -> Path:
    """繁中頁面在另一種語言的對應位置。"""
    return LANGUAGE_DIRS[locale] / source.relative_to(DOCS)


def page_hash(path: Path) -> str:
    """頁面內容的指紋，記在英文頁上，用來判斷英文翻譯是否跟上繁中。"""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def generate_page(source: Path, convert: Convert, pages: frozenset[Path]) -> str:
    """由繁中頁面產生簡中頁面的內容。"""
    target = counterpart(source, GENERATED)
    html = convert_html(source.read_text(encoding="utf-8"), convert)
    html, count = re.subn(r'<html lang="zh-Hant">', '<html lang="zh-Hans">', html, count=1)
    if count != 1:
        raise ValueError(f'{source.relative_to(ROOT)} 缺少 <html lang="zh-Hant">')
    html = _rebase_links(html, source, target, pages)
    rel = source.relative_to(ROOT).as_posix()
    notice = (
        f"<!-- 本页由 tools/i18n.py 从 {rel} 自动生成，请勿直接修改；"
        "请修改繁体中文原文后执行 uv run python tools/i18n.py sync。 -->\n"
    )
    first, _, rest = html.partition("\n")
    return f"{first}\n{notice}{rest}"


# ------------------------------------------------------------ 導覽 nav.js


def read_nav(text: str) -> tuple[str, Json]:
    """拆出 nav.js 開頭的註解與後面的 JSON。"""
    start = text.index(NAV_PREFIX)
    end = text.rindex("}") + 1
    data = cast("Json", json.loads(text[start + len(NAV_PREFIX) : end]))
    return text[:start], data


def localize(node: Json, convert: Convert) -> Json:
    """遞迴處理：凡是有 "zh-Hant" 字串的物件，都補上轉換後的 "zh-Hans"。"""
    if isinstance(node, list):
        return [localize(item, convert) for item in node]
    if not isinstance(node, dict):
        return node
    result: dict[str, Json] = {}
    source = node.get(SOURCE)
    if isinstance(source, str):
        result[SOURCE] = source
        result[GENERATED] = convert(source)
    for key, value in node.items():
        if key not in result:
            result[key] = localize(value, convert)
    return result


def dump_json(value: Json, indent: int = 0, width: int = 110) -> str:
    """固定排版：放得進一行的物件與陣列寫成一行，其餘每個元素一行。"""
    inline = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if not isinstance(value, dict | list) or len(inline) + 2 * indent <= width:
        return inline
    pad = "  " * (indent + 1)
    if isinstance(value, dict):
        items = [
            f"{pad}{json.dumps(k, ensure_ascii=False)}: {dump_json(v, indent + 1, width)}"
            for k, v in value.items()
        ]
        return "{\n" + ",\n".join(items) + "\n" + "  " * indent + "}"
    items = [f"{pad}{dump_json(v, indent + 1, width)}" for v in value]
    return "[\n" + ",\n".join(items) + "\n" + "  " * indent + "]"


def generate_nav(text: str, convert: Convert) -> str:
    header, data = read_nav(text)
    return f"{header}{NAV_PREFIX}{dump_json(localize(data, convert))};\n"


# ------------------------------------------------------------ 訊息目錄


def catalog_sources() -> list[Path]:
    patterns = ("packages/*/src/*/locales/*zh-Hant.json", "apps/*/src/*/locales/*zh-Hant.json")
    return sorted(p for pattern in patterns for p in ROOT.glob(pattern))


def catalog_target(source: Path) -> Path:
    return source.with_name(source.name.replace(SOURCE, GENERATED))


def generate_catalog(source: Path, convert: Convert) -> str:
    messages = cast("dict[str, str]", json.loads(source.read_text(encoding="utf-8")))
    converted = {key: convert(value) for key, value in messages.items()}
    return json.dumps(converted, ensure_ascii=False, indent=2) + "\n"


# ------------------------------------------------------------ 計畫、同步與檢查


def planned_outputs(convert: Convert) -> dict[Path, str]:
    """所有應該存在的簡中檔案及其內容。"""
    pages = source_pages()
    page_set = frozenset(pages)
    outputs = {counterpart(p, GENERATED): generate_page(p, convert, page_set) for p in pages}
    outputs[NAV_FILE] = generate_nav(NAV_FILE.read_text(encoding="utf-8"), convert)
    for source in catalog_sources():
        outputs[catalog_target(source)] = generate_catalog(source, convert)
    return outputs


def stale_generated(outputs: Iterable[Path]) -> list[Path]:
    """docs/zh-Hans/ 裡已經沒有繁中來源的頁面。"""
    expected = set(outputs)
    return sorted(p for p in LANGUAGE_DIRS[GENERATED].rglob("*.html") if p not in expected)


def zh_hans_problems(convert: Convert) -> list[str]:
    outputs = planned_outputs(convert)
    problems = [
        f"{path.relative_to(ROOT)} 不是最新的簡中版本"
        for path, content in outputs.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]
    problems += [f"{p.relative_to(ROOT)} 已經沒有繁中來源" for p in stale_generated(outputs)]
    return problems


_META: Final = re.compile(rf'<meta name="{SOURCE_META}" content="([^"]*)">')


def en_problems() -> list[str]:
    """英文頁是否齊全，且對照的是目前的繁中版本。"""
    problems: list[str] = []
    sources = source_pages()
    for source in sources:
        target = counterpart(source, TRANSLATED)
        rel = target.relative_to(ROOT)
        if not target.exists():
            problems.append(f"{rel} 不存在：新增繁中頁面時也要提供英文版")
            continue
        match = _META.search(target.read_text(encoding="utf-8"))
        if match is None:
            problems.append(f'{rel} 缺少 <meta name="{SOURCE_META}">：翻譯完後執行 stamp')
        elif match.group(1) != page_hash(source):
            problems.append(
                f"{rel} 對照的繁中版本已過期：依 {source.relative_to(ROOT)} 的修改更新英文，"
                f"再執行 uv run python tools/i18n.py stamp {rel.as_posix()}"
            )
    expected = {counterpart(s, TRANSLATED) for s in sources}
    for page in sorted(LANGUAGE_DIRS[TRANSLATED].rglob("*.html")):
        if page not in expected:
            problems.append(f"{page.relative_to(ROOT)} 已經沒有繁中來源")
    return problems


def stamp(target: Path) -> None:
    """在英文頁記下對照的繁中版本。"""
    target = target.resolve()
    source = DOCS / target.relative_to(LANGUAGE_DIRS[TRANSLATED])
    html = target.read_text(encoding="utf-8")
    meta = f'<meta name="{SOURCE_META}" content="{page_hash(source)}">'
    if _META.search(html):
        html = _META.sub(meta, html, count=1)
    else:
        html, count = re.subn(r'(<meta name="viewport"[^>]*>\n)', rf"\1{meta}\n", html, count=1)
        if count != 1:
            raise ValueError(f'{target.relative_to(ROOT)} 缺少 <meta name="viewport">')
    target.write_text(html, encoding="utf-8", newline="\n")


def sync(convert: Convert) -> int:
    outputs = planned_outputs(convert)
    changed = 0
    for path, content in outputs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"更新 {path.relative_to(ROOT)}")
            changed += 1
    for path in stale_generated(outputs):
        path.unlink()
        print(f"刪除 {path.relative_to(ROOT)}")
        changed += 1
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多語言同步工具（見 docs/adr/0007-i18n.html）")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync", help="從繁中重新產生全部簡中檔案")
    commands.add_parser("check", help="檢查簡中是否最新、英文是否跟上繁中")
    stamp_parser = commands.add_parser("stamp", help="記下英文頁對照的繁中版本")
    stamp_parser.add_argument("pages", nargs="*", type=Path, help="docs/en/ 下的頁面")
    stamp_parser.add_argument("--all", action="store_true", help="全部英文頁")
    args = parser.parse_args(argv)

    if args.command == "sync":
        changed = sync(opencc_converter())
        print(f"簡中已是最新（更新 {changed} 個檔案）")
        # 英文是否跟上只提醒，不擋提交；CI 的 check 才會判定失敗
        for problem in en_problems():
            print(f"提醒：{problem}", file=sys.stderr)
        return 0
    if args.command == "check":
        problems = zh_hans_problems(opencc_converter()) + en_problems()
        if problems:
            problems.append("簡中問題執行 uv run python tools/i18n.py sync 即可修正")
    else:
        pages = cast("list[Path]", args.pages)
        if cast("bool", args.all):
            pages = [counterpart(s, TRANSLATED) for s in source_pages()]
        if not pages:
            parser.error("請指定英文頁，或用 --all")
        for page in pages:
            stamp(page)
            print(f"已記錄 {page.resolve().relative_to(ROOT)}")
        problems = []

    for problem in problems:
        print(f"! {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
