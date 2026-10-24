"""頁面樣板：用假的紀錄渲染每一頁（三種語言），確認訊息鍵、樣板變數都存在。不需要資料庫。"""

import re
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import cast

import pytest

from rpa_core.dsl import Scenario, validate_file, validate_text
from rpa_core.i18n import LOCALES, NATIVE_NAMES, Locale, use_locale
from rpa_core.workflow import Workflow, WorkflowProblem
from rpa_server.agents import SCOPES, ApiClientRecord, AuditRecord, ClientPolicy
from rpa_server.context import Via, use_recorder
from rpa_server.debugging import DebugSession
from rpa_server.debugging import _steps as debug_steps  # pyright: ignore[reportPrivateUsage]
from rpa_server.domain import (
    ENGINES,
    CompositeRevisionRecord,
    DependencyItem,
    DomainRecord,
    ProjectRecord,
    RecorderRecord,
    RecordingRecord,
    RevisionRecord,
    RoleRecord,
    RunRecord,
    SceneCard,
    SceneRecord,
    VerificationRecord,
    WorkerRecord,
    WorkflowNodeState,
    WorkflowRecord,
    WorkflowRunRecord,
)
from rpa_server.gitsync import Change, GitSource, SyncStatus
from rpa_server.i18n import follow_locale, t
from rpa_server.render import js_messages, render, run_filters, workflow_messages, workflow_preview
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
PROJECT = ProjectRecord("composites", "組合場景自動化", None, 0, 2, MOMENT)
OTHER_PROJECT = ProjectRecord("billing", "帳務專案", "帳務相關的組合場景", 1, 0, MOMENT)
PROJECTS = [PROJECT, OTHER_PROJECT]
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
    RevisionRecord(
        "ba-001", 2, "b" * 64, "dsl", "passed", "改步驟", MOMENT, None, False, verified=True
    ),
    RevisionRecord(
        "ba-001", 1, "a" * 64, "dsl", "passed", None, MOMENT, MOMENT, True, verified=True
    ),
]
VERIFICATIONS = [
    VerificationRecord(
        id="ba-001-20261010-083000-abcdef",
        revision=2,
        status="passed",
        matches=True,
        finished_at=MOMENT,
        by="jia-mac",
        server_id="3a9d",
        server_name="jia-mac",
        worker="local",
        engine="chromium",
        headless=True,
        here=True,
    ),
    VerificationRecord(
        id="ba-001-20261009-010000-123456",
        revision=1,
        status="failed",
        matches=True,
        finished_at=MOMENT,
        by="yi-mac",
        server_id="5f3a",
        server_name="yi-mac",
        worker="win-01",
        engine=None,
        headless=False,
        here=False,
    ),
]
SOURCE = GitSource(url="git@github.com:org/rpa-data.git", directory="testsite", auth="ssh")
SYNC = SyncStatus(
    "testsite",
    True,
    "conflict",
    source=SOURCE,
    public_key="ssh-ed25519 AAAAC3Nza rpa-portal-testsite",
    host_keys=("256 SHA256:abc github.com (ED25519)",),
    branch="main",
    synced_commit="a" * 40,
    remote_commit="b" * 40,
    remote_commits=2,
    changes=(Change("scenes/ba-001/revisions/3.yaml", "added", "revision", "ba-001", 3),),
    conflicts=("scenes/ba-001/scene.yaml",),
    checked_at="2026-10-20T05:00:00-07:00",
    synced_at="2026-10-20T04:00:00-07:00",
    pushed_branch="rpa/testsite-20261020-050000",
)
LOCAL_SYNC = SyncStatus("google", True, "local")
SERVER = {"id": "3a9d", "name": "jia-mac"}
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
LOCATIONS: dict[str, object] = {
    "remote": False,
    "local": True,
    "default": "local",
    "display": {"local": True, "remote": False, "any": True},
}
REMOTE_LOCATIONS: dict[str, object] = {
    "remote": True,
    "local": True,
    "default": "remote",
    "display": {"local": False, "remote": True, "any": True},
}
WORKER = WorkerRecord(
    id="win-01",
    name="Windows <測試機>",
    status="busy",
    disabled=False,
    created_at=MOMENT,
    last_seen_at=MOMENT,
    current_run="ba-001-20261010-083000-abcdef",
    protocol=1,
    fingerprint="0123456789abcdef",
    same_version=False,
    os="Windows 11",
    python="3.13.1",
    host="WIN-01",
    browsers=("chromium", "firefox"),
    display=True,
    version="0.1.0",
)
WORKER_NAMES = {"local": "本機", "win-01": "Windows <測試機>"}
AGENT = ApiClientRecord(
    id="agent-erp",
    name="ERP 助理",
    description="訂單助理",
    key_prefix="rpa_ak_AbCd",
    policy=ClientPolicy(
        scopes=("scenes:read", "scenes:write", "debug", "runs:validate", "runs:read"),
        domains=("sales",),
        recorders=("mac-01",),
        target="remote",
        workers=("local",),
        page_content=True,
    ),
    disabled=False,
    created_at=MOMENT,
    last_used_at=MOMENT,
)
AUDIT = AuditRecord(
    id=1,
    at=MOMENT,
    client_id="agent-erp",
    client_name="ERP 助理",
    method="POST",
    action="/scenes/{scene_id}/revisions",
    target="order-create",
    status=201,
    code=None,
    ip="192.168.1.30",
)
RECORDER = RecorderRecord(
    id="mac-01",
    name="Amy 的 Mac",
    status="busy",
    disabled=False,
    created_at=MOMENT,
    last_seen_at=MOMENT,
    protocol=1,
    fingerprint="0123456789abcdef",
    same_version=True,
    version="0.3.0",
    os="macOS 15.4",
    host="amy-mac",
    browsers=("chromium",),
    display=True,
    active=1,
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
        session={
            "status": "waiting",
            "message": t("role.login_not_yet", url="https://e.example/login"),
        },
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
            check_unavailable={"firefox": t("roles.check_unavailable", browser="Firefox")},
            busy=True,
            engines=ENGINES,
            check_text=_check_text,
            role_values=_role_values,
            auto_example="- { id: open, action: goto, url: https://example.com }",
            domain_names={},
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
            counts={"steps": 4, "inputs": 2, "outputs": 1, "verify": 1, "secrets": 0},
        ),
        "debug-start": render(
            "debug.html",
            page="domain:testsite",
            title="Debug",
            domains=domains,
            projects=PROJECTS,
            session=None,
            **common,
        ),
        "debug-session": render(
            "debug.html",
            page="domain:testsite",
            title="Debug",
            domains=domains,
            projects=PROJECTS,
            session=session,
            **common,
        ),
    }


