"""回看播放器的時鐘（static/replay-media.js）在真的瀏覽器裡：段落與卡片的邊界（2026-10-28）。

合併回看的時間軸是一段一段接起來的（ADR 0019）。兩段相接的那一刻算後面那一段：轉場卡的結尾
用浮點數相加（開始＋長度），可能略大於下一段的開始；跳到下一段開頭（N、點節點色帶）時不能還停在
卡片上。CI 曾因此偶爾失敗（任務 20261028-main-ci-red）。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from testsite.browsers import require_engine

pytestmark = pytest.mark.browser

SCRIPT = Path(__file__).resolve().parents[1] / "src/rpa_server/static/replay-media.js"


@pytest.fixture
def page() -> Iterator[Page]:
    require_engine("chromium")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content("<video id='video'></video>")
            page.add_script_tag(content=SCRIPT.read_text(encoding="utf-8"))
            yield page
        finally:
            browser.close()


# 第一段 1.131 秒：1.131 + 2 在浮點數是 3.1310000000000002，比第二段的開始 3.131 大一點
FIRST_MS = 1131


def test_the_moment_two_segments_meet_belongs_to_the_later_one(page: Page) -> None:
    result = page.evaluate(
        """first => {
          const second = first + 2000;
          const info = {
            durationMs: second + 5000,
            clips: [
              {pageId: 'n1/page-1', startMs: 0, durationMs: first, url: null},
              {pageId: 'n2/page-1', startMs: second, durationMs: 5000, url: null},
            ],
            segments: [
              {startMs: 0, durationMs: first, page: 'n1/page-1'},
              {startMs: second, durationMs: 5000, page: 'n2/page-1'},
            ],
            cards: [{index: 1, kind: 'transition', node: 'n2', startMs: first, durationMs: 2000}],
          };
          const media = new ReplayMedia(document.getElementById('video'), info, [], null);
          const page = at => (media.segmentAt(at) || {}).page || null;
          return {
            atSecond: {card: Boolean(media.cardAt(second / 1000)), page: page(second / 1000)},
            atCard: {card: Boolean(media.cardAt(first / 1000)), page: page(first / 1000)},
            inCard: Boolean(media.cardAt((first + 1000) / 1000)),
          };
        }""",
        FIRST_MS,
    )

    assert result == {
        "atSecond": {"card": False, "page": "n2/page-1"},
        "atCard": {"card": True, "page": None},
        "inCard": True,
    }
