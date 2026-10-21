"""以真實 Git 倉庫驗證歷史完整性、只讀收集與離線輸出的資料邊界。"""

import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from tools import git_history as history


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo with spaces"
    path.mkdir()
    history.git(path, "init", "--initial-branch=main")
    history.git(path, "config", "user.name", "歷史測試者")
    history.git(path, "config", "user.email", "history@example.test")
    history.git(path, "config", "commit.gpgsign", "false")
    history.git(path, "config", "tag.gpgsign", "false")
    return path


def commit(repo: Path, message: str) -> str:
    history.git(repo, "commit", "--allow-empty", "-m", message)
    return history.git(repo, "rev-parse", "HEAD").strip()


def test_empty_repository(repo: Path) -> None:
    snapshot = history.collect(repo, fetch=False, github=False)
    assert snapshot["commits"] == []
    assert snapshot["refs"] == []
    assert not snapshot["shallow"]


def test_all_refs_merges_tags_orphans_and_detached_head(repo: Path) -> None:
    root = commit(repo, "根提交\n\n多行訊息\n第二行")
    history.git(repo, "checkout", "-b", "feature")
    side = commit(repo, "功能提交")
    history.git(repo, "tag", "-a", "v1", "-m", "版本")
    history.git(repo, "checkout", "main")
    main = commit(repo, "主線提交")
    history.git(repo, "merge", "--no-ff", "feature", "-m", "合併功能")
    merge = history.git(repo, "rev-parse", "HEAD").strip()
    history.git(repo, "checkout", "--orphan", "metrics")
    orphan = commit(repo, "獨立歷史")
    history.git(repo, "checkout", "--detach", merge)
    detached = commit(repo, "只有 HEAD 保留的提交")
    (repo / "unfinished.txt").write_text("使用者未完成的工作", encoding="utf-8")
    before = history.git(repo, "status", "--porcelain=v1", "--branch")

    snapshot = history.collect(repo, fetch=False, github=False)
    commits = {item["oid"]: item for item in snapshot["commits"]}
    assert set(commits) == {root, side, main, merge, orphan, detached}
    assert commits[merge]["parents"] == [main, side]
    assert commits[root]["body"] == "多行訊息\n第二行\n"
    assert commits[orphan]["parents"] == []
    assert any(ref["name"] == "v1" and ref["oid"] == side for ref in snapshot["refs"])
    positions = {item["oid"]: index for index, item in enumerate(snapshot["commits"])}
    assert all(
        positions[item["oid"]] < positions[p] for item in commits.values() for p in item["parents"]
    )
    assert history.git(repo, "status", "--porcelain=v1", "--branch") == before


def test_shallow_clone_is_explicit(repo: Path, tmp_path: Path) -> None:
    commit(repo, "older")
    head = commit(repo, "newer")
    target = tmp_path / "shallow"
    history.git(repo, "clone", "--depth=1", repo.as_uri(), str(target))
    snapshot = history.collect(target, fetch=False, github=False)
    assert snapshot["shallow"]
    assert [item["oid"] for item in snapshot["commits"]] == [head]


def test_render_escapes_script_and_preserves_messages(repo: Path) -> None:
    message = "</script><img src=x onerror=alert(1)> @@JS@@ & \u2028"
    commit(repo, message)
    snapshot = history.collect(repo, fetch=False, github=False)
    rendered = history.render(snapshot, locale="en")
    assert message not in rendered
    match = re.search(
        r'<script id="git-history-data" type="application/json">(.*?)</script>', rendered, re.S
    )
    assert match is not None
    payload = json.loads(match[1])
    assert payload["snapshot"]["commits"][0]["subject"] == message
    assert payload["snapshot"]["commits"] == snapshot["commits"]
    assert "connect-src 'none'" in rendered
    assert '<script src="https:' not in rendered


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "https://user:secret@github.com/owner/repo.git/",
    ],
)
def test_remote_credentials_are_not_exported(remote: str) -> None:
    assert history.github_repository(remote) == "owner/repo"


