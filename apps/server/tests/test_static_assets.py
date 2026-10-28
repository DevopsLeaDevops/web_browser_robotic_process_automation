"""頁面的 CSS 與 JavaScript 帶內容雜湊，升級後瀏覽器不會沿用舊的快取（2026-10-28）：不需要瀏覽器。

v0.7.0 驗收時，伺服器已經是新版，瀏覽器卻還在用之前快取的 replay.js：合併回看的轉場卡變成黑屏、
步驟沒有分組。網址加上內容的雜湊（``?v=…``）；帶版本的長期快取，沒帶的每次向伺服器確認。
"""

import hashlib
import re
from pathlib import Path

import pytest
from httpx2 import Client

from rpa_server import render
from rpa_server.render import STATIC, static_url

ASSETS = ("portal.css", "portal-app.css", "shell.js", "portal.js")


def test_pages_link_assets_with_a_content_hash(client: Client) -> None:
    page = client.get("/scenes").text

    for name in ASSETS:
        digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]
        assert f'"/static/{name}?v={digest}"' in page
    assert not re.search(r'"/static/[\w.-]+"', page)


def test_versioned_assets_are_cached_and_plain_ones_revalidated(client: Client) -> None:
    versioned = client.get(static_url("replay.js"))
    plain = client.get("/static/replay.js")

    assert versioned.status_code == 200
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert plain.headers["cache-control"] == "no-cache"
    assert versioned.content == plain.content


def test_the_hash_follows_the_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = tmp_path / "app.js"
    asset.write_text("one", encoding="utf-8")
    monkeypatch.setattr(render, "STATIC", tmp_path)

    first = render.static_url("app.js")
    asset.write_text("two!", encoding="utf-8")
    second = render.static_url("app.js")

    assert first != second
    assert second == f"/static/app.js?v={hashlib.sha256(b'two!').hexdigest()[:12]}"
    assert render.static_url("missing.js") == "/static/missing.js"
