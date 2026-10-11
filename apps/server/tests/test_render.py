"""頁面樣板：用假的紀錄渲染每一頁（三種語言），確認訊息鍵、樣板變數都存在。不需要資料庫。"""

from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest

from rpa_core.dsl import Scenario, validate_file
from rpa_core.i18n import LOCALES, Locale, use_locale
from rpa_server.domain import (
    ENGINES,
    PURPOSES,
    RUN_STATUSES,
    RevisionRecord,
    RunRecord,
    SceneRecord,
    Stats,
)
from rpa_server.render import render

ROOT = Path(__file__).resolve().parents[3]
MOMENT = datetime(2026, 10, 10, 8, 30, tzinfo=UTC)


def _scenario() -> Scenario:
    scenario = validate_file(ROOT / "scenarios" / "demo" / "ba-001.yaml").scenario
    assert scenario is not None
    return scenario


SCENE = SceneRecord(
    id="ba-001",
    name="建立範例紀錄",
    category="範例資料",
    description="說明 <b>不是 HTML</b>",
    kind="dsl",
    base_url=None,
    latest_number=2,
    latest_status="passed",
    published_number=1,
    archived=False,
    created_at=MOMENT,
    updated_at=MOMENT,
)
REVISIONS = [
    RevisionRecord("ba-001", 2, "b" * 64, "dsl", "passed", "改步驟", MOMENT, None, False),
    RevisionRecord("ba-001", 1, "a" * 64, "dsl", "passed", None, MOMENT, MOMENT, True),
]
RUN = RunRecord(
    id="ba-001-20261010-083000-abcdef",
    scene_id="ba-001",
    scene_name="建立範例紀錄",
    category="範例資料",
    revision_number=2,
    purpose="validation",
    status="passed",
    stage=None,
    engine="chromium",
    base_url="http://127.0.0.1:8765",
    input={"title": "甲", "quantity": 3},
    output={"recordId": "DEMO-1", "title": "甲", "quantity": 3},
    error=None,
    scenario_hash="b" * 64,
    cancel_requested=False,
    created_at=MOMENT,
    started_at=MOMENT,
    finished_at=MOMENT,
    duration_seconds=2.5,
)
RESULT: dict[str, object] = {
    "engine": "chromium",
    "input": RUN.input,
    "stages": [
        {"name": "input", "status": "passed", "message": None, "durationMs": 1},
        {"name": "automation", "status": "passed", "message": None, "durationMs": 2000},
        {"name": "verify", "status": "failed", "message": "1 條沒有通過", "durationMs": 3},
        {"name": "output", "status": "skipped", "message": None, "durationMs": 0},
    ],
    "checks": [
        {
            "name": "狀態",
            "comparison": "equals",
            "actual": "已建立",
            "expected": "已建立",
            "passed": True,
            "error": None,
        }
    ],
    "problems": ["入參 quantity 不符合限制：maximum: 30"],
}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _text(html: str) -> str:
    parser = _Collector()
    parser.feed(html)
    return " ".join(parser.text)


def _pages() -> dict[str, str]:
    scenario = _scenario()
    return {
        "scenes": render(
            "scenes.html",
            page="scenes",
            title="場景",
            scenes=[SCENE],
            categories=["範例資料"],
            stats=Stats(1, 1, 3, 2),
            query="",
            category="",
            can_import=True,
        ),
        "scenes-empty": render(
            "scenes.html",
            page="scenes",
            title="場景",
            scenes=[],
            categories=[],
            stats=Stats(0, 0, 0, 0),
            query="x",
            category="",
            can_import=False,
        ),
        "scene": render(
            "scene.html",
            page="scenes",
            title=SCENE.name,
            scene=SCENE,
            revisions=REVISIONS,
            scenario=scenario,
            default_base_url=scenario.browser.base_url,
            runs=[RUN],
        ),
        "edit": render(
            "edit.html",
            page="scenes",
            title="編輯",
            scene=SCENE,
            revision=REVISIONS[1],
            files={"scenario.yaml": "id: ba-001\n</textarea><script>", "automation.py": "pass\n"},
        ),
        "run-form": render(
            "run_form.html",
            page="scenes",
            title="驗證",
            scene=SCENE,
            revision=REVISIONS[0],
            scenario=scenario,
            purpose="validation",
            defaults={"title": "介面驗證範例", "quantity": 12},
            engines=ENGINES,
            base_url="http://127.0.0.1:8765",
        ),
        "runs": render(
            "runs.html",
            page="runs",
            title="報告",
            runs=[RUN],
            scenes=[SCENE],
            categories=["範例資料"],
            statuses=RUN_STATUSES,
            purposes=PURPOSES,
            selected={"scene": ["ba-001"], "category": [], "status": [], "purpose": []},
            limit=200,
        ),
        "run": render(
            "run.html",
            page="runs",
            title="執行",
            run=RUN,
            revision=REVISIONS[0],
            result=RESULT,
            files=["report.html", "screenshot.png"],
            can_publish=True,
        ),
        "run-queued": render(
            "run.html",
            page="runs",
            title="執行",
            run=replace(RUN, status="running", stage="automation", finished_at=None),
            revision=REVISIONS[0],
            result=None,
            files=[],
            can_publish=False,
        ),
        "placeholder": render("placeholder.html", page="recording", title="錄製", milestone="M4"),
        "error": render("error.html", page="scenes", title="錯誤", status=404, message="找不到"),
    }


@pytest.mark.parametrize("locale", LOCALES)
def test_every_page_renders(locale: Locale) -> None:
    with use_locale(locale):
        pages = _pages()
    for name, html in pages.items():
        assert html.startswith("<!doctype html>"), name
        assert f'<html lang="{locale}">' in html, name
        assert _text(html).strip(), name


def test_user_content_is_escaped() -> None:
    with use_locale("zh-Hant"):
        pages = _pages()
    assert "說明 &lt;b&gt;不是 HTML&lt;/b&gt;" in pages["scene"]
    assert "&lt;/textarea&gt;&lt;script&gt;" in pages["edit"]
    assert "<script>" not in pages["edit"].split('id="messages"')[0].split("</head>")[1]


def test_scene_page_shows_versions_and_contract() -> None:
    with use_locale("zh-Hant"):
        html = _pages()["scene"]
    text = _text(html)
    assert 'data-action="publish" data-scene="ba-001" data-revision="2"' in html
    assert "已發布" in text
    assert "maximum: 30" in text
    assert "{{ facts.record.recordId }}" in text


def test_running_page_polls() -> None:
    with use_locale("en"):
        html = _pages()["run-queued"]
    assert "data-poll" in html
    assert 'data-action="cancel-run"' in html
    assert "Automation" in _text(html)


@pytest.mark.parametrize("name", ["portal.css", "shell.js"])
def test_design_system_assets_are_unchanged_copies(name: str) -> None:
    """Portal 的 portal.css、shell.js 是設計系統 v1.0 的原檔；要改請先改設計系統再複製過來。"""
    static = ROOT / "apps" / "server" / "src" / "rpa_server" / "static" / name
    original = ROOT / "docs" / "design-system" / "assets" / name
    assert static.read_bytes() == original.read_bytes()