def test_pr_pagination_and_squash_association(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: Sequence[str], *, cwd: Path, timeout: int = 120) -> str:
        assert "--paginate" in command
        assert "--slurp" in command
        assert cwd == repo
        return json.dumps(
            [
                [
                    {
                        "number": 1,
                        "title": "已合併",
                        "state": "closed",
                        "merged_at": "2026-10-20",
                        "head": {"ref": "feature", "sha": "a"},
                        "base": {"ref": "main"},
                        "merge_commit_sha": "b",
                    }
                ],
                [
                    {
                        "number": 2,
                        "title": "進行中",
                        "state": "open",
                        "merged_at": None,
                        "head": {"ref": "next", "sha": "c"},
                        "base": {"ref": "main"},
                        "merge_commit_sha": "preview",
                    }
                ],
            ]
        )

    monkeypatch.setattr(history, "run", fake_run)
    prs = history.read_prs(repo, "owner/repo")
    assert [pr["number"] for pr in prs] == [1, 2]
    assert prs[0]["mergeOid"] == "b"
    assert prs[0]["headOid"] == "a"
    assert prs[0]["state"] == "merged"
    assert prs[1]["mergeOid"] is None  # 預覽合併不是已合入的提交


def test_fetch_updates_remote_without_checkout(repo: Path) -> None:
    root = commit(repo, "main")
    origin = repo.parent / "remote.git"
    history.git(repo, "clone", "--bare", str(repo), str(origin))
    history.git(repo, "remote", "add", "origin", str(origin))
    history.collect(repo, fetch=True, github=False)
    assert history.git(repo, "rev-parse", "origin/main").strip() == root
    assert history.git(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_github_fetch_keeps_deleted_branch_via_pr_ref(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = commit(repo, "main")
    history.git(repo, "checkout", "-b", "deleted-feature")
    pr_head = commit(repo, "PR 的原始提交")
    history.git(repo, "checkout", "main")
    origin = repo.parent / "github.git"
    history.git(repo, "clone", "--bare", str(repo), str(origin))
    history.git(origin, "update-ref", "refs/pull/1/head", pr_head)
    history.git(origin, "update-ref", "-d", "refs/heads/deleted-feature")
    history.git(repo, "branch", "-D", "deleted-feature")
    history.git(repo, "remote", "add", "origin", str(origin))
    assert [item["oid"] for item in history.read_commits(repo)] == [root]
    real_git = history.git

    def fake_url(path: Path, *args: str) -> str:
        if args == ("remote", "get-url", "origin"):
            return "https://github.com/owner/repo.git\n"
        return real_git(path, *args)

    def no_pr_metadata(path: Path, slug: str) -> list[history.PullRequest]:
        return []

    monkeypatch.setattr(history, "git", fake_url)
    monkeypatch.setattr(history, "read_prs", no_pr_metadata)
    snapshot = history.collect(repo, fetch=True, github=True)
    assert {item["oid"] for item in snapshot["commits"]} == {root, pr_head}
    assert any(ref == {"name": "PR #1", "oid": pr_head, "kind": "pr"} for ref in snapshot["refs"])
    assert real_git(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_cli_writes_standalone_html(repo: Path, tmp_path: Path) -> None:
    commit(repo, "CLI")
    output = tmp_path / "report" / "history.html"
    assert history.main(["--repo", str(repo), "--output", str(output), "--lang", "zh-Hans"]) == 0
    assert '<html lang="zh-Hans">' in output.read_text(encoding="utf-8")
    assert history.main(["--repo", str(tmp_path / "missing")]) == 1


def test_canvas_paths_reach_only_actual_parents(repo: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node 不在 PATH；純拓撲驗證需要 Node")
    # 分岔、合流、多父提交、獨立根，以及缺失的父提交。
    commits: list[dict[str, str | list[str]]] = [
        {"oid": "merge", "parents": ["left", "right", "third"]},
        {"oid": "left", "parents": ["root"]},
        {"oid": "island", "parents": []},
        {"oid": "right", "parents": ["root"]},
        {"oid": "third", "parents": ["root"]},
        {"oid": "root", "parents": ["missing"]},
    ]
    source = (
        f"const {{layout}} = require({json.dumps(str(history.ASSETS / 'viewer.js'))});"
        f"process.stdout.write(JSON.stringify(layout({json.dumps(commits)})));"
    )
    data = json.loads(history.run([node, "-e", source], cwd=repo))
    rows = cast("list[dict[str, object]]", data["rows"])
    for index, row in enumerate(rows):
        segments = cast("list[list[int]]", row["segments"])
        lanes = {target for start, target in segments if start == row["lane"]}
        reached: set[str] = set()
        for later in rows[index + 1 :]:
            if later["lane"] in lanes:
                reached.add(cast("dict[str, str]", later["commit"])["oid"])
                lanes.remove(cast("int", later["lane"]))
            lanes = {
                target
                for start, target in cast("list[list[int]]", later["segments"])
                if start in lanes
            }
        expected = set(cast("list[str]", commits[index]["parents"])) - {"missing"}
        assert reached == expected
