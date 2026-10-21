"""領域資料夾的 git 同步（M11 PR 3；任務紀錄第 10 節）。

只有管理 Portal 做拉取與推送；錄製端與 worker 不碰 git。設定了資料來源的領域在
``<資料目錄>/git/repos/<領域>.git`` 有一個裸倉庫，只用來取得遠端的提交與建立新提交，沒有工作目錄；
正在使用的仍是 ``domains/<領域>/``。

- **本機變更**：正在使用的資料夾和「上次同步的提交」裡那個目錄的差異，所以存檔不需要每次提交。
- **合併**：拉取與推送都以檔案為單位。一邊改了、另一邊沒改就取改過的；兩邊把同一個檔案改成不同的
  內容就是衝突，停下來讓使用者選（取消、推送到新分支、以遠端為準）。不自動合併同一個檔案、不強推。
  版本目錄不可變、驗證紀錄一次一個檔案，所以衝突只會發生在兩台伺服器同時替同一個場景建立同號的
  版本，或同時發布同一個場景。
- **只動設定的目錄**：新提交從遠端最新的提交開始，只換掉那個目錄，倉庫的其他目錄不動。
- **套用**：先在暫存資料夾校驗（:func:`rpa_core.pack.read_pack`），通過才逐檔新增、修改、刪除，
  再重新載入那個領域。
- **憑證**：HTTPS 權杖存在 ``git/credentials.json``（0600），只經由 GIT_ASKPASS 交給那一次 git
  子程序，不寫進網址、git 設定、資料庫或日誌；SSH 用 Portal 產生（或貼上）的部署金鑰
  ``git/keys/<領域>`` 與自己的 ``git/known_hosts``（第一次連線記下主機指紋）。不使用系統與使用者的
  git 設定，也不使用憑證快取。
"""

import contextlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.pack import (
    COMPOSITE_FILE,
    COMPOSITES_DIR,
    PACK_FILE,
    REVISIONS_DIR,
    ROLES_DIR,
    SCENE_FILE,
    SCENES_DIR,
    VERIFICATIONS_DIR,
    CompositeEntry,
    CompositeManifest,
    CompositeRevisionInfo,
    PackManifest,
    RevisionInfo,
    SceneManifest,
    is_sensitive,
    read_model,
    read_pack,
)
from rpa_server.domain import now
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.models import Domain
from rpa_server.storage import Storage

__all__ = [
    "AUTHS",
    "Auth",
    "Change",
    "GitSource",
    "GitSync",
    "Probe",
    "PushPreview",
    "SyncState",
    "SyncStatus",
]

logger = logging.getLogger("rpa_server.gitsync")

Auth = Literal["none", "https", "ssh"]
AUTHS: Final[tuple[Auth, ...]] = ("none", "https", "ssh")
SyncState = Literal[
    "local",
    "unchecked",
    "synced",
    "ahead",
    "behind",
    "diverged",
    "empty",
    "no_directory",
    "conflict",
    "error",
]
"""同步狀態（第 10.2 節）：本機領域、還沒檢查過、已同步、本機有變更、遠端有新提交、兩邊都有、
空倉庫、遠端還沒有這個目錄、衝突、錯誤。"""
ChangeKind = Literal["revision", "verification", "publication", "role", "pack", "other"]
ChangeAction = Literal["added", "modified", "deleted"]
ProbeState = Literal["ready", "empty", "no_branch", "no_directory"]

MIN_GIT: Final = (2, 25)
TIMEOUT: Final = 120
"""每個 git 命令的逾時（秒）。"""
MAX_FILE_BYTES: Final = 1024 * 1024
ALLOWED_SUFFIXES: Final = frozenset({".yaml", ".yml", ".json", ".py", ".md", ".txt"})
"""能推送的檔案：定義檔與說明。"""
DEFAULT_BRANCH: Final = "main"
SYNCED_REF: Final = "refs/rpa/synced"
"""上次同步的提交也留一個參照，免得被 git 的垃圾回收清掉。"""
_ZERO: Final = "0" * 40
_FILE_MODE: Final = "100644"
_MIN_SECRET: Final = 4
"""比這短的 Secret 值不檢查（太容易誤判）。"""

_DIRECTORY: Final = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
_BRANCH: Final = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
_EMAIL: Final = re.compile(r"[^@\s]+@[^@\s]+")
_SCP_LIKE: Final = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:\S+")
_HTTPS_USERINFO: Final = re.compile(r"https?://[^/]*@", re.IGNORECASE)
_GITHUB: Final = re.compile(
    r"(?:git@github\.com:|(?:https|ssh)://(?:git@)?github\.com/)([^/\s]+/[^/\s]+?)(?:\.git)?/?$"
)

_ASKPASS_SH: Final = """#!/bin/sh
# RPA Portal：git 問帳號時給 RPA_GIT_USERNAME，問密碼時給 RPA_GIT_PASSWORD
# （只在那一次子程序的環境裡）
case "$1" in
  Username*|username*) printf '%s\\n' "$RPA_GIT_USERNAME" ;;
  *) printf '%s\\n' "$RPA_GIT_PASSWORD" ;;
esac
"""
_ASKPASS_PY: Final = """import os, sys
prompt = sys.argv[1] if len(sys.argv) > 1 else ""
key = "RPA_GIT_USERNAME" if prompt.lower().startswith("username") else "RPA_GIT_PASSWORD"
print(os.environ.get(key, ""))
"""


# ---------------------------------------------------------------- 資料


@dataclass(frozen=True, slots=True)
class GitSource:
    """一個領域的資料來源（存在資料庫，每台伺服器自己設定；不含帳號密碼）。"""

    url: str
    directory: str
    branch: str | None = None
    """沒填時用遠端的預設分支；空倉庫時是 main。"""
    auth: Auth = "none"
    username: str | None = None
    """HTTPS 的使用者名稱；SSH 與公開倉庫不用。"""
    committer_name: str | None = None
    committer_email: str | None = None
    auto_pull: bool = True
    """伺服器啟動時自動拉取；連不上時用本機上一次的資料照常啟動。"""

    def to_json(self) -> dict[str, object]:
        return {
            "url": self.url,
            "directory": self.directory,
            "branch": self.branch,
            "auth": self.auth,
            "username": self.username,
            "committerName": self.committer_name,
            "committerEmail": self.committer_email,
            "autoPull": self.auto_pull,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "GitSource":
        def text(key: str) -> str | None:
            value = data.get(key)
            return str(value) if isinstance(value, str) and value else None

        auth = data.get("auth")
        return cls(
            url=text("url") or "",
            directory=text("directory") or "",
            branch=text("branch"),
            auth=auth if auth in AUTHS else "none",
            username=text("username"),
            committer_name=text("committerName"),
            committer_email=text("committerEmail"),
            auto_pull=bool(data.get("autoPull", True)),
        )


@dataclass(frozen=True, slots=True)
class Change:
    """本機和上次同步之間的一個檔案變更。"""

    path: str
    """相對於領域資料夾。"""
    action: ChangeAction
    kind: ChangeKind
    item: str | None = None
    """場景、組合場景或角色的代號。"""
    number: int | None = None
    """版本號碼（版本與驗證紀錄）。"""

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "action": self.action,
            "kind": self.kind,
            "item": self.item,
            "number": self.number,
        }


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """一個領域的同步狀態（第 10.2 節）。"""

    domain_id: str
    available: bool
    """這台伺服器有沒有可用的 git。"""
    state: SyncState
    source: GitSource | None = None
    has_token: bool = False
    public_key: str | None = None
    host_keys: tuple[str, ...] = ()
    branch: str | None = None
    synced_commit: str | None = None
    remote_commit: str | None = None
    remote_commits: int = 0
    """上次同步之後，遠端在這個目錄的新提交數（上次檢查遠端時）。"""
    changes: tuple[Change, ...] = ()
    error: str | None = None
    conflicts: tuple[str, ...] = ()
    checked_at: str | None = None
    synced_at: str | None = None
    pushed_branch: str | None = None
    """衝突時推送到的新分支。"""

    def count(self, *kinds: ChangeKind) -> int:
        return sum(1 for change in self.changes if change.kind in kinds)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "revisions": self.count("revision"),
            "verifications": self.count("verification"),
            "publications": self.count("publication"),
            "others": self.count("role", "pack", "other"),
            "total": len(self.changes),
        }

    @property
    def compare_url(self) -> str | None:
        """推送到新分支後，到 GitHub 開 PR 的網址。"""
        if self.source is None or self.pushed_branch is None:
            return None
        found = _GITHUB.search(self.source.url)
        if found is None:
            return None
        return f"https://github.com/{found.group(1)}/compare/{self.pushed_branch}?expand=1"

    def to_json(self) -> dict[str, object]:
        return {
            "domainId": self.domain_id,
            "available": self.available,
            "state": self.state,
            "source": self.source.to_json() if self.source is not None else None,
            "hasToken": self.has_token,
            "publicKey": self.public_key,
            "hostKeys": list(self.host_keys),
            "branch": self.branch,
            "syncedCommit": self.synced_commit,
            "remoteCommit": self.remote_commit,
            "remoteCommits": self.remote_commits,
            "counts": self.counts,
            "changes": [change.to_json() for change in self.changes],
            "error": self.error,
            "conflicts": list(self.conflicts),
            "checkedAt": self.checked_at,
            "syncedAt": self.synced_at,
            "pushedBranch": self.pushed_branch,
            "compareUrl": self.compare_url,
        }


