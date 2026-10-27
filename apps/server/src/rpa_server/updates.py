"""伺服器的分層更新（ADR 0018）：安裝更新檔、等到閒置時重新啟動、遷移前備份、確認新版本能用。

分發包的 bin/rpa 設定 ``RPA_RELEASE_DIR``（目前這份程式所在的版本資料夾）；裝好的版本在
``<安裝位置>/releases/<版本>/``，旁邊有 ``current``、``runtimes/``、``run/``（見 install.sh）。
從 clone 執行或還沒安裝的分發包沒有這些，:meth:`Layout.detect` 回傳 None，更新檔不能用。

流程：

1. ``rpa update 更新檔``（:func:`install_update`）：用執行環境的公鑰驗證，解開成新的版本資料夾、
   連到需要的執行環境、確認能載入，再換 ``current``；寫下 ``run/update.state``（新版本與上一版）
   與 ``run/restart.request``。
2. 執行中的伺服器（``bin/rpa serve`` 啟動、``RPA_SUPERVISED=1``）的 :class:`RestartWatcher` 看到
   重新啟動的請求，等到沒有進行中的錄製、逐步調試、人工登入、本機執行時結束，結束碼
   :data:`RESTART_EXIT`；bin/rpa 用 ``current`` 的版本再啟動。
3. 新版本啟動時：資料庫要遷移時先備份 SQLite（:func:`before_upgrade`），開始服務後刪掉
   ``update.state``（:func:`mark_started`）。開始服務之前就結束的話，bin/rpa 退回上一版並還原備份。
"""

import contextlib
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from sqlalchemy import Engine

from rpa_core.i18n import DEFAULT_LOCALE, Locale, use_locale
from rpa_server.i18n import t
from rpa_update.errors import UpdateError
from rpa_update.manifest import Manifest, UpdateFile
from rpa_update.runtime import Runtime, load_runtime

__all__ = [
    "KEEP",
    "RELEASE_ENV",
    "RESTART_EXIT",
    "SUPERVISED_ENV",
    "Installed",
    "Layout",
    "RestartWatcher",
    "before_upgrade",
    "install_update",
    "mark_started",
    "prune",
    "read_state",
    "supervised",
    "write_state",
]

RELEASE_ENV: Final = "RPA_RELEASE_DIR"
SUPERVISED_ENV: Final = "RPA_SUPERVISED"
RESTART_EXIT: Final = 75
"""請 bin/rpa 用 ``current`` 的版本重新啟動的結束碼（EX_TEMPFAIL）。"""
KEEP: Final = 3
"""保留最近幾個版本（和 install.sh 的預設相同）。"""
UPDATE_FILE: Final = "update.zip"
"""版本資料夾裡的更新檔：之後裝置從伺服器取得同一個版本時用（第二階段）。"""
_CHECK_SECONDS: Final = 120

logger = logging.getLogger("rpa_server.updates")


