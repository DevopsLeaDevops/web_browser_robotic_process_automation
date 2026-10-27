"""伺服器的分層更新（ADR 0018，rpa_server.updates）：安裝更新檔、等到閒置時重新啟動、
遷移前備份、確認新版本能用。

用假的安裝位置（releases/、current、runtimes/）與小的更新檔測；真正的分發包用更新檔升級、
重新啟動與退回在 CI（server-package.yml）的 Rocky 8 容器裡驗證，bin/rpa 的部分在
tests/ci/test_server_package.py。
"""

import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from rpa_core.i18n import use_locale
from rpa_server.config import sqlite_url
from rpa_server.db import create_db_engine, migration_status, upgrade
from rpa_server.updates import (
    Installed,
    Layout,
    RestartWatcher,
    before_upgrade,
    install_update,
    mark_started,
    prune,
    read_state,
    write_state,
)
from rpa_update import ed25519
from rpa_update.errors import UpdateError
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import Runtime

SEED = bytes(range(32))
KEY = ed25519.public_key(SEED)
RUNTIME_ID = "0123456789abcdef"
TARGET = "server-linux-x64"
RUNTIME = Runtime(TARGET, RUNTIME_ID, (KEY,))


@pytest.fixture(autouse=True)
def _zh_hant() -> object:
    with use_locale("zh-Hant"):
        yield


def make_prefix(root: Path, current: str = "0.5.0-aaaaaaa") -> Path:
    prefix = root / "srv"
    (prefix / "releases" / current / "app").mkdir(parents=True)
    python = prefix / "runtimes" / RUNTIME_ID / "python" / "bin"
    python.mkdir(parents=True)
    (python / "python3").write_text("#!/bin/sh\n", encoding="utf-8")
    (prefix / "releases" / current / "python").symlink_to(f"../../runtimes/{RUNTIME_ID}/python")
    (prefix / "current").symlink_to(f"releases/{current}")
    return prefix


def layout_of(prefix: Path, release: str = "0.5.0-aaaaaaa") -> Layout:
    layout = Layout.detect({"RPA_RELEASE_DIR": str(prefix / "releases" / release)})
    assert layout is not None
    return layout


