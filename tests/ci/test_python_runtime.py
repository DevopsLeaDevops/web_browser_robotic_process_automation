"""RPA Python 運行環境的建置工具（tools/build_python_runtime.py，ADR 0020）。

真的建置要下載 CPython 與套件，由 CI（python-runtime.yml）在每個平台執行；這裡測不必連網的部分：
設定檔、平台代號和 Runner 一致、精簡、打包出來的壓縮檔 Runner 認得而且解壓得了。
"""

import json
import re
import tarfile
from pathlib import Path

import pytest

from rpa_runner import pyruntime
from tools import build_python_runtime as tool

ROOT = Path(__file__).resolve().parents[2]


def test_spec_pins_python_and_lists_every_worker_platform() -> None:
    spec = tool.load_spec()
    assert set(spec.platforms) == {"windows-x86_64", "macos-arm64", "linux-x86_64", "linux-aarch64"}
    minor = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert spec.python.startswith(f"{minor}.")  # 和程式碼層、App 的 Python 同一個次版本
    for platform in spec.platforms.values():
        if platform.tag.startswith("linux-"):
            assert platform.wheels.endswith("manylinux_2_28")  # 公司伺服器的 glibc 下限
    assert pyruntime.ARCHIVE_PATTERN.fullmatch(spec.archive_name("linux-x86_64"))


@pytest.mark.parametrize(
    ("system", "machine"),
    [
        ("win32", "AMD64"),
        ("darwin", "arm64"),
        ("linux", "x86_64"),
        ("linux", "aarch64"),
    ],
)
def test_platform_tags_match_the_runner(system: str, machine: str) -> None:
    assert tool.host_platform(system, machine) == pyruntime.platform_tag(system, machine)


def test_lock_covers_every_requirement() -> None:
    """requirements.in 改了要重新產生 requirements.lock（bootstrap 或 lock 命令）。"""
    source = tool.SOURCE
    wanted = {
        re.split(r"[<>=!~;\[ ]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")
        for line in (source / "requirements.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    lock = (source / "requirements.lock").read_text(encoding="utf-8")
    pinned = {
        match.group(1).lower().replace("_", "-")
        for match in re.finditer(r"^([A-Za-z0-9_.-]+)==", lock, re.MULTILINE)
    }
    assert wanted <= pinned, sorted(wanted - pinned)
    assert "--hash=sha256:" in lock
    assert tool.LOCK_COMMAND in lock


def fake_root(root: Path) -> tuple[Path, Path]:
    """假的運行環境（Linux 的版面）：標準函式庫與 site-packages 裡放一些要拿掉的東西。"""
    stdlib = root / "lib" / "python3.13"
    site = stdlib / "site-packages"
    for path in (
        stdlib / "json" / "__init__.py",
        stdlib / "tkinter" / "__init__.py",
        stdlib / "test" / "test_x.py",
        stdlib / "ensurepip" / "__init__.py",
        stdlib / "lib-dynload" / "_tkinter.cpython-313-x86_64-linux-gnu.so",
        site / "pip" / "__init__.py",
        site / "pip-25.0.dist-info" / "METADATA",
        site / "pandas" / "__init__.py",
        root / "lib" / "tcl8.6" / "init.tcl",
        root / "lib" / "thread2.8.9" / "pkgIndex.tcl",
        stdlib / "threading.py",
        root / "bin" / "pip3",
        root / "bin" / "idle3",
        root / "bin" / "python3",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return stdlib, site


def test_slim_removes_installers_gui_and_tests(tmp_path: Path) -> None:
    root = tmp_path / "root"
    stdlib, site = fake_root(root)
    removed = tool.slim(root, stdlib, site)
    assert (stdlib / "json").is_dir()
    assert (site / "pandas").is_dir()
    assert (root / "bin" / "python3").is_file()
    for gone in (
        "tkinter",
        "test",
        "ensurepip",
        "lib-dynload/_tkinter.cpython-313-x86_64-linux-gnu.so",
    ):
        assert not (stdlib / gone).exists(), gone
    assert not (site / "pip").exists()
    assert not (site / "pip-25.0.dist-info").exists()
    assert not (root / "lib" / "tcl8.6").exists()
    assert not (root / "lib" / "thread2.8.9").exists()
    assert (stdlib / "threading.py").is_file()  # Windows 不分大小寫時 lib/thread* 曾經刪到它
    assert not (root / "bin" / "pip3").exists()
    assert "lib/python3.13/tkinter" in removed
    assert "externally-managed" in (stdlib / "EXTERNALLY-MANAGED").read_text(encoding="utf-8")


def test_packed_archive_is_found_and_extracted_by_the_runner(tmp_path: Path) -> None:
    root = tmp_path / "root"
    fake_root(root)
    spec = tool.load_spec()
    manifest = {"version": spec.version, "platform": "linux-x86_64", "python": spec.python}
    (root / pyruntime.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    archive = tmp_path / "dist" / spec.archive_name("linux-x86_64")
    digest = tool.pack(root, archive)
    assert (
        archive.with_name(archive.name + ".sha256").read_text(encoding="utf-8").startswith(digest)
    )
    with tarfile.open(archive) as bundle:
        names = bundle.getnames()
        assert pyruntime.MANIFEST in names  # 最上層就是運行環境的根目錄
        assert all(member.uid == 0 and not member.uname for member in bundle.getmembers())
    env = {"RPA_CACHE_DIR": str(tmp_path / "cache"), pyruntime.ENV_ARCHIVES: str(archive.parent)}
    major = spec.version.split(".")[0]
    prepared = pyruntime.prepare(major, environ=env, platform="linux-x86_64", check=lambda _: None)
    assert prepared.version == spec.version
    assert not prepared.reused
    assert (prepared.root / "lib" / "python3.13" / "json" / "__init__.py").is_file()
