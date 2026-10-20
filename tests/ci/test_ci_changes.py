"""tools/ci_changes.py：依這次推送與整個 PR 的改動決定執行範圍。"""

import json
from collections.abc import Callable, Mapping, Sequence

import pytest

from tools.ci_changes import Decision, decide, docs_only, nightly_matrix, touches_worker

REPO = "owner/repo"
BEFORE = "b" * 40
HEAD = "c" * 40

type Runner = Callable[[Sequence[str]], str | None]


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


def test_docs_only_and_worker_paths() -> None:
    assert docs_only(["handoff/tasks/x.html", "docs/en/index.html", "README.md"])
    assert not docs_only(["handoff/tasks/x.html", "apps/server/src/rpa_server/app.py"])
    assert not docs_only([])
    assert touches_worker(["packages/rpa_runner/src/rpa_runner/run.py"])
    assert touches_worker(["uv.lock"])
    assert not touches_worker(["apps/server/src/rpa_server/app.py", "docs/index.html"])


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
    assert (decision.mode, decision.worker) == (mode, True)


def test_handoff_only_push_reuses_the_passing_run() -> None:
    whole = ["apps/server/x.py", "handoff/tasks/x.html"]
    runner = fake(pushed=["handoff/tasks/x.html"], whole=whole)
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "docs"
    assert decision.worker is False  # 整個 PR 只改了網站
    assert "actions/runs/1" in decision.reason


@pytest.mark.parametrize("previous", ["failure", "cancelled", None])
def test_handoff_only_push_runs_again_without_a_passing_run(previous: str | None) -> None:
    runner = fake(pushed=["handoff/tasks/x.html"], previous=previous)
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "normal"


def test_code_push_runs_normally_and_worker_follows_the_whole_pr() -> None:
    runner = fake(pushed=["apps/server/x.py"], whole=["apps/server/x.py", "uv.lock"])
    decision = decide("pull_request", pull_request(), repo=REPO, workflow="ci.yml", runner=runner)
    assert decision == Decision("normal", True, "整個 PR 的改動有碰到 Worker 的路徑")


def test_new_pull_request_has_no_before() -> None:
    runner = fake(pushed=["handoff/tasks/x.html"])
    event = pull_request(action="opened")
    decision = decide("pull_request", event, repo=REPO, workflow="ci.yml", runner=runner)
    assert decision.mode == "normal"


def test_push_to_main_compares_with_the_previous_commit() -> None:
    event = {"ref": "refs/heads/main", "before": BEFORE, "after": HEAD}
    runner = fake(pushed=["apps/server/x.py"])
    decision = decide("push", event, repo=REPO, workflow="ci.yml", runner=runner)
    assert (decision.mode, decision.worker) == ("normal", False)


def test_nightly_matrix_filters_systems_and_repeats() -> None:
    everything = nightly_matrix("", 2)
    assert [(row["os"], row["python"], row["extra"]) for row in everything] == [
        ("ubuntu-latest", "3.13", 2),
        ("macos-latest", "3.13", 2),
        ("windows-latest", "3.13", 2),
        ("ubuntu-latest", "3.12", 0),
    ]
    assert nightly_matrix("windows", 0) == [{"os": "windows-latest", "python": "3.13", "extra": 0}]