def make_update(
    root: Path,
    *,
    commit: str = "bbbbbbb",
    runtimes: dict[str, str] | None = None,
    seed: bytes = SEED,
) -> Path:
    content = root / f"content-{commit}"
    (content / "app" / "rpa_core").mkdir(parents=True)
    (content / "app" / "rpa_core" / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
    (content / "server" / "bin").mkdir(parents=True)
    (content / "server" / "bin" / "rpa").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (content / "server" / "bin" / "rpa").chmod(0o755)
    (content / "server" / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    files = scan_tree(content)
    manifest = Manifest(
        version="0.6.0",
        commit=commit,
        built_at="2026-10-25T09:00:00+00:00",
        fingerprint="f" * 16,
        protocol=1,
        features=(),
        runtimes={TARGET: RUNTIME_ID} if runtimes is None else runtimes,
        files=files,
    )
    path = root / f"RPA-Update-{commit}.zip"
    write_update(path, manifest, {name: content / name for name in files}, seed)
    return path


def no_check(_: Path) -> None:
    pass


def install(layout: Layout, path: Path, **options: object) -> Installed:
    return install_update(layout, path, runtime=RUNTIME, check=no_check, **options)  # type: ignore[arg-type]


# ---------------------------------------------------------------- 安裝位置


def test_layout_needs_an_installed_release(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    layout = layout_of(prefix)
    assert layout.prefix == prefix
    assert layout.release == "0.5.0-aaaaaaa"
    assert layout.current_release() == "0.5.0-aaaaaaa"
    assert Layout.detect({}) is None
    # 解壓後還沒安裝的分發包、clone：沒有 releases/ 與 current
    assert Layout.detect({"RPA_RELEASE_DIR": str(tmp_path / "RPA-Server-0.6.0")}) is None
    (prefix / "current").unlink()
    assert Layout.detect({"RPA_RELEASE_DIR": str(prefix / "releases" / "0.5.0-aaaaaaa")}) is None


def test_state_files_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "run" / "update.state"
    write_state(path, {"target": "b", "previous": "a"})
    assert path.read_text("utf-8") == "target=b\nprevious=a\n"
    assert read_state(path) == {"target": "b", "previous": "a"}
    assert read_state(tmp_path / "missing") == {}
    with pytest.raises(ValueError, match="換行"):
        write_state(path, {"target": "b\nx=1"})


# ---------------------------------------------------------------- 安裝更新檔


def test_install_switches_current_and_asks_for_restart(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    layout = layout_of(prefix)
    update = make_update(tmp_path)
    result = install(layout, update)
    assert (result.release, result.previous, result.runtime) == (
        "0.6.0-bbbbbbb",
        "0.5.0-aaaaaaa",
        RUNTIME_ID,
    )
    release = prefix / "releases" / "0.6.0-bbbbbbb"
    assert (prefix / "current").readlink().as_posix() == "releases/0.6.0-bbbbbbb"
    assert (release / "app" / "rpa_core" / "__init__.py").read_text("utf-8") == "VALUE = 2\n"
    if os.name != "nt":  # Windows 沒有執行權限位元；分發包只在 Linux
        assert (release / "bin" / "rpa").stat().st_mode & 0o111
    assert (release / "python").readlink().as_posix() == f"../../runtimes/{RUNTIME_ID}/python"
    assert f"runtime={RUNTIME_ID}" in (release / "BUILD_INFO").read_text("utf-8")
    assert (release / "update.zip").read_bytes() == update.read_bytes()
    assert read_state(layout.state_file) == {"target": "0.6.0-bbbbbbb", "previous": "0.5.0-aaaaaaa"}
    assert read_state(layout.restart_file) == {"target": "0.6.0-bbbbbbb", "now": "0"}
    assert not [path for path in (prefix / "releases").iterdir() if path.name.startswith(".")]


def test_install_same_version_again_changes_nothing(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    update = make_update(tmp_path)
    install(layout_of(prefix), update)
    (prefix / "run" / "restart.request").unlink()
    again = install(layout_of(prefix, "0.6.0-bbbbbbb"), update, now=True)
    assert again.already
    assert not (prefix / "run" / "restart.request").exists()


def test_install_now_skips_the_wait(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    layout = layout_of(prefix)
    install(layout, make_update(tmp_path), now=True)
    assert read_state(layout.restart_file)["now"] == "1"


@pytest.mark.parametrize(
    ("runtimes", "code"),
    [
        ({"server-linux-arm64": RUNTIME_ID}, "no_build_for_target"),
        ({TARGET: "f" * 16}, "runtime_missing"),
    ],
)
def test_install_needs_the_runtime(tmp_path: Path, runtimes: dict[str, str], code: str) -> None:
    prefix = make_prefix(tmp_path)
    with pytest.raises(UpdateError) as caught:
        install(layout_of(prefix), make_update(tmp_path, runtimes=runtimes))
    assert caught.value.code == code
    assert (prefix / "current").readlink().as_posix() == "releases/0.5.0-aaaaaaa"
    assert sorted(path.name for path in (prefix / "releases").iterdir()) == ["0.5.0-aaaaaaa"]


def test_install_rejects_an_untrusted_signature(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    with pytest.raises(UpdateError) as caught:
        install(layout_of(prefix), make_update(tmp_path, seed=bytes(32)))
    assert caught.value.code == "signature_untrusted"


def test_install_needs_a_packaged_runtime(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    # 開發環境沒有 runtime.json
    with pytest.raises(UpdateError) as caught:
        install_update(layout_of(prefix), make_update(tmp_path), check=no_check)
    assert caught.value.code == "not_packaged"


def test_broken_release_is_not_switched_to(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)

    def broken(_: Path) -> None:
        raise UpdateError("release_broken", detail="ImportError")

    with pytest.raises(UpdateError, match="release_broken"):
        install_update(layout_of(prefix), make_update(tmp_path), runtime=RUNTIME, check=broken)
    assert (prefix / "current").readlink().as_posix() == "releases/0.5.0-aaaaaaa"
    assert sorted(path.name for path in (prefix / "releases").iterdir()) == ["0.5.0-aaaaaaa"]
    assert not (prefix / "run" / "update.state").exists()


def test_prune_keeps_recent_and_protected_releases(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    layout = layout_of(prefix)
    old_runtime = prefix / "runtimes" / ("1" * 16) / "python"
    old_runtime.mkdir(parents=True)
    names = ["0.4.0-0000001", "0.4.1-0000002", "0.4.2-0000003", "0.4.3-0000004"]
    for number, name in enumerate(names):
        folder = prefix / "releases" / name
        folder.mkdir()
        (folder / "python").symlink_to(f"../../runtimes/{'1' * 16}/python")
        moment = time.time() - 1000 + number
        os.utime(folder, (moment, moment))
    removed = prune(layout, keep=3, protect={"0.5.0-aaaaaaa", "0.4.0-0000001"})
    left = sorted(path.name for path in (prefix / "releases").iterdir())
    assert left == ["0.4.0-0000001", "0.4.3-0000004", "0.5.0-aaaaaaa"]
    assert sorted(removed) == ["0.4.1-0000002", "0.4.2-0000003"]
    assert old_runtime.is_dir()  # 留下的舊版本還在用
    shutil_names = prune(layout, keep=1, protect={"0.5.0-aaaaaaa"})
    assert f"runtimes/{'1' * 16}" in shutil_names
    assert not old_runtime.exists()


# ---------------------------------------------------------------- 重新啟動


def watcher(layout: Layout, busy: list[str]) -> tuple[RestartWatcher, list[bool]]:
    stopped: list[bool] = []
    return RestartWatcher(layout, busy=lambda: busy, stop=lambda: stopped.append(True)), stopped


def test_watcher_waits_until_idle(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    prefix = make_prefix(tmp_path)
    install(layout_of(prefix), make_update(tmp_path))
    busy = ["1 個錄製"]
    running, stopped = watcher(layout_of(prefix), busy)  # 執行中的還是舊版本
    with caplog.at_level("WARNING"):
        assert not running.check()
        assert not running.check()
    assert stopped == []
    assert [r.getMessage() for r in caplog.records].count(
        "已經換上 0.6.0-bbbbbbb，等進行中的工作結束後重新啟動：1 個錄製"
    ) == 1
    busy.clear()
    assert running.check()
    assert stopped == [True]
    assert running.triggered
    assert not (prefix / "run" / "restart.request").exists()


def test_watcher_now_does_not_wait(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    install(layout_of(prefix), make_update(tmp_path), now=True)
    running, stopped = watcher(layout_of(prefix), ["1 個人工登入"])
    assert running.check()
    assert stopped == [True]


def test_watcher_drops_stale_requests(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    layout = layout_of(prefix)
    # 要求換成自己：已經是這個版本
    write_state(layout.restart_file, {"target": "0.5.0-aaaaaaa", "now": "1"})
    running, stopped = watcher(layout, [])
    assert not running.check()
    assert not layout.restart_file.exists()
    # current 已經不是要求的版本（例如退回了）：不要一直重新啟動
    write_state(layout.restart_file, {"target": "0.6.0-bbbbbbb", "now": "1"})
    assert not running.check()
    assert not layout.restart_file.exists()
    assert stopped == []


def test_watcher_thread_stops_the_server(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    install(layout_of(prefix), make_update(tmp_path))
    stopped: list[bool] = []
    running = RestartWatcher(
        layout_of(prefix), busy=list, stop=lambda: stopped.append(True), interval=0.01
    )
    running.start()
    try:
        for _ in range(200):
            if stopped:
                break
            time.sleep(0.01)
    finally:
        running.close()
    assert stopped == [True]


# ---------------------------------------------------------------- 新版本啟動時


def sqlite_engine(path: Path) -> Engine:
    engine = create_db_engine(sqlite_url(path))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE t (x INTEGER)")
        connection.exec_driver_sql("INSERT INTO t VALUES (42)")
    return engine


def test_backup_before_migrating(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prefix = make_prefix(tmp_path)
    install(layout_of(prefix), make_update(tmp_path))
    monkeypatch.setenv("RPA_RELEASE_DIR", str(prefix / "releases" / "0.6.0-bbbbbbb"))
    database = tmp_path / "data" / "rpa.db"
    database.parent.mkdir()
    engine = sqlite_engine(database)
    backup = before_upgrade(engine, tmp_path / "data" / "backups", pending=True, versioned=True)
    engine.dispose()
    assert backup is not None
    assert backup.parent.name.endswith("-before-0.6.0-bbbbbbb")
    with sqlite3.connect(backup) as copy:
        assert copy.execute("SELECT x FROM t").fetchall() == [(42,)]
    state = read_state(prefix / "run" / "update.state")
    assert state["backup"] == str(backup.resolve())
    assert state["database"] == str(database.resolve())


@pytest.mark.parametrize(("pending", "versioned"), [(False, True), (True, False)])
def test_no_backup_without_migrations_or_data(
    tmp_path: Path, pending: bool, versioned: bool
) -> None:
    engine = sqlite_engine(tmp_path / "rpa.db")
    assert (
        before_upgrade(engine, tmp_path / "backups", pending=pending, versioned=versioned) is None
    )
    engine.dispose()
    assert not (tmp_path / "backups").exists()


def test_postgres_is_only_reminded(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine = cast("Engine", SimpleNamespace(url=make_url("postgresql://db/rpa")))
    with caplog.at_level("WARNING"):
        assert before_upgrade(engine, tmp_path / "backups", pending=True, versioned=True) is None
    assert "PostgreSQL 不會自動備份" in caplog.text


def test_started_confirms_the_new_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prefix = make_prefix(tmp_path)
    install(layout_of(prefix), make_update(tmp_path))
    # 舊版本還在執行時不算確認
    monkeypatch.setenv("RPA_RELEASE_DIR", str(prefix / "releases" / "0.5.0-aaaaaaa"))
    mark_started()
    assert (prefix / "run" / "update.state").exists()
    monkeypatch.setenv("RPA_RELEASE_DIR", str(prefix / "releases" / "0.6.0-bbbbbbb"))
    mark_started()
    assert not (prefix / "run" / "update.state").exists()
    assert not (prefix / "run" / "restart.request").exists()


def test_migration_status(tmp_path: Path) -> None:
    engine = create_engine(sqlite_url(tmp_path / "rpa.db"))
    assert migration_status(engine) == (True, False)
    upgrade(engine)
    assert migration_status(engine) == (False, True)
    engine.dispose()
