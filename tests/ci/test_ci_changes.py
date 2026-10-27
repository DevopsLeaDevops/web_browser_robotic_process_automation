"""tools/ci_changes.py：執行範圍（只改文件的推送）與依層建置（輸入指紋、外殼鍵、通過紀錄）。"""

import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from fnmatch import fnmatch
from pathlib import Path

import pytest

from tools import ci_changes
from tools.ci_changes import Decision, decide, docs_only, nightly_matrix

REPO = "owner/repo"
BEFORE = "b" * 40
HEAD = "c" * 40

type Runner = Callable[[Sequence[str]], str | None]
type Json = Mapping[str, object]


def fake(
    *,
    pushed: Sequence[str],
    whole: Sequence[str] | None = None,
    previous: str | None = "success",
) -> Runner:
    """假的命令執行：before→head 是 ``pushed``，merge-base→head 是 ``whole``。"""
    runs = [] if previous is None else [_run(previous)]

    def runner(command: Sequence[str]) -> str | None:
        match list(command):
            case ["git", "cat-file", *_] | ["git", "fetch", *_]:
                return ""
            case ["git", "merge-base", *_]:
                return "a" * 40 + "\n"
            case ["git", "diff", "--name-only", base, _]:
                files = pushed if base == BEFORE else (whole if whole is not None else pushed)
                return "\n".join(files) + "\n"
            case ["gh", "api", url] if f"head_sha={BEFORE}" in url:
                return json.dumps({"workflow_runs": runs})
            case _:
                return None

    return runner


def _run(conclusion: str) -> Mapping[str, object]:
    return {
        "status": "completed",
        "conclusion": conclusion,
        "event": "pull_request",
        "created_at": "2026-10-19T10:00:00Z",
        "html_url": "https://github.com/owner/repo/actions/runs/1",
    }


def pull_request(action: str = "synchronize") -> Mapping[str, object]:
    return {
        "action": action,
        "before": BEFORE,
        "pull_request": {"head": {"sha": HEAD}, "base": {"sha": "d" * 40}},
    }


def test_docs_only() -> None:
    assert docs_only(["handoff/tasks/x.html", "docs/en/index.html", "README.md"])
    assert not docs_only(["handoff/tasks/x.html", "apps/server/src/rpa_server/app.py"])
    assert not docs_only([])


@pytest.mark.parametrize(
    ("event_name", "event", "scope", "mode"),
    [
        ("schedule", {}, "role", "full"),
        ("workflow_dispatch", {}, "full", "full"),
        ("workflow_dispatch", {}, "role", "normal"),
        ("push", {"ref": "refs/tags/v0.4.0", "before": "0" * 40}, "role", "full"),
    ],
)
def test_schedule_dispatch_and_tags(
    event_name: str, event: Mapping[str, object], scope: str, mode: str
) -> None:
    decision = decide(event_name, event, repo=REPO, workflow="ci.yml", scope=scope)
    assert decision.mode == mode


def test_handoff_only_push_reuses_the_passing_run() -> None:
    whole = ["apps/server/x.py", "handoff/tasks/x.html"]
    runner = fake(pushed=["handoff/tasks/x.html"], whole=whole)
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "docs"
    assert "actions/runs/1" in decision.reason


@pytest.mark.parametrize("previous", ["failure", "cancelled", None])
def test_handoff_only_push_runs_again_without_a_passing_run(previous: str | None) -> None:
    runner = fake(pushed=["handoff/tasks/x.html"], previous=previous)
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "normal"


def test_code_push_runs_normally() -> None:
    runner = fake(pushed=["apps/server/x.py"], whole=["apps/server/x.py", "uv.lock"])
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision == Decision("normal", "照常執行")


