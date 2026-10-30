"""RPA Python 運行環境（ADR 0020）：找到、解壓、沿用。

運行環境是平台自己建置的一套 Python（python-build-standalone 加上固定的套件，見
``runtimes/python/``），打包成 ``RPA-Python-<版本>-<平台>.tar.gz``，附在 Worker App 與 Linux
伺服器分發包裡。執行運行環境模式的 Python 節點（``script.runtime``）時：

1. 找這個主版本可以用的壓縮檔（:func:`archive_dirs`），選版本最新的一個；
2. 快取資料夾的 ``python/<版本>-<平台>/`` 已經解壓、``.ready`` 記的雜湊和壓縮檔裡的
   ``rpa-runtime.json`` 相同，就直接沿用（只讀兩個小檔案）；
3. 否則解壓到同一層的暫存資料夾，用新的直譯器做一次自我檢查，寫 ``.ready``，再改名成正式的
   資料夾。同時要同一版的程序以鎖檔排隊；解壓到一半失敗就丟掉，下次重來。

沒有壓縮檔時，快取裡已經解壓好的同一主版本也可以用（例如開發環境用
``tools/build_python_runtime.py --install`` 建的）。環境變數 ``RPA_PYTHON_RUNTIME`` 指向一個
已經解壓的運行環境時直接用它（測試與開發用）。

壓縮檔的內容：最上層就是運行環境的根目錄（``rpa-runtime.json``、``bin/python3`` 或
``python.exe``、標準函式庫與 site-packages）。
"""

import contextlib
import hashlib
import json
import os
import platform as platform_module
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from rpa_runner.commands import is_frozen, no_window_flags
from rpa_runner.profiles import cache_dir

__all__ = [
    "ARCHIVE_PATTERN",
    "ENV_ARCHIVES",
    "ENV_RUNTIME",
    "MANIFEST",
    "PreparedRuntime",
    "RuntimeUnavailableError",
    "archive_dirs",
    "available_versions",
    "find_archives",
    "platform_tag",
    "prepare",
    "python_path",
    "read_manifest",
]

ENV_RUNTIME: Final = "RPA_PYTHON_RUNTIME"
"""直接用這個資料夾裡已經解壓的運行環境（開發與測試）。"""
ENV_ARCHIVES: Final = "RPA_PYTHON_ARCHIVES"
"""放運行環境壓縮檔的資料夾，多個用 os.pathsep 分隔（分發包的啟動腳本會設定）。"""
MANIFEST: Final = "rpa-runtime.json"
"""運行環境根目錄裡的說明檔：版本、平台、Python 版本、套件清單。"""
READY: Final = ".ready"
"""解壓並自我檢查通過的標記，內容是 MANIFEST 的 sha256。"""
ARCHIVE_PATTERN: Final = re.compile(
    r"RPA-Python-(?P<version>\d+\.\d+\.\d+)-(?P<platform>[a-z]+-[a-z0-9_]+)\.tar\.gz"
)
LOCK_SECONDS: Final = 600.0
"""鎖檔超過這麼久沒有更新，當成前一個程序已經不在了。"""
_SELF_CHECK: Final = (
    "import json, sqlite3, ssl, rpa_script; print(json.dumps(rpa_script.selfcheck()))"
)


class RuntimeUnavailableError(Exception):
    """運行環境準備不了；訊息給人看（已是目前語言或技術細節）。"""


@dataclass(frozen=True, slots=True)
class PreparedRuntime:
    """準備好的運行環境。"""

    root: Path
    version: str
    platform: str
    python_version: str
    reused: bool
    """沿用已經解壓的（True），或這次才解壓（False）。"""
    prepared_ms: int

    @property
    def python(self) -> Path:
        return python_path(self.root)

    def to_json(self) -> dict[str, object]:
        return {
            "runtime": self.version,
            "platform": self.platform,
            "python": self.python_version,
            "reused": self.reused,
            "preparedMs": self.prepared_ms,
        }


def platform_tag(system: str | None = None, machine: str | None = None) -> str:
    """這台電腦的平台代號：``windows-x86_64``、``macos-arm64``、``linux-x86_64``、``linux-aarch64``。"""
    name = (system or sys.platform).lower()
    arch = (machine or platform_module.machine()).lower()
    if name.startswith("win"):
        family = "windows"
    elif name in ("darwin", "macos"):
        family = "macos"
    else:
        family = "linux"
    if arch in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif arch in ("arm64", "aarch64"):
        arch = "arm64" if family == "macos" else "aarch64"
    return f"{family}-{arch}"


