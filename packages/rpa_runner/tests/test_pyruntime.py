"""RPA Python 運行環境的找到、解壓與沿用（ADR 0020，rpa_runner.pyruntime）。

這裡的壓縮檔是假的（只有說明檔與一個佔位的直譯器），自我檢查換成測試自己的函式；
真正的運行環境由 tools/build_python_runtime.py 建置，CI 在三個系統跑它的自我測試。
"""

import io
import json
import os
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

from rpa_runner.pyruntime import (
    ENV_ARCHIVES,
    ENV_RUNTIME,
    MANIFEST,
    RuntimeUnavailableError,
    archive_dirs,
    available_versions,
    clean_environment,
    find_archives,
    platform_family,
    platform_tag,
    prepare,
    script_library,
)

PLATFORM = "linux-x86_64"


def make_archive(folder: Path, version: str, platform: str = PLATFORM) -> Path:
    """一個假的運行環境壓縮檔：rpa-runtime.json 與 bin/python3（內容不重要）。"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"RPA-Python-{version}-{platform}.tar.gz"
    manifest = json.dumps({"version": version, "platform": platform, "python": "3.13.9"})
    with tarfile.open(path, "w:gz") as bundle:
        for name, data in ((MANIFEST, manifest.encode()), ("bin/python3", b"#!/bin/sh\n")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {ENV_ARCHIVES: str(tmp_path / "archives"), "RPA_CACHE_DIR": str(tmp_path / "cache")}


def no_check(root: Path) -> None:
    assert (root / MANIFEST).is_file()


@pytest.mark.parametrize(
    ("system", "machine", "tag"),
    [
        ("win32", "AMD64", "windows-x86_64"),
        ("darwin", "arm64", "macos-arm64"),
        ("linux", "x86_64", "linux-x86_64"),
        ("linux", "aarch64", "linux-aarch64"),
    ],
)
def test_platform_tag(system: str, machine: str, tag: str) -> None:
    assert platform_tag(system, machine) == tag
    assert platform_family(tag) == tag.split("-")[0]


def test_first_use_extracts_then_reuses(tmp_path: Path, env: dict[str, str]) -> None:
    make_archive(tmp_path / "archives", "1.0.0")
    first = prepare("1", environ=env, platform=PLATFORM, check=no_check)
    assert not first.reused
    assert first.version == "1.0.0"
    assert first.root == tmp_path / "cache" / "python" / f"1.0.0-{PLATFORM}"
    assert (first.root / ".ready").is_file()
    second = prepare("1", environ=env, platform=PLATFORM, check=no_check)
    assert second.reused
    assert second.root == first.root
    assert first.to_json()["runtime"] == "1.0.0"


def test_newest_archive_of_the_major_version_wins(tmp_path: Path, env: dict[str, str]) -> None:
    archives = tmp_path / "archives"
    for version in ("1.0.0", "1.2.0", "1.10.1", "2.0.0"):
        make_archive(archives, version)
    make_archive(archives, "1.99.0", platform="windows-x86_64")
    assert [version for version, _ in find_archives([archives], PLATFORM)] == [
        "2.0.0",
        "1.10.1",
        "1.2.0",
        "1.0.0",
    ]
    assert prepare("1", environ=env, platform=PLATFORM, check=no_check).version == "1.10.1"
    assert available_versions(env, platform=PLATFORM)[:2] == ["2.0.0", "1.10.1"]


def test_damaged_runtime_is_extracted_again(tmp_path: Path, env: dict[str, str]) -> None:
    make_archive(tmp_path / "archives", "1.0.0")
    root = prepare("1", environ=env, platform=PLATFORM, check=no_check).root
    (root / "bin" / "python3").unlink()
    again = prepare("1", environ=env, platform=PLATFORM, check=no_check)
    assert not again.reused
    assert (again.root / "bin" / "python3").is_file()


def test_failed_self_check_leaves_nothing_behind(tmp_path: Path, env: dict[str, str]) -> None:
    make_archive(tmp_path / "archives", "1.0.0")

    def broken(root: Path) -> None:
        raise RuntimeUnavailableError("self check failed")

    with pytest.raises(RuntimeUnavailableError):
        prepare("1", environ=env, platform=PLATFORM, check=broken)
    assert [path.name for path in (tmp_path / "cache" / "python").iterdir()] == []


def test_two_processes_wanting_the_same_version_extract_once(
    tmp_path: Path, env: dict[str, str]
) -> None:
    make_archive(tmp_path / "archives", "1.0.0")
    calls: list[Path] = []
    results: list[bool] = []

    def slow_check(root: Path) -> None:
        calls.append(root)
        threading.Event().wait(0.3)

    def worker() -> None:
        results.append(prepare("1", environ=env, platform=PLATFORM, check=slow_check).reused)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert sorted(results) == [False, True]


def test_extracted_runtime_is_used_without_an_archive(tmp_path: Path, env: dict[str, str]) -> None:
    archive = make_archive(tmp_path / "archives", "1.3.0")
    prepare("1", environ=env, platform=PLATFORM, check=no_check)
    archive.unlink()
    again = prepare("1", environ=env, platform=PLATFORM, check=no_check)
    assert again.reused
    assert again.version == "1.3.0"
    assert available_versions(env, platform=PLATFORM) == ["1.3.0"]


def test_missing_runtime(tmp_path: Path, env: dict[str, str]) -> None:
    make_archive(tmp_path / "archives", "2.0.0")
    with pytest.raises(RuntimeUnavailableError, match="no RPA Python runtime 1"):
        prepare("1", environ=env, platform=PLATFORM, check=no_check)


def test_override_folder(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / MANIFEST).write_text(json.dumps({"version": "1.4.2"}), encoding="utf-8")
    env = {ENV_RUNTIME: str(root)}
    assert prepare("1", environ=env).root == root
    with pytest.raises(RuntimeUnavailableError):
        prepare("2", environ=env)


def test_clean_environment_drops_other_pythons() -> None:
    cleaned = clean_environment(
        {
            "PATH": "/usr/bin",
            "PYTHONPATH": "/somewhere",
            "PYTHONHOME": "/x",
            "VIRTUAL_ENV": "/venv",
            "CONDA_PREFIX": "/conda",
            "PLAYWRIGHT_BROWSERS_PATH": "/pw",
            "RPA_WORKER_TOKEN": "secret",
            "PYTHON_API_KEY": "kept because it is a secret",
            "LANG": "zh_TW.UTF-8",
        },
        keep=["PYTHON_API_KEY"],
    )
    assert cleaned == {
        "PATH": "/usr/bin",
        "PYTHON_API_KEY": "kept because it is a secret",
        "LANG": "zh_TW.UTF-8",
    }


def test_script_library_is_the_runners_rpa_script(tmp_path: Path) -> None:
    env = {"RPA_CACHE_DIR": str(tmp_path / "cache")}
    first = script_library(env)
    assert first.parent == tmp_path / "cache" / "python"
    assert first.name.startswith("rpa-script-")
    copied = {path.name for path in (first / "rpa_script").iterdir()}
    assert {"__init__.py", "__main__.py", "core.py"} <= copied
    assert "__pycache__" not in copied
    assert script_library(env) == first  # 同一份程式沿用


def test_other_script_libraries_are_removed_after_a_week(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "python"
    old, recent = cache / "rpa-script-0000000000000000", cache / "rpa-script-1111111111111111"
    for folder in (old, recent):
        (folder / "rpa_script").mkdir(parents=True)
    week_ago = time.time() - 8 * 86400
    os.utime(old, (week_ago, week_ago))
    script_library({"RPA_CACHE_DIR": str(tmp_path / "cache")})
    assert not old.exists()
    assert recent.exists()


def test_frozen_app_looks_in_its_bundled_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    found = archive_dirs({})
    assert found[0] == tmp_path / "_internal" / "runtimes"
