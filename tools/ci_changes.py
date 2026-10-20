"""CI 的改動偵測：這次要跑哪些工作。每個 workflow 的第一個工作（changes）執行它。

輸出（寫進 ``$GITHUB_OUTPUT``，同時寫一則 notice 說明理由）：

- ``mode``：

  - ``full``：排程、手動觸發選了 full、推版本標籤（發布）。跑完整的範圍。
  - ``docs``：這次推送只改了文件（``handoff/``、``docs/``、根目錄的 ``*.md``），而且上一次推送
    （``before``）在同一個 workflow 的運行已經通過。程式與上一次相同，重的工作沿用那次的結果、
    改為略過；CI 仍跑靜態檢查與不需瀏覽器的測試（含文檔檢查）。
  - ``normal``：其他情況（PR、合併到 main、手動觸發選了 role）。

- ``worker``：``true`` 時要跑 Windows 的 Worker 測試，也就是整個 PR（或這次推送到 main）
  改到了 Worker 的路徑（``WORKER``）；``full`` 一律是 ``true``。

- ``matrix``（只有 ``--nightly`` 時）：每晚完整測試的矩陣，依手動觸發的選項篩選系統與重跑次數。

規則與背景見 docs/develop/ci.html；只改文件時沿用結果是使用者於 2026-10-19 同意的規則
（handoff/collaboration.html 第 5 節）。只用標準函式庫，查詢上一次運行用 ``gh api``。

用法（GitHub Actions 裡）::

    python3 tools/ci_changes.py --workflow ci.yml [--scope role|full]
    python3 tools/ci_changes.py --workflow nightly.yml --nightly --systems windows --extra 2
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Final, cast

DOCS: Final = ("handoff/*", "docs/*", "*.md")
"""只改這些檔案時，程式與上一次推送相同。docs/ 由不需瀏覽器的 tests/docs、tests/i18n 檢查。"""

WORKER: Final = (
    "packages/*",
    "apps/worker/*",
    "apps/cli/*",
    "apps/testsite/*",
    "apps/desktop/*",
    "scenarios/*",
    "conftest.py",
    "tools/ci_roles.py",
    "tools/ci_changes.py",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".github/workflows/ci.yml",
)
"""改到這些檔案時，PR 上要在 Windows 跑 Worker 的瀏覽器測試。"""

ZERO: Final = "0" * 40

NIGHTLY: Final[Sequence[Mapping[str, object]]] = (
    {"os": "ubuntu-latest", "python": "3.13", "repeat": True},
    {"os": "macos-latest", "python": "3.13", "repeat": True},
    {"os": "windows-latest", "python": "3.13", "repeat": True},
    {"os": "ubuntu-latest", "python": "3.12", "repeat": False},
)

type Json = Mapping[str, object]
type Runner = Callable[[Sequence[str]], str | None]


@dataclass(frozen=True, slots=True)
class Decision:
    mode: str
    worker: bool
    reason: str


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def docs_only(files: Sequence[str]) -> bool:
    return bool(files) and all(matches(path, DOCS) for path in files)


def touches_worker(files: Iterable[str]) -> bool:
    return any(matches(path, WORKER) for path in files)


def run(command: Sequence[str]) -> str | None:
    """執行命令，回傳標準輸出；失敗時回傳 None。"""
    done = subprocess.run(list(command), capture_output=True, text=True, check=False)
    return done.stdout if done.returncode == 0 else None


def changed(base: str, head: str, runner: Runner = run) -> list[str] | None:
    """兩個提交之間改了哪些檔案；提交不在本機時先 fetch，還是拿不到就回傳 None。"""
    for sha in (base, head):
        if runner(["git", "cat-file", "-e", f"{sha}^{{commit}}"]) is None:
            runner(["git", "fetch", "--no-tags", "--quiet", "origin", sha])
    out = runner(["git", "diff", "--name-only", base, head])
    return None if out is None else [line for line in out.splitlines() if line]


def merge_base(base: str, head: str, runner: Runner = run) -> str | None:
    out = runner(["git", "merge-base", base, head])
    return out.strip() if out else None


def previous_passed(
    repo: str, workflow: str, sha: str, event: str, runner: Runner = run
) -> str | None:
    """同一個 workflow 在 ``sha`` 上最近一次完成的運行若是通過，回傳它的網址。"""
    out = runner(
        ["gh", "api", f"repos/{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=20"]
    )
    if out is None:
        return None
    runs = cast("list[Json]", json.loads(out).get("workflow_runs", []))
    done = [item for item in runs if item.get("status") == "completed"]
    same = [item for item in done if item.get("event") == event] or done
    if not same:
        return None
    latest = max(same, key=lambda item: str(item.get("created_at", "")))
    return str(latest.get("html_url")) if latest.get("conclusion") == "success" else None


def decide(
    event_name: str,
    event: Json,
    *,
    repo: str,
    workflow: str,
    scope: str = "role",
    runner: Runner = run,
) -> Decision:
    if event_name == "schedule":
        return Decision("full", True, "排程：完整範圍")
    if event_name == "workflow_dispatch":
        if scope == "full":
            return Decision("full", True, "手動觸發：完整範圍")
        return Decision("normal", True, "手動觸發：依角色")
    ref = str(event.get("ref", ""))
    if event_name == "push" and ref.startswith("refs/tags/"):
        return Decision("full", True, "推版本標籤：完整範圍")

    if event_name == "pull_request":
        pull = cast("Json", event.get("pull_request", {}))
        head = str(cast("Json", pull.get("head", {})).get("sha", ""))
        base_sha = str(cast("Json", pull.get("base", {})).get("sha", ""))
        before = str(event.get("before") or "") if event.get("action") == "synchronize" else ""
        start = merge_base(base_sha, head, runner) if base_sha and head else None
        whole = changed(start, head, runner) if start else None
    elif event_name == "push":
        head = str(event.get("after", ""))
        before = str(event.get("before") or "")
        whole = changed(before, head, runner) if before and before != ZERO else None
    else:
        return Decision("normal", True, f"{event_name}：依角色")

    worker = True if whole is None else touches_worker(whole)
    if before and before != ZERO and head:
        pushed = changed(before, head, runner)
        if pushed is not None and docs_only(pushed):
            url = previous_passed(repo, workflow, before, event_name, runner)
            if url:
                return Decision(
                    "docs",
                    worker,
                    f"這次推送只改了文件（{len(pushed)} 個檔案），程式與 {before[:7]} 相同；"
                    f"沿用那次通過的結果：{url}",
                )
            reason = f"這次推送只改了文件，但 {before[:7]} 沒有通過的運行，照常執行"
            return Decision("normal", worker, reason)
    if whole is None:
        return Decision("normal", worker, "比對不到改動的檔案，照常執行")
    scope_text = "整個 PR 的改動" if event_name == "pull_request" else "這次推送的改動"
    text = "有" if worker else "沒有"
    return Decision("normal", worker, f"{scope_text}{text}碰到 Worker 的路徑")


def nightly_matrix(systems: str, extra: int) -> list[dict[str, object]]:
    """每晚完整測試的矩陣：``systems`` 是逗號分隔的 ubuntu／macos／windows（空的是全部）。"""
    wanted = {name.strip() for name in systems.split(",") if name.strip()}
    rows: list[dict[str, object]] = []
    for row in NIGHTLY:
        os_name = str(row["os"]).split("-")[0]
        if wanted and os_name not in wanted:
            continue
        repeat = extra if row["repeat"] else 0
        rows.append({"os": row["os"], "python": row["python"], "extra": repeat})
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI 的改動偵測：這次要跑哪些工作")
    parser.add_argument("--workflow", required=True, help="workflow 檔名，例如 ci.yml")
    parser.add_argument("--scope", default="role", choices=["role", "full"])
    parser.add_argument("--nightly", action="store_true", help="另外輸出每晚完整測試的矩陣")
    parser.add_argument("--systems", default="", help="每晚：要跑的系統，逗號分隔；空的是全部")
    parser.add_argument("--extra", default="", help="每晚：瀏覽器測試再跑幾遍（空的是 2）")
    args = parser.parse_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    path = os.environ.get("GITHUB_EVENT_PATH")
    event: Json = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    decision = decide(
        event_name,
        event,
        repo=os.environ.get("GITHUB_REPOSITORY", ""),
        workflow=args.workflow,
        scope=args.scope,
    )
    outputs = {"mode": decision.mode, "worker": "true" if decision.worker else "false"}
    if args.nightly:
        extra = int(args.extra) if args.extra.strip() else 2  # 排程沒有手動選項
        outputs["matrix"] = json.dumps(nightly_matrix(args.systems, extra))
    target = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in outputs.items()]
    if target:
        with Path(target).open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    title = f"執行範圍：{decision.mode}"
    print(f"::notice title={title}::{decision.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