@dataclass(frozen=True, slots=True)
class Probe:
    """測試連線的結果。"""

    state: ProbeState
    branch: str
    commit: str | None = None
    pack_id: str | None = None
    pack_name: str | None = None
    pack_description: str | None = None
    host_keys: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "state": self.state,
            "branch": self.branch,
            "commit": self.commit,
            "packId": self.pack_id,
            "packName": self.pack_name,
            "packDescription": self.pack_description,
            "hostKeys": list(self.host_keys),
            "message": t(f"sync.probe_{self.state}", branch=self.branch),
        }


@dataclass(frozen=True, slots=True)
class PushPreview:
    """推送前的變更清單、預設的提交說明、擋下推送的問題與提醒（第 10.4 節）。"""

    changes: tuple[Change, ...]
    message: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "changes": [change.to_json() for change in self.changes],
            "message": self.message,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


class GitError(Exception):
    """git 命令失敗；message 已經遮掉權杖。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(slots=True)
class _Credentials:
    username: str | None = None
    token: str | None = None
    key: Path | None = None

    def mask(self, text: str) -> str:
        if self.token:
            text = text.replace(self.token, "***")
        return text


@dataclass(slots=True)
class _Remote:
    branch: str
    commit: str | None
    empty: bool


Files = dict[str, str]
"""相對路徑 → blob 雜湊。"""


@dataclass(slots=True)
class _Merge:
    files: Files
    conflicts: list[str] = field(default_factory=list[str])


# ---------------------------------------------------------------- 檢查輸入


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def normalize_source(source: GitSource) -> GitSource:
    """檢查並整理資料來源；不合格時丟 422。"""
    url = (source.url or "").strip()
    if not url or any(char.isspace() for char in url):
        raise invalid("sync_url_invalid", t("error.sync_url_invalid"))
    if _HTTPS_USERINFO.match(url):
        raise invalid("sync_url_credentials", t("error.sync_url_credentials"))
    lowered = url.lower()
    if source.auth == "https" and not lowered.startswith("https://"):
        raise invalid("sync_url_https", t("error.sync_url_https"))
    if source.auth == "ssh" and not (lowered.startswith("ssh://") or _SCP_LIKE.fullmatch(url)):
        raise invalid("sync_url_ssh", t("error.sync_url_ssh"))
    directory = (source.directory or "").strip().strip("/")
    if (
        not _DIRECTORY.fullmatch(directory)
        or any(part in (".", "..") for part in directory.split("/"))
        or directory.split("/")[0] == ".git"
    ):
        raise invalid("sync_directory_invalid", t("error.sync_directory_invalid"))
    branch = _clean(source.branch)
    if branch is not None and (
        not _BRANCH.fullmatch(branch)
        or ".." in branch
        or branch.startswith("-")
        or branch.endswith(".lock")
    ):
        raise invalid("sync_branch_invalid", t("error.sync_branch_invalid"))
    email = _clean(source.committer_email)
    if email is not None and not _EMAIL.fullmatch(email):
        raise invalid("sync_email_invalid", t("error.sync_email_invalid"))
    return GitSource(
        url=url,
        directory=directory,
        branch=branch,
        auth=source.auth if source.auth in AUTHS else "none",
        username=_clean(source.username) if source.auth == "https" else None,
        committer_name=(_clean(source.committer_name) or "")[:100] or None,
        committer_email=email,
        auto_pull=source.auto_pull,
    )


def classify(path: str, action: ChangeAction) -> Change:
    """依路徑判斷變更的種類：版本、驗證紀錄、發布（scene.yaml、composite.yaml）、角色。"""
    parts = path.split("/")
    if parts[0] in (SCENES_DIR, COMPOSITES_DIR) and len(parts) >= 3:
        item = parts[1]
        if parts[2] == REVISIONS_DIR and len(parts) >= 4:
            number = parts[3].removesuffix(".yaml")
            return Change(path, action, "revision", item, int(number) if number.isdigit() else None)
        if parts[2] == VERIFICATIONS_DIR and len(parts) >= 4:
            number = parts[3]
            return Change(
                path, action, "verification", item, int(number) if number.isdigit() else None
            )
        if len(parts) == 3:
            return Change(path, action, "publication", item)
        return Change(path, action, "other", item)
    if parts[0] == ROLES_DIR and len(parts) == 2:
        return Change(path, action, "role", parts[1].removesuffix(".yaml"))
    if path == PACK_FILE:
        return Change(path, action, "pack")
    return Change(path, action, "other")


def diff(base: Files, current: Files) -> tuple[Change, ...]:
    changes: list[Change] = []
    for path in sorted(set(base) | set(current)):
        before, after = base.get(path), current.get(path)
        if before == after:
            continue
        action: ChangeAction = (
            "added" if before is None else "deleted" if after is None else "modified"
        )
        changes.append(classify(path, action))
    return tuple(changes)


def merge(base: Files, local: Files, remote: Files) -> _Merge:
    """檔案層級的三方合併：只有一邊改就取那一邊；兩邊改成不同的內容就是衝突（不合併內容）。"""
    result = _Merge(files={})
    for path in sorted(set(base) | set(local) | set(remote)):
        before, mine, theirs = base.get(path), local.get(path), remote.get(path)
        if mine in (theirs, before):
            chosen = theirs
        elif theirs == before:
            chosen = mine
        else:
            result.conflicts.append(path)
            continue
        if chosen is not None:
            result.files[path] = chosen
    return result


def _is_revision_content(path: str) -> bool:
    """版本目錄裡的檔案（寫入後唯讀）：scenes/<場景>/revisions/<n>/…、composites/…。"""
    parts = path.split("/")
    return (
        len(parts) >= 5
        and parts[0] in (SCENES_DIR, COMPOSITES_DIR)
        and parts[2] == REVISIONS_DIR
        and parts[3].isdigit()
    )


def _writable(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


# ---------------------------------------------------------------- git 命令


class _Git:
    """在裸倉庫執行 git：不讀系統與使用者的設定、不用憑證快取、不在終端機問密碼。"""

    def __init__(self, root: Path, known_hosts: Path) -> None:
        self.root = root
        self.known_hosts = known_hosts
        self.executable = shutil.which("git")
        self._version: tuple[int, ...] | None = None

    def version(self) -> tuple[int, ...] | None:
        if self.executable is None:
            return None
        if self._version is None:
            try:
                output = subprocess.run(
                    [self.executable, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                ).stdout
            except (OSError, subprocess.SubprocessError):
                return None
            found = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", output)
            self._version = tuple(int(part) for part in found.groups("0")) if found else (0,)
        return self._version

    def available(self) -> bool:
        version = self.version()
        return version is not None and version >= MIN_GIT

    def _askpass(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            script = self.root / "askpass.py"
            launcher = self.root / "askpass.cmd"
            if not launcher.exists():
                script.write_text(_ASKPASS_PY, encoding="utf-8")
                launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
            return launcher
        script = self.root / "askpass.sh"
        if not script.exists() or script.read_text(encoding="utf-8") != _ASKPASS_SH:
            script.write_text(_ASKPASS_SH, encoding="utf-8")
        script.chmod(0o700)
        return script

    def environment(
        self, credentials: _Credentials, extra: Mapping[str, str] | None
    ) -> dict[str, str]:
        keep = (
            "PATH",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "NO_PROXY",
            "https_proxy",
            "http_proxy",
            "no_proxy",
            "SSL_CERT_FILE",
            "GIT_SSL_CAINFO",
        )
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env.update(
            {
                # 不讀使用者的 git 設定與 ~/.ssh（憑證快取、預設金鑰都不用）
                "HOME": str(self.root),
                "USERPROFILE": str(self.root),
                "XDG_CONFIG_HOME": str(self.root),
                "GIT_CEILING_DIRECTORIES": str(self.root.parent),
                "LC_ALL": "C",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_ASKPASS": str(self._askpass()),
                "SSH_ASKPASS_REQUIRE": "never",
                "RPA_GIT_USERNAME": credentials.username or "git",
                "RPA_GIT_PASSWORD": credentials.token or "",
            }
        )
        if credentials.key is not None:
            ssh = shutil.which("ssh") or "ssh"
            env["GIT_SSH_COMMAND"] = (
                f'"{ssh}" -F {os.devnull} -i "{credentials.key}" -o IdentitiesOnly=yes '
                f'-o UserKnownHostsFile="{self.known_hosts}" -o StrictHostKeyChecking=accept-new '
                "-o BatchMode=yes -o ConnectTimeout=20"
            )
        if extra:
            env.update(extra)
        return env

    def run(
        self,
        repo: Path | None,
        *args: str,
        credentials: _Credentials | None = None,
        data: bytes | None = None,
        env: Mapping[str, str] | None = None,
        timeout: int = TIMEOUT,
    ) -> bytes:
        if self.executable is None:
            raise GitError("missing", t("error.git_missing"))
        self.root.mkdir(parents=True, exist_ok=True)
        credentials = credentials or _Credentials()
        command = [
            self.executable,
            "-c",
            "credential.helper=",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.quotepath=off",
            "-c",
            "protocol.ext.allow=never",
        ]
        if repo is not None:
            command += ["--git-dir", str(repo)]
        command += list(args)
        try:
            completed = subprocess.run(
                command,
                input=data,
                capture_output=True,
                env=self.environment(credentials, env),
                cwd=self.root,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise GitError("timeout", t("error.sync_timeout", seconds=timeout)) from None
        except OSError as error:
            raise GitError("missing", credentials.mask(str(error))) from None
        if completed.returncode != 0:
            message = credentials.mask(completed.stderr.decode("utf-8", "replace").strip())
            raise GitError(_error_kind(message), message or f"git {args[0]} failed")
        return completed.stdout


def _error_kind(message: str) -> str:
    lowered = message.lower()
    if any(
        text in lowered
        for text in (
            "authentication failed",
            "could not read username",
            "could not read password",
            "permission denied",
            "invalid username or password",
            "terminal prompts disabled",
            "403",
        )
    ):
        return "auth"
    if any(
        text in lowered
        for text in (
            "repository not found",
            "not found",
            "does not appear to be a git repository",
            "no such file or directory",
        )
    ):
        return "not_found"
    if any(
        text in lowered
        for text in (
            "could not resolve host",
            "connection refused",
            "connection timed out",
            "network is unreachable",
            "operation timed out",
            "unable to access",
            "host key verification failed",
        )
    ):
        return "network"
    if any(text in lowered for text in ("[rejected]", "non-fast-forward", "fetch first")):
        return "rejected"
    return "other"


def _service_error(error: GitError) -> ServiceError:
    if error.kind == "missing":
        return ServiceError(409, "git_missing", t("error.git_missing"))
    if error.kind == "rejected":
        return conflict("sync_rejected", t("error.sync_rejected"), detail=error.message)
    code = {
        "auth": "sync_auth",
        "not_found": "sync_not_found",
        "network": "sync_network",
        "timeout": "sync_network",
    }.get(error.kind, "sync_failed")
    return ServiceError(502, code, t(f"error.{code}", detail=error.message), detail=error.message)


# ---------------------------------------------------------------- 同步


class GitSync:
    """領域資料夾與 git 倉庫之間的拉取與推送。"""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: Storage,
        *,
        lock: AbstractContextManager[object],
        reload: Callable[[str], object],
        secret_values: Callable[[], Mapping[str, str]],
        operator: Callable[[], str],
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.root = storage.root / "git"
        self.repos = self.root / "repos"
        self.keys = self.root / "keys"
        self.known_hosts = self.root / "known_hosts"
        self.credentials_file = self.root / "credentials.json"
        self.folder_lock = lock
        """寫入領域資料夾的鎖（PackStore.lock）：套用拉取結果時持有。"""
        self._reload = reload
        self._secret_values = secret_values
        self._operator = operator
        self.git = _Git(self.root, self.known_hosts)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._file_lock = threading.Lock()

    # ------------------------------------------------------------ 設定

    def available(self) -> bool:
        return self.git.available()

    def _domain(self, session: Session, domain_id: str) -> Domain:
        domain = session.get(Domain, domain_id)
        if domain is None:
            raise not_found("domain_not_found", t("error.domain_not_found", id=domain_id))
        return domain

    def source(self, domain_id: str) -> GitSource | None:
        with self.sessions() as session:
            domain = self._domain(session, domain_id)
            return GitSource.from_json(domain.source) if domain.source else None

    def _sync_info(self, domain_id: str) -> dict[str, object]:
        with self.sessions() as session:
            return dict(self._domain(session, domain_id).sync or {})

    def _save_sync(self, domain_id: str, **values: object) -> dict[str, object]:
        with self.sessions() as session:
            domain = self._domain(session, domain_id)
            info = dict(domain.sync or {})
            info.update(values)
            domain.sync = info
            session.commit()
            return info

    def _require_source(self, domain_id: str) -> GitSource:
        source = self.source(domain_id)
        if source is None:
            raise conflict("sync_not_configured", t("error.sync_not_configured", id=domain_id))
        if not self.available():
            raise ServiceError(409, "git_missing", t("error.git_missing"))
        return source

    def set_source(
        self,
        domain_id: str,
        source: GitSource,
        *,
        token: str | None = None,
        private_key: str | None = None,
    ) -> SyncStatus:
        """設定資料來源。倉庫、分支或目錄改了就從頭同步（下次拉取當成第一次接上遠端）。"""
        source = normalize_source(source)
        with self._operation(domain_id):
            with self.sessions() as session:
                domain = self._domain(session, domain_id)
                previous = GitSource.from_json(domain.source) if domain.source else None
                moved = previous is None or (
                    previous.url,
                    previous.branch,
                    previous.directory,
                ) != (source.url, source.branch, source.directory)
                domain.source = source.to_json()
                if moved:
                    domain.sync = {"state": "unchecked"}
                session.commit()
            if moved:
                self._remove_repo(domain_id)
            if token:
                self._store_token(domain_id, token.strip())
            if source.auth != "https":
                self._store_token(domain_id, None)
            if private_key:
                self._store_private_key(domain_id, private_key)
        return self.status(domain_id)

    def remove_source(self, domain_id: str) -> None:
        """中斷 git 連結：資料夾保留，變成本機領域；權杖、金鑰與工作副本一起刪除。"""
        with self._operation(domain_id):
            with self.sessions() as session:
                domain = self._domain(session, domain_id)
                domain.source = None
                domain.sync = None
                session.commit()
            self.forget(domain_id)

    def forget(self, domain_id: str) -> None:
        """刪除這個領域的權杖、金鑰與工作副本（刪除領域、中斷連結時）。"""
        self._store_token(domain_id, None)
        for path in (self.keys / domain_id, self.keys / f"{domain_id}.pub"):
            path.unlink(missing_ok=True)
        self._remove_repo(domain_id)

    def _remove_repo(self, domain_id: str) -> None:
        repo = self.repos / f"{domain_id}.git"
        if repo.exists():
            shutil.rmtree(repo, ignore_errors=True)

    # ------------------------------------------------------------ 憑證

    def _read_tokens(self) -> dict[str, str]:
        try:
            data: object = json.loads(self.credentials_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in cast("dict[object, object]", data).items()
            if isinstance(value, str)
        }

    def _store_token(self, domain_id: str, token: str | None) -> None:
        with self._file_lock:
            tokens = self._read_tokens()
            if token:
                tokens[domain_id] = token
            elif domain_id in tokens:
                del tokens[domain_id]
            else:
                return
            self.root.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                self.root.chmod(0o700)
            temporary = self.credentials_file.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(tokens, handle, ensure_ascii=False, indent=2)
            temporary.replace(self.credentials_file)

    def has_token(self, domain_id: str) -> bool:
        return domain_id in self._read_tokens()

    def _credentials(
        self, domain_id: str | None, source: GitSource, token: str | None = None
    ) -> _Credentials:
        if source.auth == "https":
            stored = self._read_tokens().get(domain_id or "") if token is None else token
            return _Credentials(username=source.username, token=stored)
        if source.auth == "ssh" and domain_id is not None:
            key = self.keys / domain_id
            if not key.is_file():
                raise conflict("sync_key_missing", t("error.sync_key_missing", id=domain_id))
            return _Credentials(key=key)
        return _Credentials()

    def public_key(self, domain_id: str) -> str | None:
        path = self.keys / f"{domain_id}.pub"
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def generate_key(self, domain_id: str) -> str:
        """產生這個領域的 SSH 部署金鑰（ed25519），回傳公鑰；舊的金鑰被換掉。"""
        with self.sessions() as session:
            self._domain(session, domain_id)
        keygen = shutil.which("ssh-keygen")
        if keygen is None:
            raise ServiceError(409, "ssh_missing", t("error.ssh_missing"))
        self.keys.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.root.chmod(0o700)
            self.keys.chmod(0o700)
        key = self.keys / domain_id
        for path in (key, key.with_name(f"{domain_id}.pub")):
            path.unlink(missing_ok=True)
        comment = f"rpa-portal-{self._operator()}-{domain_id}".replace(" ", "-")
        try:
            subprocess.run(
                [keygen, "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(key)],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ServiceError(
                500, "ssh_keygen_failed", t("error.ssh_keygen_failed", detail=str(error))
            ) from None
        if os.name != "nt":
            key.chmod(0o600)
        return self.public_key(domain_id) or ""

    def _store_private_key(self, domain_id: str, text: str) -> None:
        keygen = shutil.which("ssh-keygen")
        if keygen is None:
            raise ServiceError(409, "ssh_missing", t("error.ssh_missing"))
        self.keys.mkdir(parents=True, exist_ok=True)
        key = self.keys / domain_id
        key.unlink(missing_ok=True)
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.strip().replace("\r\n", "\n") + "\n")
        try:
            public = subprocess.run(
                [keygen, "-y", "-f", str(key)],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
                env={"SSH_ASKPASS_REQUIRE": "never", "PATH": os.environ.get("PATH", "")},
                stdin=subprocess.DEVNULL,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            key.unlink(missing_ok=True)
            raise invalid("ssh_key_invalid", t("error.ssh_key_invalid")) from None
        key.with_name(f"{domain_id}.pub").write_text(public.strip() + "\n", encoding="utf-8")

    def host_keys(self) -> tuple[str, ...]:
        """Portal 自己的 known_hosts 記下的主機指紋（第一次 SSH 連線時記下）。"""
        keygen = shutil.which("ssh-keygen")
        if keygen is None or not self.known_hosts.is_file():
            return ()
        try:
            output = subprocess.run(
                [keygen, "-l", "-f", str(self.known_hosts)],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return ()
        return tuple(line.strip() for line in output.splitlines() if line.strip())

    # ------------------------------------------------------------ 鎖

    def _operation(self, domain_id: str) -> "_Held":
        """每個領域同時只有一個 git 操作；已經有人在做時回 409。"""
        with self._locks_guard:
            lock = self._locks.setdefault(domain_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise conflict("sync_busy", t("error.sync_busy", id=domain_id))
        return _Held(lock)

    # ------------------------------------------------------------ 倉庫

    def _repo(self, domain_id: str | None, source: GitSource) -> Path:
        """裸倉庫（沒有就建立），remote origin 指向設定的網址。"""
        repo = (
            self.repos / f"{domain_id}.git"
            if domain_id
            else Path(tempfile.mkdtemp(prefix="probe-", dir=self._tmp()))
        )
        if not (repo / "HEAD").is_file():
            repo.mkdir(parents=True, exist_ok=True)
            self.git.run(None, "init", "-q", "--bare", str(repo))
        self.git.run(repo, "config", "remote.origin.url", source.url)
        return repo

    def _tmp(self) -> Path:
        folder = self.root / "tmp"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _fetch(
        self,
        repo: Path,
        source: GitSource,
        credentials: _Credentials,
        known: str | None = None,
    ) -> _Remote:
        """看遠端有哪些分支，取回要同步的分支（不取標籤）。

        分支：設定的；沒設定時沿用上次同步的（known），再來是遠端的預設分支、main。
        """
        output = self.git.run(repo, "ls-remote", "--symref", "origin", credentials=credentials)
        heads: dict[str, str] = {}
        default: str | None = None
        for line in output.decode("utf-8", "replace").splitlines():
            if line.startswith("ref: ") and line.endswith("\tHEAD"):
                default = line[5:].split("\t")[0].removeprefix("refs/heads/")
                continue
            sha, _, ref = line.partition("\t")
            if ref.startswith("refs/heads/"):
                heads[ref.removeprefix("refs/heads/")] = sha
        if not heads:
            return _Remote(source.branch or known or DEFAULT_BRANCH, None, True)
        if source.branch:
            branch = source.branch
        elif known and known in heads:
            branch = known
        elif default and default in heads:
            branch = default
        else:
            branch = DEFAULT_BRANCH if DEFAULT_BRANCH in heads else sorted(heads)[0]
        if branch not in heads:
            return _Remote(branch, None, False)
        self.git.run(
            repo,
            "fetch",
            "-q",
            "--no-tags",
            "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            credentials=credentials,
        )
        return _Remote(branch, heads[branch], False)

    def _has_commit(self, repo: Path, commit: str | None) -> bool:
        if not commit or not (repo / "HEAD").is_file():
            return False
        try:
            self.git.run(repo, "cat-file", "-e", f"{commit}^{{commit}}")
        except GitError:
            return False
        return True

    def _tree(self, repo: Path, commit: str | None, directory: str) -> Files:
        """提交裡那個目錄的檔案（相對於目錄）。"""
        if commit is None:
            return {}
        output = self.git.run(
            repo, "ls-tree", "-r", "-z", "--full-tree", commit, "--", f"{directory}/"
        )
        files: Files = {}
        prefix = f"{directory}/"
        for entry in output.split(b"\0"):
            if not entry:
                continue
            meta, _, name = entry.partition(b"\t")
            parts = meta.decode().split()
            if len(parts) != 3 or parts[1] != "blob":
                continue
            path = name.decode("utf-8", "replace")
            if path.startswith(prefix):
                files[path[len(prefix) :]] = parts[2]
        return files

    def _folder(self, folder: Path, repo: Path | None, *, write: bool) -> Files:
        """正在使用的資料夾的檔案與雜湊；write 時順便把內容寫進倉庫（之後要建立提交）。"""
        paths = (
            sorted(path for path in folder.rglob("*") if path.is_file() and not path.is_symlink())
            if folder.is_dir()
            else []
        )
        if not paths:
            return {}
        args = ["hash-object", "--no-filters", "--stdin-paths"]
        if write:
            args.insert(1, "-w")
        output = self.git.run(
            repo if write else None,
            *args,
            data="\n".join(str(path) for path in paths).encode("utf-8") + b"\n",
        )
        hashes = output.decode().split()
        return {
            path.relative_to(folder).as_posix(): sha
            for path, sha in zip(paths, hashes, strict=True)
        }

    def _blobs(self, repo: Path, shas: Iterable[str]) -> dict[str, bytes]:
        wanted = sorted(set(shas))
        if not wanted:
            return {}
        output = self.git.run(repo, "cat-file", "--batch", data=("\n".join(wanted) + "\n").encode())
        found: dict[str, bytes] = {}
        position = 0
        for sha in wanted:
            end = output.index(b"\n", position)
            header = output[position:end].decode().split()
            position = end + 1
            if len(header) < 3 or header[1] == "missing":
                raise GitError("other", f"missing object {sha}")
            size = int(header[2])
            found[sha] = output[position : position + size]
            position += size + 1
        return found

    def _write_files(self, repo: Path, files: Files, target: Path) -> None:
        contents = self._blobs(repo, files.values())
        for path, sha in files.items():
            destination = target / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents[sha])

    def _validate(self, repo: Path, files: Files, domain_id: str) -> None:
        """在暫存資料夾校驗要套用的內容（第 6 節）；pack.yaml 不對時不套用。"""
        with tempfile.TemporaryDirectory(dir=self._tmp()) as temporary:
            folder = Path(temporary) / domain_id
            folder.mkdir()
            self._write_files(repo, files, folder)
            pack = read_pack(folder, expected_id=domain_id)
        if pack.manifest is None:
            raise invalid(
                "sync_invalid",
                t("error.sync_invalid", id=domain_id),
                problems=[issue.to_json() for issue in pack.issues],
            )

    def _apply(self, repo: Path, folder: Path, files: Files) -> None:
        """逐檔新增、修改、刪除，讓正在使用的資料夾和 files 一樣（不整個換掉）。"""
        current = self._folder(folder, None, write=False)
        for path in sorted(set(current) - set(files), reverse=True):
            target = folder / path
            _writable(target.parent)
            _writable(target)
            target.unlink(missing_ok=True)
        changed = {path: sha for path, sha in files.items() if current.get(path) != sha}
        contents = self._blobs(repo, changed.values())
        for path, sha in changed.items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            _writable(target.parent)
            if target.exists():
                _writable(target)
            target.write_bytes(contents[sha])
            if _is_revision_content(path):
                target.chmod(0o444)
        # 清掉變空的資料夾（由深到淺）
        for directory in sorted(
            (path for path in folder.rglob("*") if path.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            with contextlib.suppress(OSError):
                directory.rmdir()

    def _commit(
        self,
        repo: Path,
        *,
        start: str | None,
        parents: list[str],
        directory: str,
        files: Files,
        message: str,
        source: GitSource,
    ) -> str:
        """從 start 的樹開始，只換掉 directory，建立一個提交（沒有工作目錄，用暫存的索引檔）。"""
        with tempfile.TemporaryDirectory(dir=self._tmp()) as temporary:
            env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
            if start is None:
                self.git.run(repo, "read-tree", "--empty", env=env)
            else:
                self.git.run(repo, "read-tree", start, env=env)
            lines = [
                f"0 {_ZERO}\t{directory}/{path}" for path in self._tree(repo, start, directory)
            ]
            lines += [
                f"{_FILE_MODE} {sha}\t{directory}/{path}" for path, sha in sorted(files.items())
            ]
            if lines:
                self.git.run(
                    repo,
                    "update-index",
                    "--index-info",
                    data=("\n".join(lines) + "\n").encode(),
                    env=env,
                )
            tree = self.git.run(repo, "write-tree", env=env).decode().strip()
        name = source.committer_name or self._operator()
        email = source.committer_email or "rpa-portal@localhost"
        identity = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
        args = ["commit-tree", tree]
        for parent in parents:
            args += ["-p", parent]
        return (
            self.git.run(repo, *args, data=message.encode("utf-8"), env=identity).decode().strip()
        )

    def _settle(
        self, repo: Path, base: Files, local: Files, theirs: Files, result: _Merge
    ) -> _Merge:
        """把「其實是同一件事」的衝突改成用遠端的那份，其餘照舊是衝突。

        兩台各自從同一批範例建立的領域（全新的資料夾會自動匯入範例），版本內容一樣，只有說明檔
        記的建立時間、伺服器不同；不能因此在第一次拉取就衝突。

        - 版本說明檔（``revisions/<n>.yaml``）：雜湊相同就是同一個版本。
        - ``scene.yaml``、``composite.yaml``：本機沒有發布，其他欄位和遠端相同（遠端多了發布）。
        - ``pack.yaml``：第一次接上遠端時代號相同（名稱與說明以遠端為準）。
        """
        if not result.conflicts:
            return result
        remaining: list[str] = []
        for path in result.conflicts:
            mine, other = local.get(path), theirs.get(path)
            if mine is not None and other is not None and self._same(repo, path, mine, other, base):
                result.files[path] = other
            else:
                remaining.append(path)
        result.conflicts = remaining
        return result

    def _same(self, repo: Path, path: str, mine: str, other: str, base: Files) -> bool:
        parts = path.split("/")
        revision_info = (
            parts[0] in (SCENES_DIR, COMPOSITES_DIR)
            and len(parts) == 4
            and parts[2] == REVISIONS_DIR
            and parts[3].endswith(".yaml")
            and parts[3].removesuffix(".yaml").isdigit()
        )
        if revision_info:
            model = CompositeRevisionInfo if parts[0] == COMPOSITES_DIR else RevisionInfo
            first, second = self._manifests(repo, model, mine, other)
            return first is not None and second is not None and first.hash == second.hash
        if parts[0] == SCENES_DIR and len(parts) == 3 and parts[2] == SCENE_FILE:
            scene, remote = self._manifests(repo, SceneManifest, mine, other)
            return (
                scene is not None
                and remote is not None
                and scene.published is None
                and scene == remote.model_copy(update={"published": None})
            )
        if parts[0] == COMPOSITES_DIR and len(parts) == 3 and parts[2] == COMPOSITE_FILE:
            composite, remote = self._manifests(repo, CompositeManifest, mine, other)
            return (
                composite is not None
                and remote is not None
                and composite.published is None
                and composite == remote.model_copy(update={"published": None})
            )
        if path == PACK_FILE and not base:
            pack, remote = self._manifests(repo, PackManifest, mine, other)
            return pack is not None and remote is not None and pack.id == remote.id
        return False

    def _manifests[M: BaseModel](
        self, repo: Path, model: type[M], *shas: str
    ) -> tuple[M | None, ...]:
        """讀出幾個 blob 的說明檔（格式不對的是 None）。"""
        contents = self._blobs(repo, shas)
        found: list[M | None] = []
        with tempfile.TemporaryDirectory(dir=self._tmp()) as temporary:
            for index, sha in enumerate(shas):
                path = Path(temporary) / f"{index}.yaml"
                path.write_bytes(contents[sha])
                found.append(read_model(path, model)[0])
        return tuple(found)

    def _push(self, repo: Path, commit: str, branch: str, credentials: _Credentials) -> None:
        self.git.run(
            repo, "push", "-q", "origin", f"{commit}:refs/heads/{branch}", credentials=credentials
        )

    def _mark_synced(self, repo: Path, commit: str) -> None:
        self.git.run(repo, "update-ref", SYNCED_REF, commit)

    def _count(self, repo: Path, base: str | None, head: str | None, directory: str) -> int:
        if head is None or base == head:
            return 0
        span = f"{base}..{head}" if base else head
        try:
            output = self.git.run(repo, "rev-list", "--count", span, "--", f"{directory}/")
        except GitError:
            return 0
        return int(output.decode().strip() or 0)

    # ------------------------------------------------------------ 狀態

    def status(self, domain_id: str) -> SyncStatus:
        """同步狀態（不連網路；遠端的部分是上次檢查時的）。"""
        with self.sessions() as session:
            domain = self._domain(session, domain_id)
            source = GitSource.from_json(domain.source) if domain.source else None
            info = dict(domain.sync or {})
        available = self.available()
        if source is None:
            return SyncStatus(domain_id, available, "local")
        repo = self.repos / f"{domain_id}.git"
        synced = _text(info.get("syncedCommit"))
        remote = _text(info.get("remoteCommit"))
        stored = _text(info.get("state")) or "unchecked"
        changes: tuple[Change, ...] = ()
        remote_commits = 0
        if available:
            try:
                base = (
                    self._tree(repo, synced, source.directory)
                    if self._has_commit(repo, synced)
                    else {}
                )
                changes = diff(
                    base, self._folder(self.storage.domain_dir(domain_id), None, write=False)
                )
                if self._has_commit(repo, remote):
                    remote_commits = self._count(repo, synced, remote, source.directory)
            except GitError as error:
                logger.warning("無法計算領域 %s 的同步狀態：%s", domain_id, error.message)
        state: SyncState
        if stored in ("conflict", "error", "empty", "no_directory", "unchecked"):
            state = cast("SyncState", stored)
        elif changes and remote_commits:
            state = "diverged"
        elif changes:
            state = "ahead"
        elif remote_commits:
            state = "behind"
        else:
            state = "synced"
        conflicts = info.get("conflicts")
        return SyncStatus(
            domain_id=domain_id,
            available=available,
            state=state,
            source=source,
            has_token=self.has_token(domain_id),
            public_key=self.public_key(domain_id),
            host_keys=self.host_keys() if source.auth == "ssh" else (),
            branch=_text(info.get("branch")) or source.branch,
            synced_commit=synced,
            remote_commit=remote,
            remote_commits=remote_commits,
            changes=changes,
            error=_text(info.get("error")),
            conflicts=tuple(str(item) for item in cast("list[object]", conflicts))
            if isinstance(conflicts, list)
            else (),
            checked_at=_text(info.get("checkedAt")),
            synced_at=_text(info.get("syncedAt")),
            pushed_branch=_text(info.get("pushedBranch")),
        )

    # ------------------------------------------------------------ 測試連線

    def probe(self, source: GitSource, token: str | None = None) -> Probe:
        """「從 git 新增領域」前測試連線（還沒有領域，只支援公開倉庫與 HTTPS 權杖）。"""
        source = normalize_source(source)
        if not self.available():
            raise ServiceError(409, "git_missing", t("error.git_missing"))
        if source.auth == "ssh":
            raise invalid("sync_probe_ssh", t("error.sync_probe_ssh"))
        credentials = self._credentials(None, source, token or "")
        repo = self._repo(None, source)
        try:
            return self._probe(repo, source, credentials)
        except GitError as error:
            raise _service_error(error) from None
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test(self, domain_id: str) -> Probe:
        """測試連線：可以連線、認證、遠端分支與目錄在不在；結果記進同步狀態。"""
        source = self._require_source(domain_id)
        with self._operation(domain_id):
            repo = self._repo(domain_id, source)
            credentials = self._credentials(domain_id, source)
            try:
                probe = self._probe(
                    repo, source, credentials, _text(self._sync_info(domain_id).get("branch"))
                )
            except GitError as error:
                self._failed(domain_id, error)
                raise _service_error(error) from None
            values: dict[str, object] = {
                "branch": probe.branch,
                "remoteCommit": probe.commit,
                "checkedAt": now().isoformat(timespec="seconds"),
                "error": None,
            }
            info = self._sync_info(domain_id)
            if probe.state in ("empty", "no_branch", "no_directory"):
                values["state"] = (
                    "empty" if probe.state in ("empty", "no_branch") else "no_directory"
                )
            elif _text(info.get("state")) != "conflict":
                values["state"] = "checked"
            self._save_sync(domain_id, **values)
        return probe

    def _probe(
        self,
        repo: Path,
        source: GitSource,
        credentials: _Credentials,
        known: str | None = None,
    ) -> Probe:
        remote = self._fetch(repo, source, credentials, known)
        hosts = self.host_keys() if source.auth == "ssh" else ()
        if remote.commit is None:
            return Probe("empty" if remote.empty else "no_branch", remote.branch, host_keys=hosts)
        files = self._tree(repo, remote.commit, source.directory)
        if not files:
            return Probe("no_directory", remote.branch, remote.commit, host_keys=hosts)
        manifest: PackManifest | None = None
        if PACK_FILE in files:
            with tempfile.TemporaryDirectory(dir=self._tmp()) as temporary:
                path = Path(temporary) / PACK_FILE
                path.write_bytes(self._blobs(repo, [files[PACK_FILE]])[files[PACK_FILE]])
                manifest, _ = read_model(path, PackManifest)
        return Probe(
            "ready",
            remote.branch,
            remote.commit,
            pack_id=manifest.id if manifest is not None else None,
            pack_name=manifest.name if manifest is not None else None,
            pack_description=manifest.description if manifest is not None else None,
            host_keys=hosts,
        )

    def _failed(self, domain_id: str, error: GitError) -> None:
        self._save_sync(
            domain_id,
            state="error",
            error=error.message[:1000],
            checkedAt=now().isoformat(timespec="seconds"),
        )

    # ------------------------------------------------------------ 拉取

    def pull(self, domain_id: str, *, prefer_remote: bool = False) -> SyncStatus:
        """拉取並重新載入（第 10.3 節）。

        prefer_remote：本機沒有要保留的資料（剛從 git 新增的領域），直接用遠端的內容。
        """
        source = self._require_source(domain_id)
        with self._operation(domain_id):
            try:
                self._pull(domain_id, source, prefer_remote=prefer_remote)
            except GitError as error:
                self._failed(domain_id, error)
                raise _service_error(error) from None
        return self.status(domain_id)

    def _pull(self, domain_id: str, source: GitSource, *, prefer_remote: bool) -> None:
        repo = self._repo(domain_id, source)
        credentials = self._credentials(domain_id, source)
        remote = self._fetch(
            repo, source, credentials, _text(self._sync_info(domain_id).get("branch"))
        )
        moment = now().isoformat(timespec="seconds")
        common: dict[str, object] = {
            "branch": remote.branch,
            "remoteCommit": remote.commit,
            "checkedAt": moment,
            "error": None,
            "conflicts": [],
        }
        theirs = self._tree(repo, remote.commit, source.directory)
        if remote.commit is None or not theirs:
            # 空倉庫或遠端還沒有這個目錄：第一次推送時建立，本機資料照用
            state = "empty" if remote.commit is None else "no_directory"
            self._save_sync(domain_id, state=state, **common)
            return
        folder = self.storage.domain_dir(domain_id)
        info = self._sync_info(domain_id)
        synced = _text(info.get("syncedCommit"))
        base = self._tree(repo, synced, source.directory) if self._has_commit(repo, synced) else {}
        local = self._folder(folder, repo, write=True)
        # 剛建立、只有 pack.yaml 的本機領域第一次接上遠端：沒有要保留的資料，直接用遠端的
        fresh = not base and set(local) <= {PACK_FILE}
        if prefer_remote or fresh:
            result = _Merge(files=dict(theirs))
        else:
            result = self._settle(repo, base, local, theirs, merge(base, local, theirs))
        if result.conflicts:
            self._save_sync(
                domain_id, state="conflict", **{**common, "conflicts": result.conflicts}
            )
            raise conflict(
                "sync_conflict",
                t("error.sync_conflict", id=domain_id, count=len(result.conflicts)),
                conflicts=result.conflicts,
            )
        if result.files != local:
            self._validate(repo, result.files, domain_id)
            with self.folder_lock:
                if self._folder(folder, None, write=False) != local:
                    raise conflict(
                        "sync_local_changed", t("error.sync_local_changed", id=domain_id)
                    )
                self._apply(repo, folder, result.files)
                self._reload(domain_id)
        self._mark_synced(repo, remote.commit)
        self._save_sync(
            domain_id, state="checked", syncedCommit=remote.commit, syncedAt=moment, **common
        )

    def pull_on_startup(self) -> None:
        """伺服器啟動時拉取設定了「啟動時自動拉取」的領域；失敗只記下錯誤，用本機的資料照常啟動。"""
        with self.sessions() as session:
            domains = [
                domain.id
                for domain in session.scalars(select(Domain).order_by(Domain.position))
                if domain.source and GitSource.from_json(domain.source).auto_pull
            ]
        if not domains or not self.available():
            return
        for domain_id in domains:
            try:
                self.pull(domain_id)
            except ServiceError as error:
                logger.warning(
                    "%s", t("sync.startup_pull_failed", id=domain_id, detail=error.message)
                )

    # ------------------------------------------------------------ 推送

    def preview(self, domain_id: str) -> PushPreview:
        """推送前：變更清單、預設的提交說明、擋下推送的問題與提醒（不連網路）。"""
        status = self.status(domain_id)
        if status.source is None:
            raise conflict("sync_not_configured", t("error.sync_not_configured", id=domain_id))
        folder = self.storage.domain_dir(domain_id)
        blockers: list[str] = []
        warnings: list[str] = []
        pack = read_pack(folder, expected_id=domain_id)
        if pack.manifest is None:
            blockers.append(t("sync.block_manifest"))
        elif pack.errors:
            warnings.append(t("sync.warn_problems", count=len(pack.errors)))
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            relative = path.relative_to(folder).as_posix()
            if is_sensitive(path.name):
                blockers.append(t("sync.block_sensitive", path=relative))
            elif path.suffix.lower() not in ALLOWED_SUFFIXES:
                blockers.append(t("sync.block_suffix", path=relative))
            elif path.stat().st_size > MAX_FILE_BYTES:
                blockers.append(t("sync.block_size", path=relative, limit=MAX_FILE_BYTES // 1024))
        values = {
            name: value
            for name, value in self._secret_values().items()
            if len(value) >= _MIN_SECRET
        }
        for change in status.changes:
            if change.action == "deleted" or not values:
                continue
            try:
                text = (folder / change.path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name, value in values.items():
                if value in text:
                    blockers.append(t("sync.block_secret", path=change.path, name=name))
        warnings += self._dependency_warnings(domain_id, pack.composites.values())
        return PushPreview(
            changes=status.changes,
            message=self.default_message(domain_id, status.changes),
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _dependency_warnings(
        self, domain_id: str, composites: Iterable[CompositeEntry]
    ) -> list[str]:
        """組合場景依賴的其他領域：那些場景版本是不是已經在它們的遠端（第 7 節最後一列）。"""
        warnings: list[str] = []
        for entry in composites:
            numbers = {entry.latest, *([entry.published] if entry.published else [])}
            for number in numbers:
                revision = entry.revisions.get(number)
                for requirement in (revision.requires or []) if revision is not None else []:
                    if requirement.domain == domain_id:
                        continue
                    try:
                        other = self.source(requirement.domain)
                    except ServiceError:
                        other = None
                    if other is None:
                        warnings.append(t("sync.warn_dependency_local", domain=requirement.domain))
                        continue
                    info = self._sync_info(requirement.domain)
                    synced = _text(info.get("syncedCommit"))
                    repo = self.repos / f"{requirement.domain}.git"
                    path = (
                        f"{other.directory}/{SCENES_DIR}/{requirement.scene}/{REVISIONS_DIR}/"
                        f"{requirement.revision}.yaml"
                    )
                    try:
                        present = synced is not None and bool(
                            self.git.run(repo, "cat-file", "-t", f"{synced}:{path}")
                        )
                    except GitError:
                        present = False
                    if not present:
                        warnings.append(
                            t(
                                "sync.warn_dependency_unpushed",
                                domain=requirement.domain,
                                scene=requirement.scene,
                                revision=requirement.revision,
                            )
                        )
        return warnings

    def default_message(self, domain_id: str, changes: Iterable[Change]) -> str:
        """預設的提交說明，例如「testsite：ba-001 第 3 版、ba-002 驗證紀錄 2 份」。"""
        revisions: dict[str, set[int]] = {}
        verifications: dict[str, int] = {}
        publications: list[str] = []
        roles: list[str] = []
        others = 0
        for change in changes:
            if change.kind == "revision" and change.item and change.number:
                revisions.setdefault(change.item, set()).add(change.number)
            elif change.kind == "verification" and change.item and change.action == "added":
                verifications[change.item] = verifications.get(change.item, 0) + 1
            elif change.kind == "publication" and change.item:
                publications.append(change.item)
            elif change.kind == "role" and change.item:
                roles.append(change.item)
            else:
                others += 1
        parts = [
            t(
                "sync.message_revision",
                item=item,
                numbers=", ".join(str(n) for n in sorted(numbers)),
            )
            for item, numbers in sorted(revisions.items())
        ]
        parts += [
            t("sync.message_verification", item=item, count=count)
            for item, count in sorted(verifications.items())
        ]
        parts += [t("sync.message_publication", item=item) for item in sorted(set(publications))]
        parts += [t("sync.message_role", item=item) for item in sorted(set(roles))]
        if others and not parts:
            parts.append(t("sync.message_other", count=others))
        if not parts:
            return t("sync.message_empty", domain=domain_id)
        shown = parts[:6]
        if len(parts) > len(shown):
            shown.append(t("sync.message_more", count=len(parts) - len(shown)))
        return t("sync.message", domain=domain_id, items=t("sync.list_separator").join(shown))

    def push(self, domain_id: str, message: str | None = None) -> SyncStatus:
        """同步推送（第 10.4 節）：推送前檢查、建立提交、合併遠端的新提交、推送（永遠不強推）。"""
        source = self._require_source(domain_id)
        preview = self.preview(domain_id)
        if preview.blockers:
            raise invalid(
                "sync_blocked",
                t("error.sync_blocked", count=len(preview.blockers)),
                problems=list(preview.blockers),
            )
        text = (message or "").strip() or preview.message
        with self._operation(domain_id):
            try:
                self._push_changes(domain_id, source, text)
            except GitError as error:
                if error.kind == "rejected":
                    self._save_sync(domain_id, error=error.message[:1000])
                else:
                    self._failed(domain_id, error)
                raise _service_error(error) from None
        return self.status(domain_id)

    def _push_changes(self, domain_id: str, source: GitSource, message: str) -> None:
        repo = self._repo(domain_id, source)
        credentials = self._credentials(domain_id, source)
        remote = self._fetch(
            repo, source, credentials, _text(self._sync_info(domain_id).get("branch"))
        )
        folder = self.storage.domain_dir(domain_id)
        info = self._sync_info(domain_id)
        synced = _text(info.get("syncedCommit"))
        base = self._tree(repo, synced, source.directory) if self._has_commit(repo, synced) else {}
        theirs = self._tree(repo, remote.commit, source.directory)
        local = self._folder(folder, repo, write=True)
        result = self._settle(repo, base, local, theirs, merge(base, local, theirs))
        moment = now().isoformat(timespec="seconds")
        common: dict[str, object] = {"branch": remote.branch, "checkedAt": moment, "error": None}
        if result.conflicts:
            self._save_sync(
                domain_id,
                state="conflict",
                remoteCommit=remote.commit,
                conflicts=result.conflicts,
                **common,
            )
            raise conflict(
                "sync_conflict",
                t("error.sync_conflict", id=domain_id, count=len(result.conflicts)),
                conflicts=result.conflicts,
            )
        head = remote.commit
        if remote.commit is None or result.files != theirs:
            head = self._commit(
                repo,
                start=remote.commit,
                parents=[remote.commit] if remote.commit else [],
                directory=source.directory,
                files=result.files,
                message=message,
                source=source,
            )
            self._push(repo, head, remote.branch, credentials)
        assert head is not None
        if result.files != local:
            # 遠端的新提交也一起套用（推送時順便拉取）
            self._validate(repo, result.files, domain_id)
            with self.folder_lock:
                if self._folder(folder, None, write=False) != local:
                    # 推送已經成功；本機在這段時間的變更留到下次
                    logger.warning("%s", t("error.sync_local_changed", id=domain_id))
                else:
                    self._apply(repo, folder, result.files)
                    self._reload(domain_id)
        self._mark_synced(repo, head)
        self._save_sync(
            domain_id,
            state="checked",
            syncedCommit=head,
            remoteCommit=head,
            syncedAt=moment,
            conflicts=[],
            pushedBranch=None,
            **common,
        )

    # ------------------------------------------------------------ 衝突

    def resolve(self, domain_id: str, action: Literal["cancel", "branch", "remote"]) -> SyncStatus:
        """衝突時三選一（第 10.5 節）：取消、推送到新分支、以遠端為準（先備份本機）。"""
        source = self._require_source(domain_id)
        with self._operation(domain_id):
            if action == "cancel":
                self._save_sync(domain_id, state="checked", conflicts=[])
                return self.status(domain_id)
            try:
                if action == "branch":
                    self._push_branch(domain_id, source)
                else:
                    self._take_remote(domain_id, source)
            except GitError as error:
                self._failed(domain_id, error)
                raise _service_error(error) from None
        return self.status(domain_id)

    def _push_branch(self, domain_id: str, source: GitSource) -> None:
        """把本機的內容推送到新分支 rpa/<領域>-<日期時間>，到 GitHub 開 PR 合併後再拉取。"""
        repo = self._repo(domain_id, source)
        credentials = self._credentials(domain_id, source)
        remote = self._fetch(
            repo, source, credentials, _text(self._sync_info(domain_id).get("branch"))
        )
        info = self._sync_info(domain_id)
        synced = _text(info.get("syncedCommit"))
        start = synced if self._has_commit(repo, synced) else remote.commit
        local = self._folder(self.storage.domain_dir(domain_id), repo, write=True)
        commit = self._commit(
            repo,
            start=start,
            parents=[start] if start else [],
            directory=source.directory,
            files=local,
            message=t("sync.branch_message", domain=domain_id),
            source=source,
        )
        branch = f"rpa/{domain_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self._push(repo, commit, branch, credentials)
        self._save_sync(domain_id, pushedBranch=branch, error=None)

    def _take_remote(self, domain_id: str, source: GitSource) -> None:
        """以遠端為準：先把正在使用的資料夾整個備份到 backups/，再套用遠端最新的內容。"""
        repo = self._repo(domain_id, source)
        credentials = self._credentials(domain_id, source)
        remote = self._fetch(
            repo, source, credentials, _text(self._sync_info(domain_id).get("branch"))
        )
        theirs = self._tree(repo, remote.commit, source.directory)
        if remote.commit is None or not theirs:
            raise conflict("sync_remote_empty", t("error.sync_remote_empty", id=domain_id))
        self._validate(repo, theirs, domain_id)
        folder = self.storage.domain_dir(domain_id)
        moment = now()
        backup = (
            self.storage.backups / f"{moment.astimezone():%Y%m%d-%H%M%S}-before-remote-{domain_id}"
        )
        with self.folder_lock:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(folder, backup)
            self._apply(repo, folder, theirs)
            self._reload(domain_id)
        self._mark_synced(repo, remote.commit)
        self._save_sync(
            domain_id,
            state="checked",
            branch=remote.branch,
            syncedCommit=remote.commit,
            remoteCommit=remote.commit,
            syncedAt=moment.isoformat(timespec="seconds"),
            checkedAt=moment.isoformat(timespec="seconds"),
            conflicts=[],
            error=None,
            backup=backup.name,
        )


class _Held:
    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        self._lock.release()


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