def test_new_pull_request_has_no_before() -> None:
    runner = fake(pushed=["handoff/tasks/x.html"])
    event = pull_request(action="opened")
    decision = decide("pull_request", event, repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "normal"


def test_push_to_main_compares_with_the_previous_commit() -> None:
    event = {"ref": "refs/heads/main", "before": BEFORE, "after": HEAD}
    runner = fake(pushed=["apps/server/x.py"])
    decision = decide("push", event, repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "normal"


def test_nightly_matrix_filters_systems_and_repeats() -> None:
    everything = nightly_matrix("", 2)
    assert [(row["os"], row["python"], row["extra"]) for row in everything] == [
        ("ubuntu-latest", "3.13", 2),
        ("macos-latest", "3.13", 2),
        ("windows-latest", "3.13", 2),
        ("ubuntu-latest", "3.12", 0),
    ]
    assert nightly_matrix("windows", 0) == [{"os": "windows-latest", "python": "3.13", "extra": 0}]


# ---------------------------------------------------- 依層建置：輸入指紋、外殼鍵、通過紀錄

ROOT = Path(__file__).resolve().parents[2]

LOCK = """version = 1

[[package]]
name = "playwright"
version = "1.64.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "rpa-core"
version = "0.6.3"
source = { editable = "packages/rpa_core" }
dependencies = [
    { name = "pydantic" },
]
"""


def files(*changed: str) -> dict[str, str]:
    """假的檔案清單（路徑 → 內容的代號）；``changed`` 的檔案內容換掉（新檔案就加上）。"""
    base = {
        "uv.lock": "lock",
        "pyproject.toml": "root",
        "apps/desktop/pyproject.toml": "desktop",
        ".python-version": "313",
        "packages/rpa_update/src/rpa_update/boot.py": "boot",
        "apps/desktop/packaging/rpa_desktop.spec": "spec",
        "tools/build_desktop.py": "build",
        "tools/ci_changes.py": "plan",
        ".github/workflows/desktop.yml": "workflow",
        "apps/desktop/src/rpa_desktop/macos.py": "macos",
        "apps/desktop/src/rpa_desktop/recorder_gui.py": "recorder",
        "apps/desktop/src/rpa_desktop/tray.py": "tray",
        "apps/server/src/rpa_server/pages.py": "pages",
        "apps/server/src/rpa_server/client_api.py": "client",
        "apps/server/tests/test_api.py": "test",
        "packages/rpa_runner/src/rpa_runner/run.py": "run",
        "handoff/tasks/x.html": "handoff",
    }
    base.update(dict.fromkeys(changed, "v2"))
    return base


def job(job_id: str) -> ci_changes.Job:
    return next(
        item
        for groups in ci_changes.GROUPS.values()
        for jobs in groups.values()
        for item in jobs
        if item.id == job_id
    )


RECORDER = job("desktop-recorder-macos")
WORKER_MAC = job("desktop-worker-macos")
WORKER_WIN = job("desktop-worker-windows")
SERVER = job("server-package-x64")


def changed_jobs(after: Mapping[str, str]) -> set[str]:
    """和 :func:`files` 比，哪些桌面工作的指紋變了。"""
    before = files()
    jobs = (RECORDER, WORKER_MAC, WORKER_WIN, SERVER)
    return {
        item.id
        for item in jobs
        if ci_changes.fingerprint(item, before) != ci_changes.fingerprint(item, after)
    }


def test_version_numbers_are_not_part_of_the_fingerprint() -> None:
    bumped = LOCK.replace('version = "0.6.3"', 'version = "0.6.4"')
    assert ci_changes.normalize("uv.lock", LOCK) == ci_changes.normalize("uv.lock", bumped)
    # 第三方套件的版本照算
    upgraded = LOCK.replace('version = "1.64.0"', 'version = "1.65.0"')
    assert ci_changes.normalize("uv.lock", LOCK) != ci_changes.normalize("uv.lock", upgraded)
    project = '[project]\nname = "rpa-core"\nversion = "0.6.3"\ndependencies = ["pydantic"]\n'
    assert ci_changes.normalize("packages/rpa_core/pyproject.toml", project) == (
        ci_changes.normalize("packages/rpa_core/pyproject.toml", project.replace("0.6.3", "0.7.0"))
    )
    assert ci_changes.normalize("apps/desktop/src/rpa_desktop/ui.py", "x") is None


def test_tree_reads_blobs_and_normalizes_versioned_files() -> None:
    listing = (
        "100644 blob aaa\tuv.lock\0"
        "100644 blob bbb\tapps/x.py\0"
        "160000 commit ccc\tvendor/sub\0"
        "100644 blob ddd\tpackages/rpa_core/pyproject.toml\0"
    )
    blobs = {"aaa": LOCK, "ddd": '[project]\nversion = "1.0.0"\n'}

    def runner(command: Sequence[str]) -> str | None:
        match list(command):
            case ["git", "ls-tree", *_]:
                return listing
            case ["git", "cat-file", "blob", blob]:
                return blobs[blob]
            case _:
                return None

    tree = ci_changes.tree(runner)
    assert set(tree) == {"uv.lock", "apps/x.py", "packages/rpa_core/pyproject.toml"}
    assert tree["apps/x.py"] == "bbb"
    assert len(tree["uv.lock"]) == 64  # 去掉版本號後的 SHA-256


def test_server_only_change_leaves_every_device_alone() -> None:
    assert changed_jobs(files("apps/server/src/rpa_server/pages.py")) == {"server-package-x64"}
    # 伺服器的測試不進分發包
    assert changed_jobs(files("apps/server/tests/test_api.py")) == set()
    assert changed_jobs(files("handoff/tasks/x.html")) == set()


def test_device_api_and_recorder_changes() -> None:
    client = files("apps/server/src/rpa_server/client_api.py")
    assert changed_jobs(client) == {
        "desktop-recorder-macos",
        "desktop-worker-windows",
        "server-package-x64",
    }
    recorder = files("apps/desktop/src/rpa_desktop/recorder_gui.py")
    assert changed_jobs(recorder) == {"desktop-recorder-macos", "desktop-worker-windows"}
    # 通知區圖示只有 Windows 用
    assert changed_jobs(files("apps/desktop/src/rpa_desktop/tray.py")) == {"desktop-worker-windows"}
    # 一般的執行引擎：Windows Worker（生產角色）與伺服器；macOS 交給每晚的程式碼層檢查
    assert changed_jobs(files("packages/rpa_runner/src/rpa_runner/run.py")) == {
        "desktop-worker-windows",
        "server-package-x64",
    }
    every = {"desktop-recorder-macos", "desktop-worker-windows", "desktop-worker-macos"}
    assert changed_jobs(files("apps/desktop/src/rpa_desktop/macos.py")) == every


def test_shell_key_follows_only_the_runtime_inputs() -> None:
    before = files()
    key = ci_changes.shell_key("recorder-macos-arm64", before)
    code = files("apps/desktop/src/rpa_desktop/recorder_gui.py")
    assert ci_changes.shell_key("recorder-macos-arm64", code) == key
    assert ci_changes.fingerprint(RECORDER, code) != ci_changes.fingerprint(RECORDER, before)
    for name in ("uv.lock", "packages/rpa_update/src/rpa_update/boot.py", ".python-version"):
        assert ci_changes.shell_key("recorder-macos-arm64", {**before, name: "v2"}) != key
    assert ci_changes.shell_key("worker-macos-arm64", before) != key


def artifacts(*items: Json) -> Runner:
    def runner(command: Sequence[str]) -> str | None:
        if list(command[:2]) == ["gh", "api"] and "actions/artifacts?name=" in command[2]:
            name = command[2].split("name=", 1)[1].split("&", 1)[0]
            return json.dumps({"artifacts": [item for item in items if item["name"] == name]})
        return None

    return runner


def artifact(name: str, *, run: int = 7, repo_id: int = 1, expired: bool = False) -> Json:
    return {
        "name": name,
        "expired": expired,
        "workflow_run": {"id": run, "repository_id": 1, "head_repository_id": repo_id},
    }


def test_pass_records_from_this_repository_only() -> None:
    name = "pass-desktop-recorder-macos-0123456789abcdef"
    url = ci_changes.passed(REPO, name, repository_id=1, runner=artifacts(artifact(name)))
    assert url is not None
    assert url.endswith("/owner/repo/actions/runs/7")
    fork = artifacts(artifact(name, repo_id=2))
    assert ci_changes.passed(REPO, name, repository_id=1, runner=fork) is None
    expired = artifacts(artifact(name, expired=True))
    assert ci_changes.passed(REPO, name, repository_id=1, runner=expired) is None
    assert ci_changes.passed(REPO, name, runner=lambda _: None) is None


def test_plan_skips_passed_inputs_and_keeps_the_rest() -> None:
    tree = files()
    record = ci_changes.record_name(RECORDER, ci_changes.fingerprint(RECORDER, tree))
    runner = artifacts(artifact(record))
    planned = ci_changes.plan(
        "desktop.yml", tree, reuse=True, build="auto", repo=REPO, repository_id=1, runner=runner
    )["matrix"]
    assert [(item.job.id, item.runs) for item in planned] == [
        ("desktop-recorder-macos", False),
        ("desktop-worker-windows", True),
        ("desktop-worker-macos", True),
    ]
    entry = planned[1].entry()
    assert entry["os"] == "windows-latest"
    assert entry["build"] == "auto"
    assert entry["record"] == f"pass-desktop-worker-windows-{entry['fingerprint']}"
    assert entry["shell_key"] == ci_changes.shell_key("worker-windows-x64", tree)
    # 不沿用（排程、手動觸發）：全部執行；只看指定的目標
    again = ci_changes.plan(
        "desktop.yml",
        tree,
        reuse=False,
        build="full",
        targets=["recorder-macos-arm64"],
        repo=REPO,
        runner=runner,
    )["matrix"]
    assert [(item.job.id, item.runs, item.build) for item in again] == [
        ("desktop-recorder-macos", True, "full")
    ]
    server = ci_changes.plan("server-package.yml", tree, reuse=False, build="auto")["matrix"]
    assert {item.build for item in server} == {""}


@pytest.mark.parametrize(
    ("event_name", "mode", "reuse"),
    [
        ("pull_request", "normal", True),
        ("pull_request", "docs", True),
        ("push", "normal", True),
        ("push", "full", False),  # 推版本標籤
        ("schedule", "full", False),
        ("workflow_dispatch", "normal", False),
    ],
)
def test_only_pushes_and_pull_requests_reuse(event_name: str, mode: str, reuse: bool) -> None:
    assert ci_changes.reuse_allowed(event_name, mode) is reuse


def test_build_mode() -> None:
    tag = {"ref": "refs/tags/v0.7.0"}
    assert ci_changes.build_mode("push", tag, "full", "auto") == "full"  # 發布一律完整建置
    assert ci_changes.build_mode("schedule", {}, "full", "") == "full"  # 每週的完整建置
    assert ci_changes.build_mode("schedule", {}, "full", "auto") == "auto"  # 每晚的程式碼層檢查
    assert ci_changes.build_mode("pull_request", {}, "normal", "") == "auto"
    assert ci_changes.build_mode("workflow_dispatch", {}, "normal", "full") == "full"


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [path for path in out.split("\0") if path]


def test_every_input_pattern_still_matches_a_file() -> None:
    """檔案改名或刪掉時，清單裡的路徑就悄悄失效：每個模式都要對得到至少一個檔案。"""
    paths = tracked()
    stale = sorted(
        {
            f"{item.id}: {pattern}"
            for groups in ci_changes.GROUPS.values()
            for jobs in groups.values()
            for item in jobs
            for pattern in item.inputs
            if not any(fnmatch(path, pattern.removeprefix("!")) for path in paths)
        }
    )
    assert not stale


def test_every_desktop_source_file_reaches_the_windows_worker() -> None:
    """Windows 的 Worker 是生產角色：桌面 App 會執行的程式碼都要在它的輸入裡。"""
    roots = (
        "apps/desktop/src/",
        "apps/worker/src/",
        "packages/rpa_core/src/",
        "packages/rpa_runner/src/",
        "packages/rpa_update/src/",
    )
    missing = [
        path
        for path in tracked()
        if path.startswith(roots) and not ci_changes.included(path, WORKER_WIN.inputs)
    ]
    assert not missing


def test_show_prints_every_job() -> None:
    out = subprocess.run(
        [sys.executable, "tools/ci_changes.py", "--workflow", "desktop.yml", "--show"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert [line.split("\t")[1] for line in out.splitlines()] == [
        "desktop-recorder-macos",
        "desktop-worker-windows",
        "desktop-worker-macos",
    ]
