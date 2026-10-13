"""頁面樣板：用假的紀錄渲染每一頁（三種語言），確認訊息鍵、樣板變數都存在。不需要資料庫。"""

import re
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest

from rpa_core.dsl import Scenario, validate_file, validate_text
from rpa_core.i18n import LOCALES, NATIVE_NAMES, Locale, use_locale
from rpa_server.debugging import DebugSession
from rpa_server.debugging import _steps as debug_steps  # pyright: ignore[reportPrivateUsage]
from rpa_server.domain import (
    ENGINES,
    DomainRecord,
    RecordingRecord,
    RevisionRecord,
    RoleRecord,
    RunRecord,
    SceneCard,
    SceneRecord,
)
from rpa_server.i18n import follow_locale, t
from rpa_server.render import js_messages, render, run_filters
from rpa_server.secret_store import SecretInfo
from rpa_server.services import SceneNeeds

ROOT = Path(__file__).resolve().parents[3]
MOMENT = datetime(2026, 10, 10, 8, 30, tzinfo=UTC)


def _scenario() -> Scenario:
    scenario = validate_file(ROOT / "scenarios" / "demo" / "ba-001.yaml").scenario
    assert scenario is not None
    return scenario


DOMAIN = DomainRecord(
    id="testsite",
    name="測試網站自動化",
    description="對本機測試網站執行的案例",
    position=0,
    scene_count=2,
    created_at=MOMENT,
)
OTHER_DOMAIN = DomainRecord("google", "谷歌自動化", None, 1, 0, MOMENT)
DOMAINS = [DOMAIN, OTHER_DOMAIN]
SCENE = SceneRecord(
    id="ba-001",
    name="建立範例紀錄",
    category="範例資料",
    description="說明 <b>不是 HTML</b>",
    domain_id="testsite",
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


NEEDS = SceneNeeds("testsite-user", True, "needs_login", (("ERP_PASSWORD", False),))
ROLE = RoleRecord(
    id="testsite-user",
    name="測試網站：一般使用者",
    description="示範帳號 user",
    login_url="http://127.0.0.1:8765/login",
    check_url="http://127.0.0.1:8765/account",
    check_locator={"testId": "current-user"},
    engine="firefox",
    auto_login=None,
    status="logged_in",
    message=None,
    checked_at=MOMENT,
    state_saved_at=MOMENT,
    used_by=("ba-004",),
)
RECORDING = RecordingRecord(
    id="rec-20261012-080000-abcdef",
    scene_id="rec-001",
    scene_name="錄製的場景",
    new_scene=True,
    domain_id="testsite",
    revision_number=1,
    source="codegen",
    url="http://127.0.0.1:8765/",
    engine="chromium",
    role_id=None,
    status="done",
    warnings=[{"line": 12, "message": "hover 還不支援", "source": "page.hover()"}],
    error=None,
    created_at=MOMENT,
    finished_at=MOMENT,
)


def _check_text(role: RoleRecord) -> str:
    return "{ testId: current-user }"


def _role_values(role: RoleRecord) -> dict[str, object]:
    return {"name": role.name}


CONTRACT: dict[str, object] = {
    "inputs": {"title": {"type": "string", "default": "示範", "minLength": 1}},
    "outputs": {"recordId": {"type": "string", "from": "{{ facts.record.recordId }}"}},
}
FACTS = [("record", ["recordId", "status"])]


def _m4_pages(scenario: Scenario, *, english: bool = False) -> dict[str, str]:
    """M4 的頁面：登入與憑證、錄製、錄製詳情、逐步調試（開始前與進行中）。"""
    role = replace(ROLE, name="User", description="Demo") if english else ROLE
    recording = (
        replace(RECORDING, scene_name="Recorded", warnings=[{"line": 3, "message": "x"}])
        if english
        else RECORDING
    )
    waiting = replace(
        role,
        id="manager",
        activity="login",
        session={"status": "waiting", "message": None},
        status="none",
        state_saved_at=None,
        used_by=(),
    )
    session = DebugSession(
        id="abc123",
        scene_id=SCENE.id,
        revision=2,
        engine="chromium",
        headless=True,
        base_url=None,
        inputs={"title": "x"},
        folder=ROOT,
        scenario=scenario,
        steps=debug_steps(scenario),
        status="ready",
        url="http://127.0.0.1:8765/",
        screenshot="shot-0001.png",
        located={
            "locator": "{ css: main }",
            "ok": True,
            "count": 1,
            "matches": [{"tag": "main", "text": "x"}],
        },
    )
    session.steps[0].status = "passed"
    session.steps[0].runs = 1
    session.next_index = 1
    scene = replace(SCENE, name="Scene", description="About") if english else SCENE
    domains = (
        [replace(DOMAIN, name="Lab"), replace(OTHER_DOMAIN, name="Other")] if english else DOMAINS
    )
    common: dict[str, object] = {
        "domain": domains[0],
        "scene": scene,
        "scenario": scenario,
        "revisions": REVISIONS,
        "shown": 2,
        "yaml": "schemaVersion: 1\n",
        "defaults": {"title": "x"},
        "needs": None if english else NEEDS,
        "display": True,
        "engines": ENGINES,
        "base_url": None,
        "idle_minutes": 15,
    }
    return {
        "roles": render(
            "roles.html",
            page="roles",
            title="Roles",
            domains=domains,
            roles=[role, waiting],
            secrets=[SecretInfo("ERP_PASSWORD", MOMENT)],
            usage={"ERP_PASSWORD": ["ba-004"], "OTHER": ["ba-005"]},
            missing=[("OTHER", ["ba-005"])],
            environ=set[str](),
            display=False,
            busy=True,
            engines=ENGINES,
            check_text=_check_text,
            role_values=_role_values,
            auto_example="- { id: open, action: goto, url: https://example.com }",
        ),
        "recording": render(
            "recording.html",
            page="recording",
            title="Recording",
            domains=domains,
            recordings=[recording, replace(recording, id="r2", status="recording")],
            active=replace(recording, id="r2", status="recording"),
            scenes=[scene],
            roles=[role],
            engines=ENGINES,
            display=True,
            default_domain="testsite",
            default_url="",
            selected_scene="",
            scene_defaults={
                scene.id: {
                    "url": "http://127.0.0.1:8765/",
                    "engine": "firefox",
                    "roleId": None,
                    "script": False,
                    "steps": 3,
                    "revision": 2,
                }
            },
        ),
        "recording-detail": render(
            "recording_detail.html",
            page="recording",
            title="Recording",
            domains=domains,
            item=recording,
            files={"raw.py": "page.goto('x')\n", "scenario.yaml": "id: rec-001\n"},
        ),
        "debug-start": render(
            "debug.html",
            page="domain:testsite",
            title="Debug",
            domains=domains,
            session=None,
            **common,
        ),
        "debug-session": render(
            "debug.html",
            page="domain:testsite",
            title="Debug",
            domains=domains,
            session=session,
            **common,
        ),
    }


def _pages() -> dict[str, str]:
    scenario = _scenario()
    return {
        "domain": render(
            "domain.html",
            page="domain:testsite",
            title=DOMAIN.name,
            domains=DOMAINS,
            domain=DOMAIN,
            cards=[
                SceneCard(SCENE, RUN, RUN.id),
                SceneCard(
                    replace(SCENE, id="ba-009", published_number=None, kind="script"), None, None
                ),
            ],
            can_import=True,
        ),
        "domain-empty": render(
            "domain.html",
            page="domain:google",
            title=OTHER_DOMAIN.name,
            domains=DOMAINS,
            domain=OTHER_DOMAIN,
            cards=[],
            can_import=False,
        ),
        "domains": render(
            "domains.html",
            page="domains",
            title="領域管理",
            domains=DOMAINS,
            unassigned=[replace(SCENE, id="loose", domain_id=None)],
        ),
        "scene": render(
            "scene.html",
            page="domain:testsite",
            title=SCENE.name,
            domains=DOMAINS,
            domain=DOMAIN,
            scene=SCENE,
            revisions=REVISIONS,
            scenario=scenario,
            default_base_url=scenario.browser.base_url,
            runs=[RUN],
            needs=NEEDS,
            contract_data=CONTRACT,
            facts=FACTS,
        ),
        "section": render(
            "section.html",
            page="domain:testsite",
            title="斷言腳本",
            domains=DOMAINS,
            domain=DOMAIN,
            scene=SCENE,
            revision=REVISIONS[1],
            part="verify",
            text="verify:\n  - value: '{{ facts.record.status }}'\n    notEmpty: true",
            scenario=scenario,
            facts=FACTS,
        ),
        "edit": render(
            "edit.html",
            page="domain:testsite",
            title="編輯",
            domains=DOMAINS,
            domain=DOMAIN,
            scene=SCENE,
            revision=REVISIONS[1],
            files={"scenario.yaml": "id: ba-001\n</textarea><script>", "automation.py": "pass\n"},
            selected="automation.py",
            focus="",
        ),
        "run-form": render(
            "run_form.html",
            page="domains",
            title="驗證",
            domains=DOMAINS,
            domain=None,
            scene=replace(SCENE, domain_id=None),
            revision=REVISIONS[0],
            scenario=scenario,
            purpose="validation",
            defaults={"title": "介面驗證範例", "quantity": 12},
            engines=ENGINES,
            base_url="http://127.0.0.1:8765",
            display=True,
        ),
        "runs": render(
            "runs.html",
            page="runs",
            title="報告",
            runs=[RUN],
            filters=run_filters(
                scenes=[SCENE], categories=["範例資料"], selected={"scene": ["ba-001"]}
            ),
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
            role=None,
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
            role="testsite-user",
        ),
        "run-needs-login": render(
            "run.html",
            page="runs",
            title="執行",
            run=replace(RUN, status="needs_login", error="角色「一般使用者」需要重新登入"),
            revision=REVISIONS[0],
            result={
                **RESULT,
                "stages": [
                    {"name": "login", "status": "needs_login", "message": "x", "durationMs": 9}
                ],
            },
            files=["login.png", "report.html"],
            can_publish=False,
            role="testsite-user",
        ),
        **_m4_pages(scenario),
        "placeholder": render(
            "placeholder.html", page="playground", title="試驗場", milestone="M6"
        ),
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


def test_side_menu_lists_domains_then_domain_management() -> None:
    with use_locale("zh-Hant"):
        html = _pages()["domain"]
    side = html.split('id="sidenav"')[1].split("</nav>")[0]
    labels = [part.split("</span>")[0] for part in side.split("<span>")[1:]]
    assert labels == ["測試網站自動化", "谷歌自動化", "領域管理", "登入與憑證"]
    assert 'href="/domains/testsite" class="active" aria-current="page"' in side


def test_scene_card_follows_the_design() -> None:
    with use_locale("zh-Hant"):
        html = _pages()["domain"]
    published, draft = html.split('class="panel panel-body scene-card"')[1:3]
    text = _text(published)
    for label in ("自動化腳本", "斷言腳本", "執行報告", "入參設定", "出參設定", "調試", "運行"):
        assert label in text, label
    assert 'src="/runs/ba-001-20261010-083000-abcdef/files/screenshot.png"' in published
    assert 'data-status="passed"' in published
    assert 'href="/scenes/ba-001/edit?part=steps"' in published
    assert 'href="/scenes/ba-001/edit?part=verify"' in published
    assert "暫無執行截圖" in _text(draft)
    assert "未執行" in _text(draft)
    assert 'aria-disabled="true"' in draft
    assert 'href="/scenes/ba-009/edit?file=assertion.py"' in draft
    assert "2 個場景" in _text(html)


# ---------------------------------------------------------------- 多語言


ASCII_SCENARIO = """\
schemaVersion: 1
id: ascii-001
name: ASCII scenario
browser: {baseUrl: "http://127.0.0.1:8765"}
inputs:
  title: {type: string, default: hello}
outputs:
  message: {type: string, from: "{{ facts.message }}"}
steps:
  - {id: open, action: goto, url: /}
  - {id: read, action: extract, target: {css: p}, as: message}
verify:
  - {name: has message, value: "{{ facts.message }}", equals: done}
"""


def _english_domain_pages() -> dict[str, str]:
    """用沒有中文的資料渲染這次加入的頁面；畫面上剩下的中文就是忘了翻譯的字。"""
    scenario = validate_text(ASCII_SCENARIO).scenario
    assert scenario is not None
    domain = replace(DOMAIN, name="Lab", description="Cases for the lab")
    domains = [domain, replace(OTHER_DOMAIN, name="Other")]
    scene = replace(SCENE, name="Scene", category="Cat", description="About")
    run = replace(RUN, scene_name="Scene", category="Cat", input={}, output=None)
    with use_locale("en"):
        return {
            "domain": render(
                "domain.html",
                page="domain:testsite",
                title="Lab",
                domains=domains,
                domain=domain,
                cards=[
                    SceneCard(scene, run, run.id),
                    SceneCard(replace(scene, id="b", published_number=None), None, None),
                ],
                can_import=True,
            ),
            "domain-empty": render(
                "domain.html",
                page="domain:google",
                title="Other",
                domains=domains,
                domain=domains[1],
                cards=[],
                can_import=False,
            ),
            "domains": render(
                "domains.html",
                page="domains",
                title=t("nav.domains"),
                domains=domains,
                unassigned=[replace(scene, id="loose", domain_id=None)],
            ),
            "scene": render(
                "scene.html",
                page="domain:testsite",
                title="Scene",
                domains=domains,
                domain=domain,
                scene=scene,
                revisions=[replace(revision, note=None) for revision in REVISIONS],
                scenario=scenario,
                default_base_url=scenario.browser.base_url,
                runs=[run],
                needs=None,
                contract_data=CONTRACT,
                facts=FACTS,
            ),
            "section": render(
                "section.html",
                page="domain:testsite",
                title="Assertions",
                domains=domains,
                domain=domain,
                scene=scene,
                revision=REVISIONS[1],
                part="steps",
                text="steps:\n  - { id: open, action: goto, url: / }",
                scenario=scenario,
                facts=FACTS,
            ),
            **_m4_pages(scenario, english=True),
        }


@pytest.mark.parametrize(
    "name",
    [
        "domain",
        "domain-empty",
        "domains",
        "scene",
        "roles",
        "recording",
        "recording-detail",
        "debug-start",
        "debug-session",
    ],
)
def test_new_pages_have_no_untranslated_text(name: str) -> None:
    html = _english_domain_pages()[name]
    for native in NATIVE_NAMES.values():  # 語言切換選單用各語言自己的文字，不翻譯
        html = html.replace(native, "")
    leftovers = re.findall(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff60]+", html)
    assert leftovers == [], name


@pytest.mark.parametrize("locale", LOCALES)
def test_script_messages_keep_their_placeholders(locale: Locale) -> None:
    """portal.js 用 {name}、{ids} 代入值；字詞順序與標點由各語言的訊息決定。"""
    with use_locale(locale):
        messages = js_messages()
    assert "{name}" in messages["domain_delete_title"]
    assert "{ids}" in messages["imported"]
    assert messages["list_separator"]


def test_builtin_texts_follow_the_language() -> None:
    stored = "測試網站自動化"  # 第一次啟動時用伺服器的語言存進資料庫
    with use_locale("en"):
        assert follow_locale(stored, "domain.testsite_name") == "Test site automation"
        assert follow_locale("Test site automation", "domain.testsite_name") == (
            "Test site automation"
        )
    with use_locale("zh-Hans"):
        assert follow_locale(stored, "domain.testsite_name") == t("domain.testsite_name")
    with use_locale("en"):
        assert follow_locale("我們的測試", "domain.testsite_name") == "我們的測試"  # 改過的名稱
        assert follow_locale(None, "domain.testsite_description") is None


@pytest.mark.parametrize("display", [True, False])
def test_run_form_offers_headed_mode_when_a_window_can_be_shown(display: bool) -> None:
    """有圖形介面時預設有頭模式（顯示瀏覽器視窗）；沒有時只能無頭模式。"""
    scenario = _scenario()
    with use_locale("zh-Hant"):
        html = render(
            "run_form.html",
            page="domains",
            title="驗證",
            domains=DOMAINS,
            domain=None,
            scene=SCENE,
            revision=REVISIONS[0],
            scenario=scenario,
            purpose="validation",
            defaults={},
            engines=ENGINES,
            base_url=None,
            display=display,
        )
    headed = html.split('name="headless" value="0"')[1].split(">")[0]
    headless = html.split('name="headless" value="1"')[1].split(">")[0]
    text = _text(html)
    assert "顯示（有頭模式，headed）" in text
    assert "不顯示（無頭模式，headless）" in text
    if display:
        assert "checked" in headed
        assert "checked" not in headless
    else:
        assert "disabled" in headed
        assert "checked" in headless
        assert "沒有圖形介面" in text


def test_run_page_shows_the_browser_window_mode() -> None:
    with use_locale("en"):
        headless = _text(_pages()["run"])
        headed = _text(
            render(
                "run.html",
                page="runs",
                title="run",
                run=replace(RUN, headless=False),
                revision=REVISIONS[0],
                result=None,
                files=[],
                can_publish=False,
                role=None,
            )
        )
    assert "Hide (headless mode)" in headless
    assert "Show (headed mode)" in headed


def test_run_filters_are_menus_with_checkboxes() -> None:
    """執行報告的每個篩選條件都是同一種選單：按鈕顯示目前的選擇，點開勾選。"""
    scenes = [SCENE, replace(SCENE, id="ba-002", name="查詢範例紀錄")]
    with use_locale("zh-Hant"):
        filters = run_filters(
            scenes=scenes,
            categories=["範例資料"],
            selected={"scene": ["ba-001", "ba-002"], "status": ["failed"]},
        )
        html = render("runs.html", page="runs", title="報告", runs=[], filters=filters, limit=200)
    assert "<select" not in html.split('class="filters"')[1].split("</form>")[0]
    summaries = [
        _text(part.split("</summary>")[0])
        for part in html.split('<details class="filter-menu" data-filter-menu>')[1:]
    ]
    assert [" ".join(text.split()) for text in summaries] == [
        "分類 全部 ▾",
        "場景 2 項 ▾",
        "結果 失敗 ▾",
        "目的 全部 ▾",
    ]
    assert html.count("checked") == 3
    assert 'name="scene" value="ba-002" checked' in html
    assert 'href="/runs"' in html  # 有條件時顯示「清除篩選」


def test_many_scenes_get_a_search_box() -> None:
    scenes = [replace(SCENE, id=f"s-{index}") for index in range(9)]
    with use_locale("en"):
        few, many = (
            run_filters(scenes=items, categories=[], selected={})[1]
            for items in (scenes[:8], scenes)
        )
    assert not few.searchable
    assert many.searchable
