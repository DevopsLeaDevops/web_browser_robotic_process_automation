"""CI 的執行範圍：這次要跑哪些工作。每個 workflow 的第一個工作（執行範圍）執行它。

規則與背景見 docs/develop/ci.html。只用標準函式庫；查詢 GitHub 用 ``gh api``。

一、``mode`` 與 Linux 測試的範圍（2026-10-19 起）
------------------------------------------------

- ``mode``：

  - ``full``：排程、手動觸發選了 full、推版本標籤（發布）。跑完整的範圍，不沿用任何結果。
  - ``docs``：這次推送只改了文件（``handoff/``、``docs/``、根目錄的 ``*.md``），而且上一次推送
    （``before``）在同一個 workflow 的運行已經通過。CI 的 Linux 測試只跑不需瀏覽器的部分。
  - ``normal``：其他情況（PR、合併到 main、手動觸發選了 role）。

- ``matrix``（只有 ``--nightly`` 時）：每晚完整測試的矩陣，依手動觸發的選項篩選系統與重跑次數。

二、依層建置：同一組輸入只驗證一次（2026-10-27 起）
---------------------------------------------------

重的工作（桌面端建置、伺服器分發包、一鍵安裝腳本、CI 的 Windows Worker 測試）在 :data:`GROUPS`
列出會影響它結果的檔案。這些檔案的內容算成**輸入指紋**：

- 同一個指紋已經有**通過紀錄**（這個倉庫的運行上傳的產物 ``pass-<工作>-<指紋>``，還沒過期）
  就略過、沿用那次的結果；否則執行，通過後上傳通過紀錄。
- 版本號不算：``pyproject.toml`` 的 ``version`` 與 ``uv.lock`` 裡工作區套件的版本換成空字串。
  發布 PR 只改版本號，指紋不變。
- ``full`` 與手動觸發一律執行、不沿用；通過時一樣留下紀錄（完整範圍涵蓋一般範圍）。

桌面 App 另外算**外殼鍵**（:func:`shell_key`）：Python、第三方套件、PyInstaller 的設定、
rpa_update 這些外殼（執行環境，ADR 0018）的輸入。外殼鍵相同時，桌面端建置從快取取出上次建好的
App，裝上這次的程式碼層（更新檔）測試，不重新打包；外殼鍵不同、快取過期或 ``build=full`` 才
完整建置。

輸出（寫進 ``$GITHUB_OUTPUT``，每個工作一則 notice 說明理由，另寫一張表到運行摘要）：

- 桌面端建置、伺服器分發包：``matrix``，要執行的矩陣項（JSON，空的是 ``[]``）。
- 一鍵安裝腳本：``linux``（Rocky 8 的兩種模式）、``inrepo``（三個系統的專案內執行）。
- CI：``worker``（``true``／``false``）與 ``worker_record``（通過時上傳的產物名稱）。

用法（GitHub Actions 裡）::

    python3 tools/ci_changes.py --workflow ci.yml [--scope role|full]
    python3 tools/ci_changes.py --workflow desktop.yml [--targets recorder-macos-arm64] \\
        [--build auto]
    python3 tools/ci_changes.py --workflow nightly.yml --nightly --systems windows --extra 2

本機看某個提交的指紋：``python3 tools/ci_changes.py --workflow desktop.yml --show``。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Final, cast

DOCS: Final = ("handoff/*", "docs/*", "*.md")
"""只改這些檔案時，程式與上一次推送相同。docs/ 由不需瀏覽器的 tests/docs、tests/i18n 檢查。"""

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
    reason: str


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def docs_only(files: Sequence[str]) -> bool:
    return bool(files) and all(matches(path, DOCS) for path in files)


def run(command: Sequence[str]) -> str | None:
    """執行命令，回傳標準輸出；失敗時回傳 None。"""
    done = subprocess.run(
        list(command), capture_output=True, text=True, encoding="utf-8", check=False
    )
    return done.stdout if done.returncode == 0 else None


def changed(base: str, head: str, runner: Runner = run) -> list[str] | None:
    """兩個提交之間改了哪些檔案；提交不在本機時先 fetch，還是拿不到就回傳 None。"""
    for sha in (base, head):
        if runner(["git", "cat-file", "-e", f"{sha}^{{commit}}"]) is None:
            runner(["git", "fetch", "--no-tags", "--quiet", "origin", sha])
    out = runner(["git", "diff", "--name-only", base, head])
    return None if out is None else [line for line in out.splitlines() if line]


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
    """``mode``：完整、只改文件、或一般。"""
    if event_name == "schedule":
        return Decision("full", "排程：完整範圍")
    if event_name == "workflow_dispatch":
        if scope == "full":
            return Decision("full", "手動觸發：完整範圍")
        return Decision("normal", "手動觸發：依角色")
    ref = str(event.get("ref", ""))
    if event_name == "push" and ref.startswith("refs/tags/"):
        return Decision("full", "推版本標籤：完整範圍")
    if event_name == "pull_request":
        pull = cast("Json", event.get("pull_request", {}))
        head = str(cast("Json", pull.get("head", {})).get("sha", ""))
        before = str(event.get("before") or "") if event.get("action") == "synchronize" else ""
    elif event_name == "push":
        head = str(event.get("after", ""))
        before = str(event.get("before") or "")
    else:
        return Decision("normal", f"{event_name}：依角色")
    if before and before != ZERO and head:
        pushed = changed(before, head, runner)
        if pushed is not None and docs_only(pushed):
            url = previous_passed(repo, workflow, before, event_name, runner)
            if url:
                return Decision(
                    "docs",
                    f"這次推送只改了文件（{len(pushed)} 個檔案），程式與 {before[:7]} 相同；"
                    f"沿用那次通過的結果：{url}",
                )
            reason = f"這次推送只改了文件，但 {before[:7]} 沒有通過的運行，照常執行"
            return Decision("normal", reason)
    return Decision("normal", "照常執行")


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


# ---------------------------------------------------------------- 依層建置：工作與它們的輸入

EPOCH: Final = 1
"""指紋的格式版本：算法或輸入的寫法改了，加 1 讓舊的通過紀錄全部失效。"""
SHELL_EPOCH: Final = 1
"""外殼鍵的版本：desktop.yml 的建置步驟（不在外殼鍵的檔案裡）改了，加 1 讓快取的外殼全部重建。"""
RETENTION_DAYS: Final = 30
"""通過紀錄（產物）保留幾天；過期之後同一組輸入再驗證一次。"""

DEPS: Final = ("pyproject.toml", "*/pyproject.toml", "uv.lock", ".python-version")
"""依賴與 Python 版本（版本號不算，見 :func:`normalize`）。"""
PLAN: Final = ("tools/ci_changes.py",)
"""這個檔案本身：決定範圍的規則改了，全部重新驗證一次。"""

SHELL: Final = (
    *DEPS,
    "packages/rpa_update/src/*",
    "apps/desktop/packaging/*",
    "tools/build_desktop.py",
)
"""桌面 App 外殼（執行環境，ADR 0018）的輸入：Python、第三方套件、PyInstaller 的設定、
rpa_update（啟動器與驗證）。這些沒變，快取裡的 App 就和重新打包的一樣，只差程式碼層。"""

DESKTOP_TOOLS: Final = (
    *PLAN,
    ".github/workflows/desktop.yml",
    "tools/desktop_shell.py",
    # 程式碼層的更新檔（tools/build_update.py 用 build_server.py 的方法建）
    "tools/build_update.py",
    "tools/build_server.py",
    # 自我測試：打包版自己的測試網站與 BA-001（含 Python 腳本版）
    "apps/testsite/src/*",
    "scenarios/demo/*",
)
APP_CORE: Final = tuple(
    f"apps/desktop/src/rpa_desktop/{name}"
    for name in (
        "__init__.py",
        "__main__.py",
        "entry.py",
        "build_info.py",
        "selftest.py",
        "updates.py",
        "downloads.py",
        "credentials.py",
        "single_instance.py",
        "settings.py",
        "logs.py",
        "i18n.py",
        "locales/*",
        "ui.py",
        "ui/portal.css",
    )
)
"""兩個桌面 App 共用、而且有系統專屬分支的程式：入口、自我測試、更新、下載瀏覽器、
鑰匙圈／認證管理員。"""
MACOS_ONLY: Final = ("apps/desktop/src/rpa_desktop/macos.py",)
DEVICE_API: Final = tuple(
    f"apps/server/src/rpa_server/{name}"
    for name in ("client_api.py", "worker_api.py", "devices.py", "device_updates.py")
)
"""伺服器上和裝置對話的部分：配對、任務、更新端點（端到端從原始碼啟動管理 Portal）。"""

RECORDER: Final = (
    *SHELL,
    *DESKTOP_TOOLS,
    *APP_CORE,
    *MACOS_ONLY,
    "apps/desktop/src/rpa_desktop/recorder_*",
    "apps/desktop/src/rpa_desktop/ui/recorder.*",
    # 錄製端：本機閘道、互動子程序、配對；逐步調試與錄製
    "apps/worker/src/rpa_worker/gateway.py",
    "apps/worker/src/rpa_worker/recorder.py",
    "apps/worker/src/rpa_worker/interactive.py",
    "apps/worker/src/rpa_worker/pairing.py",
    "apps/worker/src/rpa_worker/environment.py",
    "packages/rpa_runner/src/rpa_runner/commands.py",
    "packages/rpa_runner/src/rpa_runner/debug.py",
    "packages/rpa_runner/src/rpa_runner/record.py",
    "apps/server/src/rpa_server/client_api.py",
    "apps/server/src/rpa_server/device_updates.py",
    # 端到端與建置時跑的單元測試
    "tools/recorder_e2e.py",
    "tools/desktop_e2e.py",
    "scenarios/examples/iframe-form.yaml",
    "scenarios/examples/popup-form.yaml",
    "apps/desktop/tests/test_recorder_app.py",
    "apps/desktop/tests/test_ui.py",
    "apps/desktop/tests/test_worker_app.py",
    "apps/worker/tests/test_gateway.py",
    "apps/worker/tests/test_recorder.py",
    "apps/worker/tests/test_interactive.py",
)
"""RPA 錄製端（macOS）：外殼，加上錄製、逐步調試、本機閘道與 macOS 專屬的程式（2026-10-27 使用者
同意「窄」的範圍）。其他程式碼層的改動由 Linux 的 role_recorder 測試、Windows 的程式碼層測試與
每晚的 macOS 程式碼層檢查涵蓋；發布一律完整建置。"""

WORKER_UNIT_TESTS: Final = (
    "apps/desktop/tests/*",
    "packages/rpa_runner/tests/test_commands.py",
    "packages/rpa_runner/tests/test_files.py",
    "apps/worker/tests/test_service.py",
)
"""建置 Worker 前在那個系統上跑的單元測試（desktop.yml）。"""

WORKER_MACOS: Final = (
    *SHELL,
    *PLAN,
    ".github/workflows/desktop.yml",
    "tools/desktop_shell.py",
    *MACOS_ONLY,
    "apps/desktop/src/rpa_desktop/autostart.py",
    "apps/desktop/src/rpa_desktop/credentials.py",
    "apps/desktop/src/rpa_desktop/single_instance.py",
    "apps/desktop/src/rpa_desktop/gui.py",
    "apps/desktop/src/rpa_desktop/ui/worker.*",
    *WORKER_UNIT_TESTS,
)
"""RPA Worker（macOS）不是生產角色：只在外殼或 Worker App 的 macOS 部分（選單列、LaunchAgent、
鑰匙圈、視窗）改了時才跑（2026-10-27 使用者同意）。"""

WORKER_WINDOWS: Final = (
    *SHELL,
    *DESKTOP_TOOLS,
    "packages/rpa_core/src/*",
    "packages/rpa_script/src/*",
    "packages/rpa_runner/src/*",
    "apps/worker/src/*",
    "apps/desktop/src/*",
    *DEVICE_API,
    "tools/desktop_e2e.py",
    "scenarios/examples/iframe-form.yaml",
    "scenarios/examples/popup-form.yaml",
    *WORKER_UNIT_TESTS,
)
"""RPA Worker（Windows）是生產角色：它會執行的程式碼一改就跑（程式碼層路徑）。"""

CI_WORKER: Final = (
    *DEPS,
    *PLAN,
    "packages/*",
    "apps/worker/*",
    "apps/cli/*",
    "apps/testsite/*",
    "apps/desktop/*",
    "scenarios/*",
    "conftest.py",
    "tools/ci_roles.py",
    ".github/workflows/ci.yml",
)
"""CI 在 Windows 跑 Worker 的瀏覽器測試（原本的 WORKER 路徑）。"""

SERVER_PACKAGE: Final = (
    *DEPS,
    *PLAN,
    "apps/server/*",
    "apps/cli/*",
    "apps/worker/*",
    "apps/testsite/*",
    "packages/*",
    "!apps/*/tests/*",
    "!packages/*/tests/*",
    "scenarios/demo/*",
    "tools/build_server.py",
    "tools/build_update.py",
    "tools/linux_server_smoke.py",
    ".github/workflows/server-package.yml",
)
"""伺服器分發包（原本 server-package.yml 的 paths）。"""

SETUP: Final = (
    *DEPS,
    *PLAN,
    "scripts/*",
    ".github/workflows/setup-scripts.yml",
    "tools/linux_server_smoke.py",
    "tools/install_browsers.py",
    "tests/ci/test_browser_download.py",
    "tests/ci/test_linux_setup.py",
    "apps/cli/src/rpa_cli/serve.py",
)
"""一鍵安裝腳本（原本 setup-scripts.yml 的 paths）。"""


@dataclass(frozen=True, slots=True)
class Job:
    """一個重的工作（或矩陣的一項）。"""

    id: str
    """通過紀錄的名稱用它（``pass-<id>-<指紋>``）。"""
    inputs: tuple[str, ...]
    """會影響結果的檔案（fnmatch，``*`` 也比對 ``/``；``!`` 開頭是排除）。"""
    fields: Mapping[str, str] = field(default_factory=dict[str, str])
    """放進矩陣的其他欄位（app、os、name、target、mode）。"""
    shell: bool = False
    """桌面 App：另外算外殼鍵。"""


GROUPS: Final[Mapping[str, Mapping[str, Sequence[Job]]]] = {
    "desktop.yml": {
        "matrix": (
            Job(
                "desktop-recorder-macos",
                RECORDER,
                {
                    "app": "recorder",
                    "os": "macos-15",
                    "name": "RPA 錄製端（macOS）",
                    "target": "recorder-macos-arm64",
                },
                shell=True,
            ),
            Job(
                "desktop-worker-windows",
                WORKER_WINDOWS,
                {
                    "app": "worker",
                    "os": "windows-latest",
                    "name": "RPA Worker（Windows）",
                    "target": "worker-windows-x64",
                },
                shell=True,
            ),
            Job(
                "desktop-worker-macos",
                WORKER_MACOS,
                {
                    "app": "worker",
                    "os": "macos-15",
                    "name": "RPA Worker（macOS）",
                    "target": "worker-macos-arm64",
                },
                shell=True,
            ),
        ),
    },
    "server-package.yml": {
        "matrix": (
            Job("server-package-x64", SERVER_PACKAGE, {"label": "x64", "os": "ubuntu-latest"}),
            Job(
                "server-package-arm64",
                SERVER_PACKAGE,
                {"label": "arm64", "os": "ubuntu-24.04-arm"},
            ),
        ),
    },
    "setup-scripts.yml": {
        "linux": (
            Job("setup-rocky-in-repo", SETUP, {"mode": "in-repo"}),
            Job("setup-rocky-from-scratch", SETUP, {"mode": "from-scratch"}),
        ),
        "inrepo": (
            Job("setup-in-repo-ubuntu", SETUP, {"os": "ubuntu-latest"}),
            Job("setup-in-repo-macos", SETUP, {"os": "macos-latest"}),
            Job("setup-in-repo-windows", SETUP, {"os": "windows-latest"}),
        ),
    },
    "ci.yml": {"worker": (Job("ci-worker-windows", CI_WORKER),)},
}
"""每個 workflow 的重工作，依輸出名稱分組。"""


def included(path: str, patterns: Iterable[str]) -> bool:
    """``path`` 是不是這組輸入的檔案：符合任一個模式，而且不符合任何 ``!`` 開頭的排除。"""
    positive = [pattern for pattern in patterns if not pattern.startswith("!")]
    negative = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
    return matches(path, positive) and not matches(path, negative)


_PROJECT_VERSION: Final = re.compile(r'(?m)^version = "[^"]*"$')
_WORKSPACE_LOCK_VERSION: Final = re.compile(
    r'(\[\[package\]\]\nname = "[^"]+"\nversion = )"[^"]*"(\nsource = \{ (?:editable|virtual) = )'
)
"""uv.lock 裡工作區套件的版本（和 tools/release_version.py 改的是同一個地方）。"""


def normalize(path: str, text: str) -> str | None:
    """不算版本號的內容；不需要處理的檔案回傳 None（直接用 git 的物件代號）。"""
    if path == "uv.lock":
        return _WORKSPACE_LOCK_VERSION.sub(r'\1""\2', text.replace("\r\n", "\n"))
    if path == "pyproject.toml" or path.endswith("/pyproject.toml"):
        return _PROJECT_VERSION.sub('version = ""', text.replace("\r\n", "\n"))
    return None


def tree(runner: Runner = run, rev: str = "HEAD") -> dict[str, str]:
    """``rev`` 的每個檔案 → 內容的代號（git 物件代號；有版本號的檔案改用去掉版本號的雜湊）。"""
    out = runner(["git", "ls-tree", "-r", "-z", "--full-tree", rev])
    if out is None:
        raise SystemExit(f"讀不到 {rev} 的檔案清單（git ls-tree）")
    files: dict[str, str] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        files[path] = parts[2]
    for path, blob in list(files.items()):
        if normalize(path, "") is None:
            continue
        text = runner(["git", "cat-file", "blob", blob])
        if text is None:
            raise SystemExit(f"讀不到 {path}（git cat-file）")
        files[path] = hashlib.sha256(str(normalize(path, text)).encode()).hexdigest()
    return files


def digest(salt: str, files: Mapping[str, str], patterns: Iterable[str]) -> str:
    """``patterns`` 選出的檔案（路徑與內容的代號）加上 ``salt`` 的 SHA-256 前 16 個字元。"""
    chosen = tuple(patterns)
    hasher = hashlib.sha256(salt.encode())
    for path in sorted(path for path in files if included(path, chosen)):
        hasher.update(f"\n{path}\0{files[path]}".encode())
    return hasher.hexdigest()[:16]


def fingerprint(job: Job, files: Mapping[str, str]) -> str:
    """這個工作的輸入指紋。"""
    return digest(f"fingerprint {EPOCH} {job.id}", files, job.inputs)


def shell_key(target: str, files: Mapping[str, str]) -> str:
    """桌面 App 外殼的快取鍵（:data:`SHELL` 的檔案加上目標）。"""
    return digest(f"shell {SHELL_EPOCH} {target}", files, SHELL)


def record_name(job: Job, print_: str) -> str:
    return f"pass-{job.id}-{print_}"


def passed(
    repo: str, name: str, *, repository_id: int | None = None, runner: Runner = run
) -> str | None:
    """名為 ``name`` 的通過紀錄（產物）還在的話，回傳留下它的運行網址。

    只認這個倉庫自己的運行（``head_repository_id`` 相同）：fork 的 PR 不能替別人宣告通過。
    """
    out = runner(["gh", "api", f"repos/{repo}/actions/artifacts?name={name}&per_page=10"])
    if out is None:
        return None
    try:
        artifacts = cast("list[Json]", json.loads(out).get("artifacts", []))
    except (ValueError, AttributeError):
        return None
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    for item in artifacts:
        if item.get("name") != name or item.get("expired"):
            continue
        origin = cast("Json", item.get("workflow_run") or {})
        head = origin.get("head_repository_id")
        if repository_id is not None and head is not None and head != repository_id:
            continue
        return f"{server}/{repo}/actions/runs/{origin.get('id')}"
    return None


@dataclass(frozen=True, slots=True)
class Planned:
    job: Job
    fingerprint: str
    shell_key: str
    build: str
    reused: str | None
    """沿用的運行網址；None 是要執行。"""

    @property
    def runs(self) -> bool:
        return self.reused is None

    def entry(self) -> dict[str, str]:
        """矩陣的一項。"""
        return {
            **self.job.fields,
            "job": self.job.id,
            "fingerprint": self.fingerprint,
            "record": record_name(self.job, self.fingerprint),
            "shell_key": self.shell_key,
            "build": self.build,
        }


def plan(
    workflow: str,
    files: Mapping[str, str],
    *,
    reuse: bool,
    build: str,
    targets: Sequence[str] = (),
    repo: str = "",
    repository_id: int | None = None,
    runner: Runner = run,
) -> dict[str, list[Planned]]:
    """每一組要執行與沿用的工作。``targets`` 非空時只看矩陣欄位 target 在裡面的工作。"""
    result: dict[str, list[Planned]] = {}
    for group, jobs in GROUPS.get(workflow, {}).items():
        planned: list[Planned] = []
        for job in jobs:
            target = job.fields.get("target", "")
            if targets and target not in targets:
                continue
            print_ = fingerprint(job, files)
            key = shell_key(target, files) if job.shell else ""
            name = record_name(job, print_)
            url = (
                passed(repo, name, repository_id=repository_id, runner=runner)
                if reuse and repo
                else None
            )
            planned.append(Planned(job, print_, key, build if job.shell else "", url))
        result[group] = planned
    return result


def reuse_allowed(event_name: str, mode: str) -> bool:
    """推送與 PR 才沿用；排程、手動觸發、推版本標籤一律執行。"""
    return mode != "full" and event_name in ("push", "pull_request")


def build_mode(event_name: str, event: Json, mode: str, requested: str) -> str:
    """桌面 App 要不要完整建置：``full``（重新打包）或 ``auto``（外殼在快取裡就只換程式碼層）。

    推版本標籤一律完整建置（發布的安裝包）；其他時候照 ``requested``（手動觸發、被呼叫時的
    選項），沒有給的話完整範圍（排程、手動觸發選 full）是 full，其他是 auto。
    """
    if event_name == "push" and str(event.get("ref", "")).startswith("refs/tags/"):
        return "full"
    if requested in ("auto", "full"):
        return requested
    return "full" if mode == "full" else "auto"


def summary(planned: Mapping[str, Sequence[Planned]]) -> str:
    """運行摘要裡的表格。"""
    lines = [
        "### 執行範圍（依層建置，docs/develop/ci.html）",
        "",
        "| 工作 | 輸入指紋 | 外殼鍵 | 結果 |",
        "|---|---|---|---|",
    ]
    for items in planned.values():
        for item in items:
            if item.reused:
                result = f"沿用：[同一組輸入已通過]({item.reused})"
            elif item.build == "full":
                result = "執行（完整建置）"
            elif item.build == "auto":
                result = "執行（外殼在快取裡就只換程式碼層）"
            else:
                result = "執行"
            lines.append(
                f"| {item.job.id} | `{item.fingerprint}` | `{item.shell_key or '-'}` | {result} |"
            )
    return "\n".join(lines) + "\n"


def notices(planned: Mapping[str, Sequence[Planned]]) -> list[str]:
    lines: list[str] = []
    for items in planned.values():
        for item in items:
            if item.reused:
                text = f"輸入指紋 {item.fingerprint} 已在 {item.reused} 通過：略過，沿用那次的結果"
                lines.append(f"::notice title=沿用（{item.job.id}）::{text}")
            else:
                text = f"輸入指紋 {item.fingerprint} 沒有通過紀錄（或這次不沿用）：執行"
                lines.append(f"::notice title=執行（{item.job.id}）::{text}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI 的執行範圍：這次要跑哪些工作")
    parser.add_argument("--workflow", required=True, help="workflow 檔名，例如 ci.yml")
    parser.add_argument("--scope", default="role", choices=["role", "full"])
    parser.add_argument("--nightly", action="store_true", help="另外輸出每晚完整測試的矩陣")
    parser.add_argument("--systems", default="", help="每晚：要跑的系統，逗號分隔；空的是全部")
    parser.add_argument("--extra", default="", help="每晚：瀏覽器測試再跑幾遍（空的是 2）")
    parser.add_argument("--targets", default="", help="桌面端建置：只看這些目標，逗號分隔")
    parser.add_argument("--build", default="", help="桌面端建置：auto 或 full；空的依事件決定")
    parser.add_argument("--show", action="store_true", help="只印出每個工作的指紋（本機用）")
    args = parser.parse_args(argv)

    if args.show:
        files = tree()
        for group, jobs in GROUPS.get(args.workflow, {}).items():
            for job in jobs:
                key = shell_key(job.fields.get("target", ""), files) if job.shell else "-"
                print(f"{group}\t{job.id}\t{fingerprint(job, files)}\t{key}")
        return 0

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    path = os.environ.get("GITHUB_EVENT_PATH")
    event: Json = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    decision = decide(event_name, event, repo=repo, workflow=args.workflow, scope=args.scope)
    outputs = {"mode": decision.mode}
    if args.nightly:
        extra = int(args.extra) if args.extra.strip() else 2  # 排程沒有手動選項
        outputs["matrix"] = json.dumps(nightly_matrix(args.systems, extra))
    lines = [f"::notice title=執行範圍：{decision.mode}::{decision.reason}"]

    if args.workflow in GROUPS:
        repository = cast("Json", event.get("repository") or {})
        identifier = repository.get("id")
        reuse = reuse_allowed(event_name, decision.mode)
        build = build_mode(event_name, event, decision.mode, args.build.strip())
        targets = [name.strip() for name in args.targets.split(",") if name.strip()]
        planned = plan(
            args.workflow,
            tree(),
            reuse=reuse,
            build=build,
            targets=targets,
            repo=repo,
            repository_id=identifier if isinstance(identifier, int) else None,
        )
        for group, items in planned.items():
            outputs[group] = json.dumps([item.entry() for item in items if item.runs])
        if "worker" in planned:
            worker = [item for item in planned["worker"] if item.runs]
            outputs["worker"] = "true" if worker else "false"
            outputs["worker_record"] = worker[0].entry()["record"] if worker else ""
        lines += notices(planned)
        report = os.environ.get("GITHUB_STEP_SUMMARY")
        if report:
            with Path(report).open("a", encoding="utf-8") as stream:
                stream.write(summary(planned))

    target = os.environ.get("GITHUB_OUTPUT")
    pairs = [f"{key}={value}" for key, value in outputs.items()]
    if target:
        with Path(target).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(pairs) + "\n")
    print("\n".join(pairs))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