CHAIN = Workflow.model_validate(
    {
        "nodes": [
            {"id": "n1", "sceneId": "ba-001", "revision": 1, "inputs": {"title": {"value": "x"}}},
            {
                "id": "n2",
                "sceneId": "ba-002",
                "revision": 1,
                "inputs": {"recordId": {"node": "n1", "output": "recordId"}},
            },
        ]
    }
)


def _source(kind: str, **fields: object) -> dict[str, object]:
    return {"kind": kind, "node": None, "output": None, "value": None, **fields}


def _m6_pages(*, english: bool = False) -> dict[str, str]:
    """自由試驗場（M6）：序列清單、編輯序列、序列的執行（通過、需要登入、執行中）；
    專案空間的專案頁與專案管理（2026-10-23）。"""
    domains = (
        [replace(DOMAIN, name="Lab"), replace(OTHER_DOMAIN, name="Other")] if english else DOMAINS
    )
    projects = (
        [
            replace(PROJECT, name="Composite automation"),
            replace(OTHER_PROJECT, name="Billing", description="Billing flows"),
        ]
        if english
        else PROJECTS
    )
    name = "Create then look up" if english else "建立後查詢"
    run = (
        replace(RUN, scene_name="Scene", input={"title": "x"}, output={"recordId": "DEMO-1"})
        if english
        else RUN
    )
    first = WorkflowNodeState(
        0,
        "n1",
        "ba-001",
        run.scene_name,
        1,
        "passed",
        {"title": _source("value", value="x"), "quantity": _source("default", value=12)},
        replace(run, purpose="workflow", workflow_run_id="wf1-x", node_id="n1"),
    )
    second = WorkflowNodeState(
        1,
        "n2",
        "ba-002",
        "Look up" if english else "查詢範例紀錄",
        1,
        "passed",
        {"recordId": _source("output", node="n1", output="recordId")},
        replace(run, id="ba-002-x", purpose="workflow", workflow_run_id="wf1-x", node_id="n2"),
    )
    passed = WorkflowRunRecord(
        id="wf1-20261013-083000-abcdef",
        workflow_id=1,
        workflow_name=name,
        workflow_version=2,
        status="passed",
        engine=None,
        headless=True,
        error=None,
        failed_node=None,
        resumed_from=None,
        cancel_requested=False,
        created_at=MOMENT,
        finished_at=MOMENT,
        nodes=(first, second),
    )
    login = replace(
        passed,
        id="wf1-20261013-084000-abcdef",
        status="needs_login",
        error="Node n2 stopped" if english else "節點 n2 需要登入",
        failed_node="n2",
        resumed_from=passed.id,
        nodes=(replace(first, status="reused"), replace(second, status="needs_login")),
    )
    running = replace(
        passed,
        status="running",
        finished_at=None,
        nodes=(replace(first, status="running"), replace(second, status="pending", run=None)),
    )
    blocked = replace(
        passed,
        status="failed",
        error="Node n2 did not start" if english else "節點 n2 沒有開始執行",
        failed_node="n2",
        nodes=(first, replace(second, status="failed", run=None, error="recordId")),
    )
    problem = WorkflowProblem(
        "workflow.input_missing", "Node n2: no source" if english else "缺少來源", "n2", "recordId"
    )
    record = WorkflowRecord(
        1,
        name,
        None,
        CHAIN,
        2,
        MOMENT,
        MOMENT,
        (problem,),
        passed,
        code="wf-1",
        domain_id="composites",
        published_number=1,
        dependency="warnings",
        project_id="composites",
    )
    revisions = [
        CompositeRevisionRecord(2, "b" * 64, "draft", True, None, None, MOMENT, None, False),
        CompositeRevisionRecord(1, "a" * 64, "passed", True, None, "v1", MOMENT, MOMENT, True),
    ]
    dependencies = [
        DependencyItem(
            "warning",
            "role_login",
            "Role buyer needs login" if english else "角色 buyer 需要登入",
            2,
            "ba",
            "ba-001",
            "login",
        ),
        DependencyItem(
            "error",
            "domain_missing",
            "Domain hr is missing" if english else "沒有領域 hr",
            2,
            "hr",
            "hr-001",
            "add_domain",
            {"url": "https://github.com/org/rpa-data.git", "directory": "hr"},
        ),
    ]
    data = {
        "id": 1,
        "name": name,
        "description": "",
        "version": 2,
        "definition": CHAIN.to_json(),
        "problems": [problem.to_json()],
        "library": [],
        "display": False,
        "engines": list(ENGINES),
        "locations": REMOTE_LOCATIONS,
    }
    common: dict[str, object] = {"messages": workflow_messages()}
    return {
        "project": render(
            "project.html",
            page="project:composites",
            domains=(),
            projects=projects,
            **common,
            title=projects[0].name,
            project=projects[0],
            workflows=[record, replace(record, id=2, domain_id=None, published_number=None)],
            data=data,
            runs=[passed],
            has_published=True,
            domain_names={"composites": "Composites"},
        ),
        "project-empty": render(
            "project.html",
            page="project:billing",
            domains=domains,
            projects=projects,
            **common,
            title=projects[1].name,
            project=projects[1],
            workflows=[],
            data=data,
            runs=[],
            has_published=False,
            domain_names={},
        ),
        "projects": render(
            "projects.html",
            page="projects",
            domains=domains,
            projects=projects,
            title=t("nav.projects"),
            unassigned=[replace(record, id=3, code="wf-3", project_id=None)],
        ),
        "projects-empty": render(
            "projects.html",
            page="projects",
            domains=domains,
            title=t("nav.projects"),
            unassigned=[],
        ),
        "playground": render(
            "playground.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=t("nav.playground"),
            workflows=[
                record,
                replace(record, id=2, workflow=Workflow(), problems=(), last_run=None),
            ],
            runs=[passed, login, running],
            has_published=True,
            **common,
        ),
        "playground-empty": render(
            "playground.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=t("nav.playground"),
            workflows=[],
            runs=[],
            has_published=False,
            **common,
        ),
        "workflow": render(
            "workflow.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=name,
            workflow=record,
            project=projects[0],
            data=data,
            runs=[passed],
            revisions=revisions,
            verifications=VERIFICATIONS,
            dependencies=dependencies,
            **common,
        ),
        "workflow-run": render(
            "workflow_run.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=passed.id,
            run=passed,
            workflow_exists=True,
            project=projects[0],
            role=None,
            **common,
        ),
        "workflow-run-login": render(
            "workflow_run.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=login.id,
            run=login,
            project=None,
            workflow_exists=False,
            role="testsite-user",
            **common,
        ),
        "workflow-running": render(
            "workflow_run.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=running.id,
            run=running,
            project=None,
            workflow_exists=True,
            role=None,
            **common,
        ),
        "workflow-blocked": render(
            "workflow_run.html",
            page="playground",
            domains=domains,
            projects=projects,
            title=blocked.id,
            run=blocked,
            project=None,
            workflow_exists=True,
            role=None,
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
            sync=SYNC,
            can_import=True,
        ),
        "domain-empty": render(
            "domain.html",
            page="domain:google",
            title=OTHER_DOMAIN.name,
            domains=DOMAINS,
            domain=OTHER_DOMAIN,
            cards=[],
            sync=LOCAL_SYNC,
            can_import=False,
        ),
        "domains": render(
            "domains.html",
            page="domains",
            title="領域管理",
            domains=DOMAINS,
            unassigned=[replace(SCENE, id="loose", domain_id=None)],
            syncs={DOMAIN.id: SYNC, OTHER_DOMAIN.id: LOCAL_SYNC},
            server=SERVER,
            git_available=True,
            dependents={},
        ),
        "domain-sync": render(
            "domain_sync.html",
            page="domain:testsite",
            title="資料來源與同步",
            domains=DOMAINS,
            domain=DOMAIN,
            sync=SYNC,
            source=SOURCE,
            server=SERVER,
        ),
        "scene": render(
            "scene.html",
            page="domain:testsite",
            title=SCENE.name,
            domains=DOMAINS,
            domain=DOMAIN,
            scene=SCENE,
            revisions=REVISIONS,
            verifications=VERIFICATIONS,
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
            locations=LOCATIONS,
        ),
        "run-form-remote": render(
            "run_form.html",
            page="domains",
            title="執行",
            domains=DOMAINS,
            domain=None,
            scene=replace(SCENE, domain_id=None),
            revision=REVISIONS[0],
            scenario=scenario,
            purpose="execution",
            defaults={"title": "x"},
            engines=ENGINES,
            base_url=None,
            display=True,
            locations=REMOTE_LOCATIONS,
        ),
        "runs-remote": render(
            "runs.html",
            page="runs",
            title="報告",
            runs=[
                replace(RUN, target="remote", worker_id="win-01"),
                replace(RUN, id="queued", status="queued", target="any", worker_id=None),
            ],
            filters=run_filters(scenes=[SCENE], categories=[], selected={}),
            limit=200,
            worker_names=WORKER_NAMES,
        ),
        "run-remote": render(
            "run.html",
            page="runs",
            title="執行",
            run=replace(RUN, target="remote", worker_id="win-01"),
            revision=REVISIONS[0],
            result=RESULT,
            files=["report.html"],
            can_publish=False,
            role=None,
            worker_names=WORKER_NAMES,
        ),
        "workers": render(
            "workers.html",
            page="workers",
            title="遠端 Worker",
            workers=[
                WORKER,
                replace(
                    WORKER,
                    id="mac",
                    name="Mac",
                    status="offline",
                    disabled=True,
                    last_seen_at=None,
                    current_run=None,
                    fingerprint=None,
                    same_version=True,
                ),
            ],
            recorders=[RECORDER, replace(RECORDER, id="mac-02", status="disabled", disabled=True)],
            default_target="any",
            targets=("local", "remote", "any"),
            local_worker=False,
            worker_port=8081,
            api_url="http://192.168.1.10:8081",
            fingerprint="fedcba9876543210",
        ),
        "agents": render(
            "agents.html",
            page="agents",
            title="API 用戶端",
            agents=[
                AGENT,
                replace(
                    AGENT,
                    id="agent-old",
                    name="舊系統 <b>",
                    disabled=True,
                    policy=ClientPolicy(domains=(), expires_at=MOMENT, allowed_ips=("10.0.0.0/8",)),
                ),
            ],
            audit=[AUDIT, replace(AUDIT, id=2, status=403, code="scope_missing", target=None)],
            audit_client=None,
            scopes=SCOPES,
            targets=("local", "remote", "any"),
            recorders=[RECORDER],
            workers=[WORKER],
            local_worker=True,
            worker_port=8081,
            api_url="http://192.168.1.10:8081",
            now=MOMENT,
        ),
        "agents-empty": render(
            "agents.html",
            page="agents",
            title="API 用戶端",
            agents=[],
            audit=[],
            audit_client="agent-erp",
            scopes=SCOPES,
            targets=("local", "remote", "any"),
            recorders=[],
            workers=[],
            local_worker=False,
            worker_port=None,
            api_url=None,
            now=MOMENT,
        ),
        "workers-empty": render(
            "workers.html",
            page="workers",
            title="遠端 Worker",
            workers=[],
            recorders=[],
            default_target="local",
            targets=("local", "remote", "any"),
            local_worker=True,
            worker_port=None,
            api_url=None,
            fingerprint="fedcba9876543210",
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
        **_m6_pages(),
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
    assert "舊系統 &lt;b&gt;" in pages["agents"]


def test_scene_page_shows_versions_and_contract() -> None:
    with use_locale("zh-Hant"):
        html = _pages()["scene"]
    text = _text(html)
    assert 'data-action="publish" data-scene="ba-001" data-revision="2"' in html
    assert "已發布" in text
    assert 'id="contract-preview-defaults"' in html
    assert 'id="contract-preview-sample"' in html
    assert 'id="contract-preview-mapping"' in html
    assert 'id="contract-inputs"' in html
    assert 'id="contract-outputs"' in html


def test_running_page_polls() -> None:
    with use_locale("en"):
        html = _pages()["run-queued"]
    assert "data-poll" in html
    assert 'data-action="cancel-run"' in html
    assert "Automation" in _text(html)


@pytest.mark.parametrize("name", ["portal.css", "shell.js"])
def test_design_system_assets_are_unchanged_copies(name: str) -> None:
    """Portal 的 portal.css、shell.js 是設計系統的原檔；要改請先改 docs/design-system 再複製。"""
    static = ROOT / "apps" / "server" / "src" / "rpa_server" / "static" / name
    original = ROOT / "docs" / "design-system" / "assets" / name
    assert static.read_bytes() == original.read_bytes()


def _menu(html: str, menu: str) -> list[str]:
    """選單（topnav、sidenav）裡的連結，依顯示的順序。"""
    return re.findall(r'href="([^"]+)"', html.split(f'id="{menu}"')[1].split("</nav>")[0])


def test_side_menu_lists_domains_then_roles() -> None:
    """2026-10-22：領域 ×N，登入與憑證放最後；領域管理搬到管理後台。
    2026-10-23：「組合場景自動化」換成專案空間的專案，場景管理不再列它。"""
    with use_locale("zh-Hant"):
        html = _pages()["domain"]
    side = html.split('id="sidenav"')[1].split("</nav>")[0]
    labels = [part.split("</span>")[0] for part in side.split("<span>")[1:]]
    assert labels == ["測試網站自動化", "谷歌自動化", "登入與憑證"]
    current = 'href="/domains/testsite" title="測試網站自動化" class="active" aria-current="page"'
    assert current in side


def test_top_menu_has_six_groups_on_the_server() -> None:
    """三段分工：伺服器本機看得到全部第一級選單；二級選單依調整後的分組。
    2026-10-23：專案空間放在叢集管理前面，二級選單是專案；管理後台多了專案管理。"""
    with use_locale("zh-Hant"):
        pages = _pages()
    html = pages["domain"]
    assert _menu(html, "topnav") == [
        "/scenes",
        "/recording",
        "/runs",
        "/workspace",
        "/devices",
        "/domains",
    ]
    top = html.split('id="topnav"')[1].split("</nav>")[0]
    assert [part.split("</a>")[0].split(">")[-1] for part in top.split("<a ")[1:]] == [
        "場景管理",
        "場景生產",
        "場景運行",
        "專案空間",
        "叢集管理",
        "管理後台",
    ]
    assert _menu(pages["recording"], "sidenav") == ["/recording", "/playground"]
    assert _menu(pages["runs"], "sidenav") == ["/runs", "/replay"]
    assert _menu(pages["project"], "sidenav") == ["/projects/composites", "/projects/billing"]
    assert _menu(pages["workers"], "sidenav") == ["/devices"]
    assert _menu(pages["domains"], "sidenav") == ["/domains", "/projects", "/agents"]
    assert _menu(pages["projects"], "sidenav") == ["/domains", "/projects", "/agents"]
    assert 'class="active" aria-current="true">場景運行' in pages["runs"]
    assert 'class="active" aria-current="true">專案空間' in pages["project"]
    assert 'href="/projects/composites" title="組合場景自動化" class="active"' in pages["project"]
    assert 'class="active" aria-current="true">管理後台' in pages["domains"]
    assert 'class="active" aria-current="true">管理後台' in pages["projects"]
    assert 'href="/projects" title="專案管理" class="active"' in pages["projects"]
    assert 'href="/domains">' in pages["domain"]  # 領域頁的「管理領域」
    assert 'href="/projects">' in pages["project"]  # 專案頁的「管理專案」


def test_domain_management_orders_the_domains() -> None:
    """領域管理（管理後台）：每一列上移、下移；第一列不能上移，最後一列不能下移。"""
    with use_locale("zh-Hant"):
        html = _pages()["domains"]
    assert "場景管理左側的領域選單照這個順序" in html
    rows = (
        html.split('id="domain-order"')[1].split("<tbody>")[1].split("</tbody>")[0].split("</tr>")
    )
    first, last = rows[0], rows[-2]
    assert '<span class="order-number" data-order-number>1</span>' in first
    assert 'aria-label="上移「測試網站自動化」" disabled' in first
    assert 'aria-label="下移「測試網站自動化」">' in first
    assert 'data-direction="down"' in last
    assert last.split('data-direction="down"')[1].split(">")[0].endswith(" disabled")


def _waiting_run() -> str:
    """排隊中、等待遠端 worker 的執行頁（有連到裝置頁的按鈕）。"""
    queued = replace(RUN, status="queued", target="remote", finished_at=None)
    return render(
        "run.html",
        page="runs",
        title="執行",
        run=queued,
        revision=REVISIONS[0],
        result=None,
        files=[],
        can_publish=False,
        role=None,
        worker_wait={"worker": None},
    )


def test_recorders_hide_cluster_and_admin_menus_by_default() -> None:
    """三段分工：透過錄製端時，叢集管理與管理後台只在裝置頁替那台打開時顯示。"""
    with use_locale("zh-Hant"), use_recorder(Via("mac-01", "Mac")):
        hidden = {**_pages(), "run-waiting": _waiting_run()}
    with use_locale("zh-Hant"), use_recorder(Via("mac-01", "Mac", ("cluster",))):
        cluster = {**_pages(), "run-waiting": _waiting_run()}
    # 專案空間取代場景管理裡的「組合場景自動化」，錄製端照樣顯示（2026-10-23）
    assert _menu(hidden["domain"], "topnav") == ["/scenes", "/recording", "/runs", "/workspace"]
    assert 'href="/domains"' not in hidden["domain"]  # 領域頁的「管理領域」也不顯示
    assert 'href="/projects"' not in hidden["project"]  # 專案頁的「管理專案」也不顯示
    assert _menu(hidden["project"], "sidenav") == ["/projects/composites", "/projects/billing"]
    assert "data-worker-wait" in hidden["run-waiting"]
    assert 'href="/devices"' not in hidden["run-waiting"]  # 等待 worker 時不連到裝置頁
    assert _menu(cluster["domain"], "topnav") == [
        "/scenes",
        "/recording",
        "/runs",
        "/workspace",
        "/devices",
    ]
    assert 'href="/domains"' not in cluster["domain"]
    assert 'href="/devices"' in cluster["run-waiting"]
    # 只是不顯示：直接打開時照樣渲染（M8 才有權限）
    assert _menu(hidden["workers"], "sidenav") == ["/devices"]


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
    # 連結列只有設計稿的五項；「調試」：DSL 場景打開逐步調試，腳本場景驗證最新版本
    links = published.split('class="card-links')[1].split("</nav>")[0]
    assert links.count("<a ") == 5
    assert "逐步調試" not in _text(published)
    assert 'href="/scenes/ba-001/debug" title=' in published
    assert 'href="/scenes/ba-009/run?purpose=validation"' in draft
    assert "範例資料" in _text(published)  # 右上角是分類
    assert "2 個場景" in _text(html)


def test_scene_page_lists_validation_records_from_every_server() -> None:
    with use_locale("zh-Hant"):
        html = _pages()["scene"]
    panel = html.split('id="verifications"')[1].split("</section>")[0]
    text = _text(panel)
    assert "驗證紀錄" in text
    # 這台的紀錄連到報告；別台的只顯示執行編號與在哪一台
    assert 'href="/runs/ba-001-20261010-083000-abcdef"' in panel
    assert 'href="/runs/ba-001-20261009-010000-123456"' not in panel
    assert "報告在 yi-mac" in text
    assert "win-01 · —" in text
    # 有雜湊相符的通過紀錄才顯示「發布」
    assert 'data-action="publish" data-scene="ba-001" data-revision="2"' in html


def test_domain_page_shows_load_problems_and_reload() -> None:
    problem = {
        "path": "scenes/ba-002/scene.yaml",
        "line": 2,
        "code": "pack.scene_id_mismatch",
        "message": "scene.yaml 的 id 是 x",
        "severity": "error",
    }
    with use_locale("zh-Hant"):
        html = render(
            "domain.html",
            page="domain:testsite",
            title=DOMAIN.name,
            domains=DOMAINS,
            domain=replace(DOMAIN, problems=(problem,), loaded_at=MOMENT),
            cards=[],
            sync=LOCAL_SYNC,
            can_import=False,
        )
    assert 'data-action="reload-domain" data-domain="testsite"' in html
    details = html.split('id="domain-problems"')[1].split("</details>")[0]
    assert " open>" in details
    assert "scenes/ba-002/scene.yaml:2" in details
    assert "1 個問題" in _text(details)


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
                sync=SYNC,
                can_import=True,
            ),
            "domain-empty": render(
                "domain.html",
                page="domain:google",
                title="Other",
                domains=domains,
                domain=domains[1],
                cards=[],
                sync=LOCAL_SYNC,
                can_import=False,
            ),
            "domains": render(
                "domains.html",
                page="domains",
                title=t("nav.domains"),
                domains=domains,
                unassigned=[replace(scene, id="loose", domain_id=None)],
                syncs={domain.id: SYNC, domains[1].id: LOCAL_SYNC},
                server=SERVER,
                git_available=True,
                dependents={},
            ),
            "domain-sync": render(
                "domain_sync.html",
                page="domain:testsite",
                title="Source & sync",
                domains=domains,
                domain=domain,
                sync=SYNC,
                source=SOURCE,
                server=SERVER,
            ),
            "scene": render(
                "scene.html",
                page="domain:testsite",
                title="Scene",
                domains=domains,
                domain=domain,
                scene=scene,
                revisions=[replace(revision, note=None) for revision in REVISIONS],
                verifications=VERIFICATIONS,
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
            **_m6_pages(english=True),
            "workers": render(
                "workers.html",
                page="workers",
                title=t("nav.workers"),
                workers=[
                    replace(WORKER, name="Windows PC", os="Windows", host="PC"),
                    replace(WORKER, id="mac", name="Mac", status="disabled", disabled=True),
                ],
                recorders=[replace(RECORDER, name="Amy Mac")],
                default_target="remote",
                targets=("local", "remote", "any"),
                local_worker=False,
                worker_port=8081,
                api_url="http://10.0.0.2:8081",
                fingerprint="0" * 16,
            ),
            "workers-empty": render(
                "workers.html",
                page="workers",
                title=t("nav.workers"),
                workers=[],
                recorders=[],
                default_target="local",
                targets=("local", "remote", "any"),
                local_worker=True,
                worker_port=None,
                api_url=None,
                fingerprint="0" * 16,
            ),
            "run-form-remote": render(
                "run_form.html",
                page="domain:testsite",
                title="Run",
                domains=domains,
                domain=domain,
                scene=scene,
                revision=REVISIONS[0],
                scenario=scenario,
                purpose="execution",
                defaults={},
                engines=ENGINES,
                base_url=None,
                display=True,
                locations=REMOTE_LOCATIONS,
            ),
            "run-remote": render(
                "run.html",
                page="runs",
                title="Run",
                run=replace(run, target="remote", worker_id="win-01"),
                revision=REVISIONS[0],
                result=None,
                files=[],
                can_publish=False,
                role=None,
                worker_names={"local": t("worker.local"), "win-01": "Windows PC"},
            ),
        }


@pytest.mark.parametrize(
    "name",
    [
        "domain",
        "domain-empty",
        "domains",
        "domain-sync",
        "scene",
        "roles",
        "recording",
        "recording-detail",
        "debug-start",
        "debug-session",
        "playground",
        "playground-empty",
        "project",
        "project-empty",
        "projects",
        "projects-empty",
        "workflow",
        "workflow-run",
        "workflow-run-login",
        "workflow-running",
        "workflow-blocked",
        "workers",
        "workers-empty",
        "run-form-remote",
        "run-remote",
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
            locations=LOCATIONS,
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


def test_dynamic_defaults_are_marked_and_kept_as_written() -> None:
    """入參的動態值：入參表格標示「動態值」，執行表單的 JSON 照原本的寫法帶入。"""
    text = (
        "schemaVersion: 1\nid: ba-001\nname: 採購\ninputs:\n"
        "  arrivalDate: { default: '{{today}}' }\n"
        "  department: { default: 測試部 }\n"
        "steps:\n  - { id: open, action: goto, url: https://example.test/ }\n"
    )
    scenario = validate_text(text).scenario
    assert scenario is not None
    pages: dict[str, str] = {}
    for locale in ("zh-Hant", "en"):
        with use_locale(locale):
            pages[locale] = render(
                "run_form.html",
                page="domains",
                title="驗證",
                domains=DOMAINS,
                domain=None,
                scene=SCENE,
                revision=REVISIONS[0],
                scenario=scenario,
                purpose="validation",
                defaults={"arrivalDate": "{{today}}", "department": "測試部"},
                engines=ENGINES,
                base_url=None,
                display=True,
                locations=LOCATIONS,
            )
    html = pages["zh-Hant"]
    assert html.count('class="badge blue"') == 1
    assert "動態值" in _text(html)
    assert '"arrivalDate": "{{today}}"' in _text(html)
    assert "{{today}}、{{today+1}}、{{random:10:30}}" in _text(html)
    assert "dynamic" in _text(pages["en"])


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


def test_workflow_pages_show_sources_and_actions() -> None:
    """序列執行頁：入參的值與來源、停下的節點可以「繼續」、執行中會輪詢；節點執行頁連回序列。"""
    with use_locale("zh-Hant"):
        pages = _m6_pages()
        node_run = render(
            "run.html",
            page="runs",
            title="n2",
            domains=DOMAINS,
            role=None,
            run=replace(RUN, purpose="workflow", workflow_run_id="wf1-x", node_id="n2"),
            revision=REVISIONS[0],
            result=RESULT,
            files=[],
            can_publish=False,
        )
    passed = pages["workflow-run"]
    assert "<code>title</code> = <code>&#34;甲&#34;</code>" in passed  # 那次執行實際的入參
    assert "<code>n1.recordId</code>" in passed
    assert 'data-resume="1"' not in passed
    login = pages["workflow-run-login"]
    assert 'data-resume="1"' in login
    assert "從 n2 繼續" in login
    assert 'href="/roles#role-testsite-user"' in login
    assert 'data-status="reused"' in login
    assert "data-poll" in pages["workflow-running"]
    assert 'data-signature="running|running,pending"' in pages["workflow-running"]
    assert 'data-node="n2" data-status="failed" class="is-stopped"' in pages["workflow-blocked"]
    editor = pages["workflow"]
    assert 'id="workflow-data"' in editor
    assert "缺少來源" in editor
    assert '"binding_output": "{name} \\u2190 {node}.{output}"' in editor  # tojson 跳脫非 ASCII
    assert 'href="/playground/runs/wf1-x"' in node_run
    assert 'data-action="rerun"' not in node_run


def test_waiting_for_a_worker_is_explained() -> None:
    """M9a 收尾：排隊中、沒有線上的遠端 worker 時說明在等什麼，並連到裝置頁。"""
    queued = replace(RUN, status="queued", target="remote", finished_at=None)
    with use_locale("zh-Hant"):
        pages = {
            name: render(
                "run.html",
                page="runs",
                title="執行",
                run=queued,
                revision=REVISIONS[0],
                result=None,
                files=[],
                can_publish=False,
                role=None,
                worker_wait=wait,
            )
            for name, wait in (
                ("any", {"worker": None}),
                ("named", {"worker": "Windows <測試機>"}),
                ("none", None),
            )
        }
    assert "目前沒有線上的遠端 worker" in _text(pages["any"])
    assert 'href="/devices"' in pages["any"].split("data-worker-wait")[1]
    assert "等待 worker「Windows &lt;測試機&gt;」" in pages["named"]
    assert "data-worker-wait" not in pages["none"]


def test_location_filter_and_local_url_warning() -> None:
    """有遠端 worker 時執行報告多一個「執行位置」篩選；執行表單有網址指向本機的提醒（預設隱藏）。"""
    with use_locale("zh-Hant"):
        filters = run_filters(
            scenes=[SCENE],
            categories=[],
            selected={"worker": ["win-01"]},
            locations=[("local", "本機"), ("win-01", "Windows")],
        )
        html = render("runs.html", page="runs", title="報告", runs=[], filters=filters, limit=200)
        alone = run_filters(scenes=[SCENE], categories=[], selected={}, locations=[])
        form = _pages()["run-form-remote"]
    assert [menu.name for menu in filters][-1] == "worker"
    assert len(alone) == 4
    assert 'name="worker" value="win-01" checked' in html
    assert "執行位置 Windows" in " ".join(_text(html).split())
    assert "data-local-url-warning hidden" in form


def test_remote_worker_pages() -> None:
    """M9a：執行位置的選項、由哪台 worker 執行、遠端 Worker 頁（名稱要跳脫）。"""
    with use_locale("zh-Hant"):
        pages = _pages()
    assert 'name="target"' not in pages["run-form"]  # 沒有遠端 worker 時不顯示
    form = pages["run-form-remote"]
    assert "data-target-choice" in form
    assert 'value="remote" checked' in form
    runs = _text(pages["runs-remote"])
    assert "在 Windows <測試機> 執行" in runs
    assert "任一（誰有空誰執行）" in runs
    assert "Windows &lt;測試機&gt;" in pages["run-remote"]
    workers = pages["workers"]
    assert 'id="worker-win-01"' in workers
    assert 'data-api-url="http://192.168.1.10:8081"' in workers
    assert "和 Portal 的程式版本不同" in _text(workers)
    assert 'data-action="enable-worker" data-kind="worker" data-worker="mac"' in workers
    assert 'value="local" disabled' in workers  # --no-local-worker
    assert "rpa serve --worker-port 8081" in _text(pages["workers-empty"])
    cluster = pages["workers"].split('id="sidenav"')[1].split("</nav>")[0]
    assert 'href="/devices"' in cluster
    assert "裝置" in _text(cluster)
    # M10.1：重新邀請取代重新產生權杖；停用的裝置與沒開對外埠時不能邀請
    assert 'data-action="invite-worker" data-kind="worker" data-worker="win-01"' in workers
    assert 'data-action="invite-worker" data-kind="worker" data-worker="mac"' not in workers
    assert "rotate-worker" not in workers
    assert "App 0.1.0" in _text(workers)
    assert 'id="worker-invite"' in workers
    assert 'data-action="new-worker" disabled' in pages["workers-empty"]
    assert 'data-action="new-worker" disabled' not in workers
    # M10.2：錄製端的清單與種類
    assert 'id="recorder-mac-01"' in workers
    assert 'data-action="invite-worker" data-kind="recorder" data-worker="mac-01"' in workers
    assert 'data-action="invite-worker" data-kind="recorder" data-worker="mac-02"' not in workers
    assert 'data-action="enable-worker" data-kind="recorder" data-worker="mac-02"' in workers
    text = _text(workers)
    assert "Amy 的 Mac" in text
    assert "使用中" in text
    assert "1 個錄製、調試或人工登入進行中" in text
    assert '<option value="recorder">RPA 錄製端</option>' in workers
    assert 'data-app="recorder" hidden' in workers
    assert "還沒有錄製端" in _text(pages["workers-empty"])


def test_pages_through_a_recorder_say_server_for_local() -> None:
    """M10.2：透過錄製端看頁面時，頁首標出哪台，「本機」改稱「伺服器」。"""
    with use_locale("zh-Hant"):
        plain = _pages()["run-form-remote"]
        with use_recorder(Via("mac-01", "Amy <Mac>")):
            pages = _pages()
    assert 'id="via-recorder"' not in plain
    form = pages["run-form-remote"]
    assert 'id="via-recorder"' in form
    assert "透過錄製端「Amy &lt;Mac&gt;」" in form
    assert "伺服器（執行 Portal 的電腦）" in _text(form)
    assert "本機（這台電腦）" not in _text(form)


@pytest.mark.parametrize("mode", ["serial", "explicit", "binding"])
def test_workflow_preview_preserves_layout_and_dependencies(mode: str) -> None:
    definition = CHAIN.model_dump(by_alias=True, exclude_none=True)
    definition["nodes"][0]["position"] = {"x": 650, "y": 220}
    definition["nodes"][1]["position"] = {"x": 20, "y": 40}
    if mode != "serial":
        definition.update(version=2, mode="dag", edges=[])
    if mode != "binding":
        definition["nodes"][1]["inputs"] = {}
    if mode == "explicit":
        definition["edges"] = [{"source": "n1", "target": "n2"}]
    workflow = Workflow.model_validate(definition)
    before = workflow.model_dump()
    preview = workflow_preview(workflow)
    assert workflow.model_dump() == before
    assert preview["nodes"] == [
        {"id": "n1", "scene": "ba-001", "revision": 1, "x": 650, "y": 220},
        {"id": "n2", "scene": "ba-002", "revision": 1, "x": 20, "y": 40},
    ]
    edges = cast(list[dict[str, str]], preview["edges"])
    assert len(edges) == 1
    assert edges[0]["source"] == "n1"
    assert edges[0]["target"] == "n2"
    # 反向排布時也包含曲線控制點，不能只裁出節點矩形。
    left, top, width, height = map(float, str(preview["viewbox"]).split())
    assert left < 20
    assert left + width > 850
    assert top < 40
    assert top + height > 316
