"""建置 RPA Python 運行環境（ADR 0020）：Python 節點的運行環境模式用的那一套 Python。

    uv run python tools/build_python_runtime.py lock              # 依 requirements.in 更新鎖定檔
    uv run python tools/build_python_runtime.py build             # 建這台電腦平台的運行環境
    uv run python tools/build_python_runtime.py build --install   # 建好後解壓到本機的快取（開發用）

產物在 dist/runtime/：``RPA-Python-<版本>-<平台>.tar.gz`` 與同名的 ``.sha256``；中間檔在
build/runtime/。內容與版本在 ``runtimes/python/``（runtime.toml、requirements.in、
requirements.lock、smoke.py）。

步驟：

1. 直譯器：``uv python install`` 下載 runtime.toml 固定的 CPython（python-build-standalone；
   uv 依它內建的清單核對 sha256），整個複製出來。它不依賴系統的 Python，可以搬到任何位置。
2. 套件：照 requirements.lock 裝進這份 Python（只用 wheel、核對 sha256、選這個平台的 wheel；
   Linux 選 glibc 2.28 載入得了的）。``rpa_script`` 不裝：執行時由 Runner 提供它自己的那份
   （rpa_runner.pyruntime.script_library），程式碼層更新後不會和運行環境錯開。
3. 精簡：拿掉 pip、ensurepip、tkinter、IDLE、標準函式庫的測試；放 ``EXTERNALLY-MANAGED``，
   Worker 上沒有辦法在這份 Python 裡另外裝套件。
4. ``rpa-runtime.json``：版本、平台、Python 版本、每個套件的版本、建置的提交。
5. 用剛建好的直譯器以 ``-E -s -X utf8`` 執行 ``runtimes/python/smoke.py``（中文路徑、Excel、
   Big5 的 CSV、Word、PDF、壓縮；rpa_script 用工作區的原始碼，和 Runner 提供的方式相同），
   通過才打包。

``build`` 只建這台電腦的平台（要用那個平台的直譯器跑自我測試）；CI 在 Windows、macOS、Linux
（x64、arm64）各建一份（.github/workflows/python-runtime.yml），Worker App 與伺服器分發包建置時
也各建一份放進去（tools/build_desktop.py、tools/build_server.py 呼叫 :func:`build`）。
運行環境的內容（Python、套件）改了要升 runtime.toml 的 version：App 的環境代號（ADR 0018）只看
壓縮檔的名稱，同一個版本號的裝置不會換新的運行環境。

``lock`` 要連得到 PyPI：連不到的開發環境在提交訊息加 [bootstrap]，由 bootstrap 流程產生。
只用標準函式庫，伺服器分發包的建置（系統的 python3）也能呼叫；需要 PATH 上有 uv。
最後印出 ``archive: …``，在 GitHub Actions 裡同時寫進步驟的輸出。
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

ROOT: Final = Path(__file__).resolve().parent.parent
SOURCE: Final = ROOT / "runtimes" / "python"
SCRIPT_SOURCE: Final = ROOT / "packages" / "rpa_script" / "src"
"""自我測試用的 rpa_script（Runner 執行時把它的那份加在 import 路徑最後，這裡用工作區的）。"""
DIST: Final = ROOT / "dist" / "runtime"
WORK: Final = ROOT / "build" / "runtime"
MANIFEST: Final = "rpa-runtime.json"
"""運行環境根目錄裡的說明檔（rpa_runner.pyruntime 讀它）。"""
LOCK_COMMAND: Final = "uv run python tools/build_python_runtime.py lock"

STDLIB_REMOVED: Final = ("ensurepip", "idlelib", "tkinter", "turtledemo", "test", "turtle.py")
"""標準函式庫裡拿掉的：安裝工具、圖形介面與它的範例、測試。"""
SITE_REMOVED: Final = re.compile(r"^(pip|setuptools|wheel)([-_].*)?$", re.IGNORECASE)
EXTERNALLY_MANAGED: Final = """[externally-managed]
Error=這是 RPA Python 運行環境（ADR 0020），套件由平台固定，不能另外安裝。需要新的套件時，提出加進
 runtimes/python/requirements.in（新的次版本，所有 Worker 一起更新）。
 This is the RPA Python runtime; its packages are fixed by the platform and cannot be changed.
