"""把全部可達的 Git 歷史匯出為離線互動圖；只用標準函式庫與 Git。

python3 tools/git_history.py --fetch --github --open
不修改工作檔案／分支；--fetch 更新遠端引用，--github 額外讀取 PR 資料。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import webbrowser
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urlsplit

ASSETS = Path(__file__).with_name("git_history_assets")
LOCALES = ("zh-Hant", "zh-Hans", "en")
GITHUB_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
COMMIT_FORMAT = "%H%x00%P%x00%an%x00%aI%x00%cI%x00%s%x00%b"


class HistoryError(Exception):
    """可向操作者說明的收集錯誤。"""


class Commit(TypedDict):
    oid: str
    parents: list[str]
    author: str
    authored: str
    committed: str
    subject: str
    body: str


class Ref(TypedDict):
    name: str
    oid: str
    kind: str


class PullRequest(TypedDict):
    number: int
    title: str
    state: str
    base: str
    head: str
    headOid: str
    mergeOid: str | None
    url: str


class Snapshot(TypedDict):
    name: str
    generated: str
    fetched: bool
    shallow: bool
    github: str | None
    commits: list[Commit]
    refs: list[Ref]
    prs: list[PullRequest]


def run(command: Sequence[str], *, cwd: Path, timeout: int = 120) -> str:
    """不經 shell 執行；不在錯誤中顯示 URL 內的認證資訊。"""
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HistoryError(f"{command[0]}: {type(error).__name__}") from None
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        detail = re.sub(r"(https?://)[^/\s]+@", r"\1[redacted]@", detail)
        raise HistoryError(f"{command[0]} ({result.returncode}): {detail[:2000]}")
    return result.stdout.decode("utf-8", "replace")


def git(repo: Path, *args: str) -> str:
    return run(["git", "--no-replace-objects", *args], cwd=repo)


def read_commits(repo: Path) -> list[Commit]:
    """NUL 分隔欄位；不把主旨或本文當成程式碼，也不以行數截斷歷史。"""
    # date-order 同樣保證子提交先於父提交，並讓獨立的指標分支與主線交錯呈現。
    raw = git(repo, "log", "--all", "--date-order", "-z", f"--format={COMMIT_FORMAT}")
    if not raw:
        return []
    fields = raw.removesuffix("\0").split("\0")
    if len(fields) % 7:
        raise HistoryError("Invalid Git log record")
    commits: list[Commit] = []
    for offset in range(0, len(fields), 7):
        oid, parents, author, authored, committed, subject, body = fields[offset : offset + 7]
        commits.append(
            Commit(
                oid=oid,
                parents=parents.split(),
                author=author,
                authored=authored,
                committed=committed,
                subject=subject,
                body=body,
            )
        )
    return commits


def read_refs(repo: Path) -> list[Ref]:
    result: list[Ref] = []
    raw = git(
        repo, "for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)%00%(symref)"
    )
    for line in raw.splitlines():
        name, oid, kind, symbolic = line.split("\0")
        if symbolic:
            continue
        if kind != "commit":
            try:
                oid = git(repo, "rev-parse", "--verify", f"{name}^{{commit}}").strip()
            except HistoryError:
                continue  # 指向 tree／blob 的標籤沒有提交節點
        if name.startswith("refs/heads/"):
            name, kind = name.removeprefix("refs/heads/"), "branch"
        elif name.startswith("refs/remotes/"):
            name, kind = name.removeprefix("refs/remotes/"), "remote"
        elif name.startswith("refs/tags/"):
            name, kind = name.removeprefix("refs/tags/"), "tag"
        elif name.startswith("refs/git-history/"):
            name, kind = f"PR #{name.rsplit('/', 1)[-1]}", "pr"
        else:
            kind = "other"
        result.append(Ref(name=name, oid=oid, kind=kind))
    with suppress(HistoryError):  # 空倉庫的 unborn HEAD
        result.append(
            Ref(name="HEAD", oid=git(repo, "rev-parse", "--verify", "HEAD").strip(), kind="head")
        )
    return result


def github_repository(remote_url: str) -> str:
    """只接受 github.com 倉庫；移除 URL 的帳密，不寫入輸出。"""
    if remote_url.startswith("git@github.com:"):
        slug = remote_url.removeprefix("git@github.com:")
    else:
        parsed = urlsplit(remote_url)
        if parsed.hostname != "github.com" or parsed.scheme not in ("https", "ssh"):
            raise HistoryError("--github requires a github.com remote")
        slug = parsed.path.lstrip("/")
    slug = slug.rstrip("/").removesuffix(".git")
    if not GITHUB_REPO.fullmatch(slug):
        raise HistoryError("Invalid GitHub repository")
    return slug


def read_prs(repo: Path, slug: str) -> list[PullRequest]:
    raw: object = json.loads(
        run(
            ["gh", "api", "--paginate", "--slurp", f"repos/{slug}/pulls?state=all&per_page=100"],
            cwd=repo,
        )
    )
    if not isinstance(raw, list):
        raise HistoryError("Invalid GitHub pull request response")
    result: list[PullRequest] = []
    for page in cast("list[object]", raw):
        if not isinstance(page, list):
            raise HistoryError("Invalid GitHub pull request page")
        for item in cast("list[object]", page):
            if not isinstance(item, dict):
                raise HistoryError("Invalid GitHub pull request")
            value = cast("dict[str, object]", item)
            head = cast("dict[str, object]", value["head"])
            base = cast("dict[str, object]", value["base"])
            number = int(str(value["number"]))
            merged = bool(value.get("merged_at"))
            result.append(
                PullRequest(
                    number=number,
                    title=str(value["title"]),
                    state="merged" if merged else str(value["state"]),
                    base=str(base["ref"]),
                    head=str(head["ref"]),
                    headOid=str(head["sha"]),
                    mergeOid=str(value["merge_commit_sha"]) if merged else None,
                    url=f"https://github.com/{slug}/pull/{number}",
                )
            )
    return result


def collect(repo: Path, *, fetch: bool, github: bool, remote: str = "origin") -> Snapshot:
    """更新僅限 fetch；PR head 放進工具專用 refs，不建立工作分支。"""
    if not repo.is_dir():
        raise HistoryError(f"Not a directory: {repo}")
    git(repo, "rev-parse", "--git-dir")
    slug = None
    if github:
        if remote not in git(repo, "remote").splitlines():
            raise HistoryError(f"Unknown remote: {remote}")
        slug = github_repository(git(repo, "remote", "get-url", remote).strip())
    if fetch:
        git(repo, "fetch", "--all", "--tags")
        if github:
            git(repo, "fetch", remote, f"+refs/pull/*/head:refs/git-history/{remote}/pr/*")
    prs = read_prs(repo, slug) if slug else []
    return Snapshot(
        name=repo.name,
        generated=datetime.now(UTC).isoformat(timespec="seconds"),
        fetched=fetch,
        shallow=git(repo, "rev-parse", "--is-shallow-repository").strip() == "true",
        github=slug,
        commits=read_commits(repo),
        refs=read_refs(repo),
        prs=prs,
    )


def json_for_html(value: object) -> str:
    """JSON 放進 script 時必須跳脫 HTML 結束標記；使用者字串以 textContent 顯示。"""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render(
    snapshot: Snapshot, *, locale: str = "zh-Hant", timezone: str = "America/Los_Angeles"
) -> str:
    messages = {
        lang: json.loads((ASSETS / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in LOCALES
    }
    values = {
        "LANG": html.escape(locale),
        "CSS": (ASSETS / "viewer.css").read_text(encoding="utf-8"),
        "JS": (ASSETS / "viewer.js").read_text(encoding="utf-8"),
        "DATA": json_for_html(
            {"snapshot": snapshot, "messages": messages, "locale": locale, "timezone": timezone}
        ),
    }
    template = (ASSETS / "viewer.html").read_text(encoding="utf-8")
    # 單次替換，避免提交訊息中的樣板標記被二次展開。
    return re.sub(r"@@(LANG|CSS|JS|DATA)@@", lambda match: values[match[1]], template)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a complete, offline Git history graph.")
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="Git worktree (default: current directory)"
    )
    parser.add_argument(
        "--output", type=Path, help="HTML destination (default: REPO/artifacts/git-history.html)"
    )
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch all remotes and tags before exporting"
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="Read all GitHub PRs with gh; with --fetch also retrieve PR heads",
    )
    parser.add_argument("--remote", default="origin", help="GitHub remote used by --github")
    parser.add_argument(
        "--open", action="store_true", help="Open the generated file in the default browser"
    )
    parser.add_argument("--lang", choices=LOCALES, default="zh-Hant")
    parser.add_argument(
        "--timezone", default="America/Los_Angeles", help="IANA timezone for displayed dates"
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo).expanduser().resolve()
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else repo / "artifacts" / "git-history.html"
    )
    try:
        snapshot = collect(repo, fetch=args.fetch, github=args.github, remote=args.remote)
        document = render(snapshot, locale=args.lang, timezone=args.timezone)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
    except (HistoryError, OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(output)
    if args.open:
        webbrowser.open(output.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