def platform_family(tag: str) -> str:
    """平台代號的系統部分（``windows``、``macos``、``linux``），對照場景的 ``script.platforms``。"""
    return tag.split("-", 1)[0]


def python_path(root: Path) -> Path:
    """運行環境的直譯器：Windows 是根目錄的 python.exe，其他系統是 bin/python3。"""
    for candidate in (root / "python.exe", root / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    return root / "bin" / "python3"


def read_manifest(root: Path) -> dict[str, object]:
    """運行環境的說明檔；讀不到或格式不對時拋出 RuntimeUnavailableError。"""
    try:
        data: object = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeUnavailableError(f"{root / MANIFEST}: {error}") from error
    manifest = cast("dict[str, object]", data) if isinstance(data, dict) else {}
    if not isinstance(manifest.get("version"), str):
        raise RuntimeUnavailableError(f"{root / MANIFEST}: invalid manifest")
    return manifest


def archive_dirs(environ: Mapping[str, str] | None = None) -> list[Path]:
    """可能放著運行環境壓縮檔的資料夾（依序）。

    ``RPA_PYTHON_ARCHIVES``；打包後的 App 自己的 ``runtimes/``（macOS 是 ``Contents/Resources``）；
    Python 安裝位置旁邊的 ``runtimes/``（伺服器分發包）。
    """
    env = os.environ if environ is None else environ
    found = [Path(item) for item in env.get(ENV_ARCHIVES, "").split(os.pathsep) if item]
    if is_frozen():
        here = Path(sys.executable).resolve().parent
        found += [here / "runtimes", here.parent / "Resources" / "runtimes"]
    found += [Path(sys.prefix) / "runtimes", Path(sys.prefix).parent / "runtimes"]
    return list(dict.fromkeys(found))


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def find_archives(dirs: Iterable[Path], platform: str) -> list[tuple[str, Path]]:
    """這個平台的壓縮檔：(版本, 路徑)，版本由新到舊。"""
    found: dict[str, Path] = {}
    for folder in dirs:
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            match = ARCHIVE_PATTERN.fullmatch(path.name)
            if match and match["platform"] == platform and path.is_file():
                found.setdefault(match["version"], path)
    return sorted(found.items(), key=lambda item: _version_key(item[0]), reverse=True)


def _ready_dirs(root: Path, platform: str) -> list[tuple[str, Path]]:
    """快取裡已經解壓、自我檢查通過的運行環境：(版本, 資料夾)，版本由新到舊。"""
    found: list[tuple[str, Path]] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return found
    for path in entries:
        version, _, tag = path.name.partition("-")
        if tag == platform and re.fullmatch(r"\d+\.\d+\.\d+", version) and (path / READY).is_file():
            found.append((version, path))
    return sorted(found, key=lambda item: _version_key(item[0]), reverse=True)


def available_versions(
    environ: Mapping[str, str] | None = None, *, platform: str | None = None
) -> list[str]:
    """這台電腦能用的運行環境版本（附帶的壓縮檔與快取裡已經解壓的），由新到舊。

    Worker 上線時回報給管理 Portal，派工時比對主版本。
    """
    env = os.environ if environ is None else environ
    tag = platform or platform_tag()
    versions: set[str] = set()
    override = env.get(ENV_RUNTIME)
    if override:
        with contextlib.suppress(RuntimeUnavailableError):
            versions.add(str(read_manifest(Path(override))["version"]))
    versions.update(version for version, _ in find_archives(archive_dirs(env), tag))
    versions.update(version for version, _ in _ready_dirs(cache_dir(env) / "python", tag))
    return sorted(versions, key=_version_key, reverse=True)


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def _manifest_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive_manifest(archive: Path) -> bytes:
    """壓縮檔裡 rpa-runtime.json 的內容（不解壓整個檔案）。"""
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            for name in (MANIFEST, f"./{MANIFEST}"):
                try:
                    member = bundle.getmember(name)
                except KeyError:
                    continue
                handle = bundle.extractfile(member)
                if handle is not None:
                    return handle.read()
    except (OSError, tarfile.TarError) as error:
        raise RuntimeUnavailableError(f"{archive.name}: {error}") from error
    raise RuntimeUnavailableError(f"{archive.name}: {MANIFEST} missing")


def _acquire(lock: Path, wait_seconds: float) -> None:
    """建立鎖檔；別的程序正在解壓同一版時等它完成（或鎖檔太舊時接手）。"""
    end = time.monotonic() + wait_seconds
    lock.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > LOCK_SECONDS
            except FileNotFoundError:
                continue
            if stale:
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() >= end:
                raise RuntimeUnavailableError(f"{lock}: busy") from None
            time.sleep(0.2)
            continue
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        return


def _self_check(root: Path, timeout: float = 60.0) -> None:
    """用新解壓的直譯器跑一次自我檢查：能 import 標準函式庫的重要模組與 rpa_script。"""
    command = [str(python_path(root)), "-E", "-s", "-X", "utf8", "-c", _SELF_CHECK]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=clean_environment(os.environ),
            creationflags=no_window_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeUnavailableError(f"self check: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
        raise RuntimeUnavailableError(f"self check failed: {' '.join(detail)}")


def _extract(archive: Path, target: Path, manifest: bytes, check: Callable[[Path], None]) -> None:
    """解壓到 target 旁邊的暫存資料夾、自我檢查、寫 .ready，再改名成 target。"""
    temp = target.with_name(f".tmp-{target.name}-{uuid.uuid4().hex[:8]}")
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(temp, filter="data")
        python = python_path(temp)
        if os.name != "nt" and python.is_file():
            python.chmod(python.stat().st_mode | 0o111)
        check(temp)
        (temp / READY).write_text(_manifest_digest(manifest), encoding="utf-8")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        temp.rename(target)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _usable(folder: Path, digest: str | None) -> bool:
    try:
        ready = (folder / READY).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if digest is not None and ready != digest:
        return False
    try:
        manifest = (folder / MANIFEST).read_bytes()
    except OSError:
        return False
    return _manifest_digest(manifest) == ready and python_path(folder).is_file()


def prepare(
    major: str,
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    wait_seconds: float = 300.0,
    clock: Callable[[], float] = time.monotonic,
    check: Callable[[Path], None] | None = None,
) -> PreparedRuntime:
    """準備這個主版本的運行環境（找到、必要時解壓），失敗時拋出 RuntimeUnavailableError。

    ``check`` 是解壓後的自我檢查（預設用新的直譯器 import 重要的模組；測試可以換掉）。
    """
    started = clock()
    env = os.environ if environ is None else environ
    tag = platform or platform_tag()

    def done(root: Path, reused: bool) -> PreparedRuntime:
        data = read_manifest(root)
        version = str(data["version"])
        if _major(version) != major:
            raise RuntimeUnavailableError(f"{root}: runtime {version} is not major version {major}")
        return PreparedRuntime(
            root=root,
            version=version,
            platform=str(data.get("platform") or tag),
            python_version=str(data.get("python") or ""),
            reused=reused,
            prepared_ms=int((clock() - started) * 1000),
        )

    override = env.get(ENV_RUNTIME)
    if override:
        return done(Path(override), reused=True)
    cache = cache_dir(env) / "python"
    archives = [item for item in find_archives(archive_dirs(env), tag) if _major(item[0]) == major]
    if archives:
        version, archive = archives[0]
        target = cache / f"{version}-{tag}"
        manifest = _archive_manifest(archive)
        digest = _manifest_digest(manifest)
        if _usable(target, digest):
            return done(target, reused=True)
        lock = cache / f".{target.name}.lock"
        _acquire(lock, wait_seconds)
        try:
            if _usable(target, digest):  # 等鎖的時候別人已經解壓好了
                return done(target, reused=True)
            _extract(archive, target, manifest, check or _self_check)
        finally:
            lock.unlink(missing_ok=True)
        return done(target, reused=False)
    for version, folder in _ready_dirs(cache, tag):
        if _major(version) == major and _usable(folder, None):
            return done(folder, reused=True)
    raise RuntimeUnavailableError(f"no RPA Python runtime {major} for {tag}")


_DROPPED_PREFIXES: Final = ("PYTHON", "CONDA_", "PLAYWRIGHT_", "RPA_WORKER_", "PIP_", "UV_")
_DROPPED: Final = frozenset({"VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "PYTHONHOME", "PYTHONPATH"})


def clean_environment(environ: Mapping[str, str], keep: Sequence[str] = ()) -> dict[str, str]:
    """給運行環境的子程序用的環境變數：拿掉會影響 Python 的、其他 Python 環境與 Worker 自己的。

    ``keep`` 是一定要保留的名稱（例如這次執行的 Secrets，名稱剛好以 PYTHON 開頭也照樣給）。
    """
    kept = set(keep)
    return {
        key: value
        for key, value in environ.items()
        if key in kept
        or (key.upper() not in _DROPPED and not key.upper().startswith(_DROPPED_PREFIXES))
    }