"""


@dataclass(frozen=True, slots=True)
class Platform:
    tag: str
    """運行環境的平台代號，例如 windows-x86_64（和 rpa_runner.pyruntime.platform_tag 相同）。"""
    uv: str
    """uv 的 Python 下載代號的後半，例如 windows-x86_64-none。"""
    wheels: str
    """``uv pip install --python-platform``。"""


@dataclass(frozen=True, slots=True)
class Spec:
    version: str
    python: str
    platforms: Mapping[str, Platform]

    def archive_name(self, tag: str) -> str:
        return f"RPA-Python-{self.version}-{tag}.tar.gz"


def load_spec(source: Path = SOURCE) -> Spec:
    data = tomllib.loads((source / "runtime.toml").read_text(encoding="utf-8"))
    raw = cast("dict[str, dict[str, str]]", data["platforms"])
    platforms = {
        tag: Platform(tag=tag, uv=str(item["uv"]), wheels=str(item["wheels"]))
        for tag, item in raw.items()
    }
    version, python = str(data["version"]), str(data["python"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"runtime.toml 的 version 要是 主.次.修：{version}")
    if not re.fullmatch(r"3\.\d+\.\d+", python):
        raise SystemExit(f"runtime.toml 的 python 要固定到修訂版（例如 3.13.14）：{python}")
    return Spec(version=version, python=python, platforms=platforms)


def host_platform(system: str | None = None, machine: str | None = None) -> str:
    """這台電腦的平台代號（和 rpa_runner.pyruntime.platform_tag 相同的規則）。"""
    name = (system or sys.platform).lower()
    arch = (machine or platform.machine()).lower()
    family = "windows" if name.startswith("win") else "macos" if name == "darwin" else "linux"
    if arch in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif arch in ("arm64", "aarch64"):
        arch = "arm64" if family == "macos" else "aarch64"
    return f"{family}-{arch}"


# ---------------------------------------------------------------- 執行命令


def _run(command: Sequence[str | Path], env: Mapping[str, str] | None = None) -> str:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.stderr.strip():
        print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
    if completed.returncode != 0:
        print(completed.stdout.rstrip(), flush=True)
        raise SystemExit(f"命令失敗（結束碼 {completed.returncode}）：{printable}")
    return completed.stdout


def find_uv() -> str:
    found = shutil.which("uv")
    if not found:
        raise SystemExit("找不到 uv（https://docs.astral.sh/uv/）")
    return found


def _clean_env() -> dict[str, str]:
    """執行建好的直譯器時的環境：不讀開發環境的 PYTHON*、VIRTUAL_ENV。"""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA_"))
    }


def python_in(root: Path) -> Path:
    windows = root / "python.exe"
    return windows if windows.is_file() else root / "bin" / "python3"


def commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]+", value) else ""


# ---------------------------------------------------------------- lock


def lock(uv: str, spec: Spec, source: Path = SOURCE) -> Path:
    """依 requirements.in 產生 requirements.lock：一份涵蓋所有平台、每個 wheel 都有 sha256。"""
    minor = ".".join(spec.python.split(".")[:2])
    target = source / "requirements.lock"
    _run(
        [
            uv,
            "pip",
            "compile",
            source / "requirements.in",
            "--universal",
            "--generate-hashes",
            "--only-binary",
            ":all:",
            "--python-version",
            minor,
            "--custom-compile-command",
            LOCK_COMMAND,
            "--output-file",
            target,
        ]
    )
    return target


# ---------------------------------------------------------------- build


def stage_python(uv: str, spec: Spec, target: Platform, root: Path) -> Path:
    """下載（已經有就沿用）固定版本的 CPython，複製到 root，回傳直譯器。"""
    key = f"cpython-{spec.python}-{target.uv}"
    _run([uv, "python", "install", key])
    executable = _run([uv, "python", "find", "--managed-python", key]).strip()
    prefix = _run(
        [executable, "-c", "import sys; print(sys.base_prefix)"], env=_clean_env()
    ).strip()
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(prefix, root, symlinks=True)
    for marker in root.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()  # uv 加的記號；這份由我們管理，裝完套件再放自己的
    python = python_in(root)
    if not python.exists():
        raise SystemExit(f"{prefix} 裡沒有 Python 直譯器")
    return python


def stdlib_dir(python: Path) -> Path:
    return Path(
        _run(
            [python, "-c", "import sysconfig; print(sysconfig.get_paths()['stdlib'])"],
            env=_clean_env(),
        ).strip()
    )


def site_dir(python: Path) -> Path:
    return Path(
        _run(
            [python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            env=_clean_env(),
        ).strip()
    )


def install_packages(uv: str, python: Path, target: Platform, source: Path) -> None:
    """照鎖定檔裝第三方套件：只用 wheel、核對 sha256、選這個平台的 wheel。"""
    requirements = source / "requirements.lock"
    if not requirements.is_file():
        raise SystemExit(f"沒有 {requirements}：先執行 {LOCK_COMMAND}")
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            python,
            "--break-system-packages",
            "--python-platform",
            target.wheels,
            "--link-mode",
            "copy",
            "--compile-bytecode",
            "--no-deps",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "-r",
            requirements,
        ]
    )


def slim(root: Path, stdlib: Path, site: Path) -> list[str]:
    """拿掉安裝工具、圖形介面與測試，放 EXTERNALLY-MANAGED；回傳拿掉的項目（相對路徑）。"""
    removed: list[str] = []

    def remove(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path.relative_to(root).as_posix())

    for name in STDLIB_REMOVED:
        path = stdlib / name
        if path.exists():
            remove(path)
    for path in sorted(site.iterdir()):
        if SITE_REMOVED.match(path.name):
            remove(path)
    for folder in (root / "bin", root / "Scripts"):
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if re.match(r"^(pip|idle|2to3|pydoc)", path.name):
                    remove(path)
    for pattern in ("lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "tcl", "DLLs/_tkinter.pyd"):
        for path in sorted(root.glob(pattern)):
            remove(path)
    for path in sorted(root.glob("DLLs/t[ck]*.dll")):
        remove(path)
    for path in sorted(stdlib.glob("lib-dynload/_tkinter*")):
        remove(path)
    (stdlib / "EXTERNALLY-MANAGED").write_text(EXTERNALLY_MANAGED, encoding="utf-8")
    return removed


_PACKAGES_SCRIPT: Final = (
    "import json, importlib.metadata as m; "
    "print(json.dumps(sorted((d.metadata['Name'], d.version) for d in m.distributions())))"
)


def write_manifest(python: Path, root: Path, spec: Spec, target: Platform) -> dict[str, object]:
    """寫出 rpa-runtime.json：運行環境是什麼、裝了哪些套件（版本）。"""
    env = _clean_env()
    full = _run([python, "-c", "import platform; print(platform.python_version())"], env=env)
    packages = cast("list[list[str]]", json.loads(_run([python, "-c", _PACKAGES_SCRIPT], env=env)))
    manifest: dict[str, object] = {
        "version": spec.version,
        "platform": target.tag,
        "python": full.strip(),
        "packages": dict(packages),
        "commit": commit(),
    }
    (root / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def smoke(python: Path, source: Path = SOURCE) -> None:
    """用建好的直譯器跑 smoke.py：失敗就停止建置。"""
    command = [python, "-E", "-s", "-X", "utf8", source / "smoke.py", "--rpa-script", SCRIPT_SOURCE]
    print(_run(command, env=_clean_env()).rstrip(), flush=True)


def _reset(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def pack(root: Path, archive: Path) -> str:
    """把 root 的內容（最上層就是運行環境的根目錄）打包成 tar.gz，寫出 .sha256，回傳 sha256。"""
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.unlink(missing_ok=True)
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        for path in sorted(root.iterdir()):
            bundle.add(path, arcname=path.name, filter=_reset)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    return digest


def build(tag: str | None = None, out: Path = DIST, source: Path = SOURCE) -> Path:
    """建這台電腦平台的運行環境，回傳壓縮檔。"""
    spec = load_spec(source)
    host = host_platform()
    tag = tag or host
    if tag != host:
        raise SystemExit(f"只能建這台電腦的平台（{host}），不能建 {tag}")
    target = spec.platforms.get(tag)
    if target is None:
        raise SystemExit(f"runtime.toml 沒有平台 {tag}")
    uv = find_uv()
    work = WORK / tag
    root = work / "root"
    python = stage_python(uv, spec, target, root)
    install_packages(uv, python, target, source)
    stdlib, site = stdlib_dir(python), site_dir(python)
    removed = slim(root, stdlib, site)
    print(f"拿掉 {len(removed)} 項：{', '.join(removed[:12])}{' …' if len(removed) > 12 else ''}")
    manifest = write_manifest(python, root, spec, target)
    print(f"運行環境 {spec.version}（{tag}，Python {manifest['python']}）")
    smoke(python, source)
    archive = out / spec.archive_name(tag)
    digest = pack(root, archive)
    size = archive.stat().st_size / 1024 / 1024
    print(f"{archive.name}：{size:.1f} MB，sha256 {digest}")
    return archive


def install(archive: Path) -> str:
    """把壓縮檔解壓到這台電腦的快取（和 Worker 執行時相同的方法），回傳運行環境的資料夾。"""
    from rpa_runner.pyruntime import ENV_ARCHIVES, prepare

    match = re.fullmatch(r"RPA-Python-(\d+)\.\d+\.\d+-.+\.tar\.gz", archive.name)
    if match is None:
        raise SystemExit(f"不是運行環境的壓縮檔：{archive.name}")
    prepared = prepare(match.group(1), environ={**os.environ, ENV_ARCHIVES: str(archive.parent)})
    return str(prepared.root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建置 RPA Python 運行環境（ADR 0020）")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock", help="依 requirements.in 更新 requirements.lock")
    build_parser = commands.add_parser("build", help="建這台電腦平台的運行環境")
    build_parser.add_argument("--platform", help="平台代號（只能是這台電腦的）")
    build_parser.add_argument("--out", type=Path, default=DIST, help="產物放哪裡")
    build_parser.add_argument("--install", action="store_true", help="建好後解壓到本機的快取")
    args = parser.parse_args(argv)
    if args.command == "lock":
        print(f"lock: {lock(find_uv(), load_spec()).relative_to(ROOT).as_posix()}")
        return 0
    archive = build(args.platform, args.out)
    lines = {"archive": archive.as_posix()}
    if args.install:
        lines["installed"] = install(archive)
    for key, value in lines.items():
        print(f"{key}: {value}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in lines.items())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