def read_state(path: Path) -> dict[str, str]:
    """``KEY=值`` 一行一項的狀態檔（bin/rpa 用 sed 讀）；沒有檔案時回傳空的。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key and key not in values:
            values[key] = value
    return values


def write_state(path: Path, values: Mapping[str, str]) -> None:
    """寫狀態檔：先寫暫存檔再改名，讀的一方不會讀到一半。"""
    for key, value in values.items():
        if "\n" in key or "=" in key or "\n" in value:
            raise ValueError(f"狀態檔的值不能有換行：{key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True, slots=True)
class Layout:
    """分發包的安裝位置與這份程式所在的版本。"""

    prefix: Path
    release: str
    """這份程式所在的版本資料夾名稱（``0.6.0-1a2b3c4``）。"""

    @classmethod
    def detect(cls, environ: Mapping[str, str] | None = None) -> "Layout | None":
        env = os.environ if environ is None else environ
        value = env.get(RELEASE_ENV)
        if not value:
            return None
        directory = Path(value)
        prefix = directory.parent.parent
        if directory.parent.name != "releases" or not (prefix / "current").is_symlink():
            return None
        return cls(prefix=prefix, release=directory.name)

    @property
    def releases(self) -> Path:
        return self.prefix / "releases"

    @property
    def runtimes(self) -> Path:
        return self.prefix / "runtimes"

    @property
    def run(self) -> Path:
        return self.prefix / "run"

    @property
    def state_file(self) -> Path:
        return self.run / "update.state"

    @property
    def failed_file(self) -> Path:
        return self.run / "update.failed"

    @property
    def restart_file(self) -> Path:
        return self.run / "restart.request"

    def current_release(self) -> str:
        return (self.prefix / "current").readlink().name

    def switch(self, release: str) -> None:
        """原子地把 ``current`` 換成 ``release``（新連結先建好再改名蓋過去）。

        Windows 的改名蓋不過指向資料夾的連結（WinError 5，存取被拒）：先刪掉舊的連結再改名，
        不是原子的。分發包只支援 Linux，這只讓 Windows 上的開發環境與測試能跑
        （2026-10-27，每晚完整測試 issue #80、一鍵安裝腳本 issue #74）。
        """
        temporary = self.prefix / ".current.new"
        current = self.prefix / "current"
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        temporary.symlink_to(f"releases/{release}", target_is_directory=True)
        if os.name == "nt":
            with contextlib.suppress(FileNotFoundError):
                current.unlink()
        temporary.replace(current)


# ---------------------------------------------------------------- 安裝更新檔


@dataclass(frozen=True, slots=True)
class Installed:
    manifest: Manifest
    release: str
    previous: str | None
    """換過來之前的版本；已經是這個版本時是 None。"""
    runtime: str

    @property
    def already(self) -> bool:
        return self.previous is None


def _clean_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    drop = ("PYTHON", "VIRTUAL_ENV", RELEASE_ENV, SUPERVISED_ENV, "RPA_EXAMPLES_DIR")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env.update(extra or {})
    return env


def _check_release(directory: Path) -> None:
    """新的版本資料夾能用：rpa 命令與伺服器的程式載入得了（同 install.sh 的 verify_release）。"""
    checks: Sequence[tuple[Sequence[str], Mapping[str, str]]] = (
        ([str(directory / "bin" / "rpa"), "--version"], _clean_env()),
        (
            [
                str(directory / "python" / "bin" / "python3"),
                "-c",
                "import sqlite3, ssl; from rpa_server.app import create_app; "
                "from rpa_server.config import Settings",
            ],
            _clean_env({"PYTHONPATH": str(directory / "app"), "PYTHONNOUSERSITE": "1"}),
        ),
    )
    for command, env in checks:
        try:
            done = subprocess.run(
                command,
                env=dict(env),
                capture_output=True,
                text=True,
                timeout=_CHECK_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise UpdateError("release_broken", detail=str(error)) from None
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
            raise UpdateError("release_broken", detail=detail[0])


def _build_info(manifest: Manifest, runtime: str) -> str:
    lines = {
        "app": "server",
        "version": manifest.version,
        "commit": manifest.commit,
        "arch": platform.machine(),
        "python": platform.python_version(),
        "runtime": runtime,
        "built_at": manifest.built_at,
        "installed_from": "update",
    }
    return "".join(f"{key}={value}\n" for key, value in lines.items())


def install_update(
    layout: Layout,
    path: Path,
    *,
    now: bool = False,
    keep: int = KEEP,
    runtime: Runtime | None = None,
    check: Callable[[Path], None] | None = None,
) -> Installed:
    """安裝更新檔並換掉 ``current``，請執行中的伺服器重新啟動。錯誤時拋出 UpdateError。

    ``runtime`` 預設是執行這段程式的執行環境；``check`` 確認新的版本資料夾能用（測試換掉）。
    """
    info = load_runtime() if runtime is None else runtime
    if info is None:
        raise UpdateError("not_packaged")
    with UpdateFile(path, info.keys) as update:
        manifest = update.manifest
        needed = manifest.runtime_for(info.target)
        if needed is None:
            raise UpdateError("no_build_for_target", target=info.target, version=manifest.version)
        if not (layout.runtimes / needed / "python" / "bin" / "python3").exists():
            raise UpdateError("runtime_missing", runtime=needed, version=manifest.version)
        release = manifest.release
        target = layout.releases / release
        current = layout.current_release()
        if release == current:
            if not (target / UPDATE_FILE).exists():
                shutil.copyfile(path, target / UPDATE_FILE)
            return Installed(manifest, release, None, needed)
        update.check()
        staging = layout.releases / f".{release}.tmp.{os.getpid()}"
        shutil.rmtree(staging, ignore_errors=True)
        try:
            update.extract("app/", staging / "app")
            update.extract("server/", staging)
            (staging / "python").symlink_to(f"../../runtimes/{needed}/python")
            (staging / "BUILD_INFO").write_text(_build_info(manifest, needed), encoding="utf-8")
            (check or _check_release)(staging)
            shutil.copyfile(path, staging / UPDATE_FILE)
            if target.exists():  # 之前裝過（不是使用中的版本）：換成這一份
                shutil.rmtree(target)
            staging.rename(target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    os.utime(target)  # 修改時間＝最近一次安裝，舊版本依它刪除（和 install.sh 相同）
    with contextlib.suppress(FileNotFoundError):
        layout.failed_file.unlink()
    write_state(layout.state_file, {"target": release, "previous": current})
    layout.switch(release)
    write_state(layout.restart_file, {"target": release, "now": "1" if now else "0"})
    prune(layout, keep=keep, protect={release, current, layout.release})
    return Installed(manifest, release, current, needed)


def prune(layout: Layout, *, keep: int = KEEP, protect: set[str] | None = None) -> list[str]:
    """保留最近的 ``keep`` 個版本（``protect`` 一定保留），再刪掉沒有版本用到的執行環境。"""
    removed: list[str] = []
    kept = set(protect or ())
    folders = [p for p in layout.releases.iterdir() if p.is_dir() and not p.name.startswith(".")]
    for folder in sorted(folders, key=lambda p: p.stat().st_mtime, reverse=True):
        if folder.name in kept:
            continue
        if len(kept) < keep:
            kept.add(folder.name)
            continue
        shutil.rmtree(folder, ignore_errors=True)
        removed.append(folder.name)
    used = {
        link.readlink().parent.name
        for link in layout.releases.glob("*/python")
        if link.is_symlink()
    }
    if layout.runtimes.is_dir():
        for runtime in layout.runtimes.iterdir():
            if runtime.is_dir() and not runtime.name.startswith(".") and runtime.name not in used:
                shutil.rmtree(runtime, ignore_errors=True)
                removed.append(f"runtimes/{runtime.name}")
    return removed


# ---------------------------------------------------------------- 重新啟動


class RestartWatcher:
    """等 ``run/restart.request``：沒有進行中的工作（或要求立即）時呼叫 ``stop``。

    只在 bin/rpa serve 底下執行（``RPA_SUPERVISED=1``）：沒有人會再啟動的話，結束就等於停機。
    """

    def __init__(
        self,
        layout: Layout,
        *,
        busy: Callable[[], Sequence[str]],
        stop: Callable[[], None],
        interval: float = 2.0,
        locale: Locale = DEFAULT_LOCALE,
    ) -> None:
        self.layout = layout
        self.busy = busy
        self.stop = stop
        self.interval = interval
        self.locale: Locale = locale
        """日誌與等待原因用伺服器的語言（背景執行緒沒有請求的語言）。"""
        self.triggered = False
        self._closing = threading.Event()
        self._thread: threading.Thread | None = None
        self._waiting: tuple[str, ...] = ()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="restart-watcher", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closing.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._closing.wait(self.interval):
            try:
                with use_locale(self.locale):
                    if self.check():
                        return
            except Exception:
                logger.exception("檢查重新啟動的請求失敗")

    def check(self) -> bool:
        """看一次請求；決定重新啟動時回傳 True。"""
        request = read_state(self.layout.restart_file)
        target = request.get("target")
        if not target:
            return False
        if target == self.layout.release or target != self.layout.current_release():
            # 已經是這個版本，或 current 已經換到別的版本（例如退回）：請求過時了
            with contextlib.suppress(FileNotFoundError):
                self.layout.restart_file.unlink()
            return False
        if request.get("now") != "1":
            reasons = tuple(self.busy())
            if reasons:
                if reasons != self._waiting:
                    logger.warning(
                        "%s", t("server.update_waiting", release=target, reasons=", ".join(reasons))
                    )
                    self._waiting = reasons
                return False
        with contextlib.suppress(FileNotFoundError):
            self.layout.restart_file.unlink()
        logger.warning("%s", t("server.update_restarting", release=target))
        self.triggered = True
        self.stop()
        return True


# ---------------------------------------------------------------- 新版本啟動時


def _sqlite_path(engine: Engine) -> Path | None:
    url = engine.url
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def before_upgrade(engine: Engine, backups: Path, *, pending: bool, versioned: bool) -> Path | None:
    """資料庫要遷移時先備份 SQLite（``pending``：有還沒套用的遷移；``versioned``：不是全新的）。

    剛換上的版本（``update.state`` 指向它）把備份與資料庫的位置記進狀態檔，起不來時 bin/rpa 還原。
    PostgreSQL 由管理員自己備份：只提醒。回傳備份的檔案。
    """
    if not pending or not versioned:
        return None
    layout = Layout.detect()
    state = read_state(layout.state_file) if layout is not None else {}
    updating = layout is not None and state.get("target") == layout.release
    database = _sqlite_path(engine)
    if database is None:
        logger.warning("%s", t("server.update_postgres"))
        return None
    moment = datetime.now(UTC).astimezone()
    suffix = layout.release if layout is not None else "upgrade"
    folder = backups / f"{moment:%Y%m%d-%H%M%S}-before-{suffix}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "rpa.db"
    source = sqlite3.connect(database)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    logger.warning("%s", t("server.update_backup", path=target))
    if updating and layout is not None:
        write_state(
            layout.state_file,
            {**state, "backup": str(target.resolve()), "database": str(database.resolve())},
        )
    return target


def mark_started() -> None:
    """伺服器開始服務：剛換上的版本確認能用（刪掉 ``update.state``），清掉過時的重新啟動請求。"""
    layout = Layout.detect()
    if layout is None:
        return
    state = read_state(layout.state_file)
    if state.get("target") == layout.release:
        layout.state_file.unlink(missing_ok=True)
        logger.warning("%s", t("server.update_confirmed", release=layout.release))
    request = read_state(layout.restart_file)
    if request.get("target") == layout.release:
        layout.restart_file.unlink(missing_ok=True)


def supervised(environ: Mapping[str, str] | None = None) -> bool:
    """這個伺服器是不是由 bin/rpa serve 啟動（結束碼 75 時會有人再啟動它）。"""
    env = os.environ if environ is None else environ
    return env.get(SUPERVISED_ENV) == "1"
