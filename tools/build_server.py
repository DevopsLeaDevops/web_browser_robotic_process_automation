"""建置 Linux 伺服器的分發包：自帶 Python、照 uv.lock 裝好套件的 tar.gz。

    python3 tools/build_server.py        # 在 Linux（x86_64 或 aarch64）上，產物在 dist/server/

伺服器（``rpa serve``）以前只能 clone 程式碼再執行 scripts/setup-linux.sh：伺服器要連得到 GitHub
與 PyPI，每次升級都重新下載套件。分發包把這些在 CI 先做好：

1. Python：uv 管理的 CPython（python-build-standalone，``.python-version`` 的版本），整個複製進來。
   它不依賴系統的 Python，可以搬到任何位置；需要 glibc 2.17 以上。
2. 套件：``uv export`` 照 uv.lock 列出 rpa-cli 需要的套件（含 sha256），工作區的套件另外建成
   wheel，都直接裝進這份 Python 的 site-packages。指定 ``manylinux_2_28`` 平台：建置的機器
   （Ubuntu）比較新，不指定的話可能選到公司伺服器（glibc 2.28）載入不了的 wheel；裝好後再逐一
   核對每個 wheel 的平台標籤。
3. ``bin/rpa``（apps/server/packaging/rpa）、``install.sh``（apps/server/packaging/install.sh）、
   第一次啟動時匯入的範例場景（scenarios/demo）、``BUILD_INFO``（版本、提交、架構）。
4. 用包內的 Python 執行 ``rpa --version`` 並載入伺服器的程式，確認能用之後打包成
   ``RPA-Server-<版本>-linux-<x64|arm64>.tar.gz``。

只用標準函式庫，CI 用系統的 python3 執行，不必先 ``uv sync``；需要 PATH 上有 uv。
在哪個架構執行就建哪個架構（要用包內的 Python 編譯 .pyc、做最後的檢查）。
最後印出 ``artifact: …``；在 GitHub Actions 裡同時寫進步驟的輸出。
"""

import argparse
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent
DIST: Final = ROOT / "dist" / "server"
WORK: Final = ROOT / "build" / "server"
PACKAGING: Final = ROOT / "apps" / "server" / "packaging"
EXAMPLES: Final = ROOT / "scenarios" / "demo"

PACKAGES: Final = ("rpa-core", "rpa-runner", "rpa-worker", "rpa-testsite", "rpa-server", "rpa-cli")
"""裝進分發包的工作區套件（rpa-cli 與它的相依）；桌面端（rpa-desktop）不裝。"""
GLIBC_FLOOR: Final = (2, 28)
"""公司伺服器的下限（README、scripts/setup-linux.sh 的檢查）。"""


@dataclass(frozen=True, slots=True)
class Target:
    machine: str
    """``uname -m``：x86_64、aarch64。"""
    label: str
    """檔名裡的架構：x64、arm64（和桌面端的檔名一致）。"""

    @property
    def platform(self) -> str:
        """``uv pip install --python-platform``：選 glibc 2.28 載入得了的 wheel。"""
        return f"{self.machine}-manylinux_{GLIBC_FLOOR[0]}_{GLIBC_FLOOR[1]}"

    def python(self, version: str) -> str:
        """uv 的 Python 下載代號（python-build-standalone 的 glibc 版本）。"""
        return f"cpython-{version}-linux-{self.machine}-gnu"


TARGETS: Final = {
    "x86_64": Target("x86_64", "x64"),
    "aarch64": Target("aarch64", "arm64"),
}


def host_target(machine: str | None = None) -> Target:
    name = (machine or platform.machine()).lower()
    name = {"amd64": "x86_64", "arm64": "aarch64"}.get(name, name)
    try:
        return TARGETS[name]
    except KeyError:
        raise SystemExit(f"不支援的架構：{name}（只有 x86_64、aarch64）") from None


def package_version() -> str:
    """伺服器的版本（所有套件同一個版本，tools/release_version.py 維護）。"""
    data = tomllib.loads((ROOT / "apps" / "server" / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def python_version() -> str:
    return (ROOT / ".python-version").read_text(encoding="utf-8").strip()


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


def bundle_name(version: str, target: Target) -> str:
    return f"RPA-Server-{version}-linux-{target.label}"


# ---------------------------------------------------------------- wheel 的平台


_MANYLINUX: Final = re.compile(r"manylinux_(\d+)_(\d+)_")
_LEGACY: Final = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}


def tag_glibc(tag: str) -> tuple[int, int] | None:
    """一個 wheel 標籤需要的 glibc；不限 glibc（純 Python、其他系統）回傳 None。"""
    platform_tag = tag.rsplit("-", 1)[-1]
    found = _MANYLINUX.search(platform_tag + "_")
    if found:
        return int(found.group(1)), int(found.group(2))
    for name, version in _LEGACY.items():
        if platform_tag.startswith(name + "_"):
            return version
    return None


def wheel_glibc(tags: Iterable[str]) -> tuple[int, int] | None:
    """一個 wheel（可能有多個標籤）最少需要的 glibc；任一標籤不限 glibc 就是 None。"""
    needs: list[tuple[int, int]] = []
    for tag in tags:
        need = tag_glibc(tag)
        if need is None:
            return None
        needs.append(need)
    return min(needs) if needs else None


def too_new_wheels(site_packages: Path, floor: tuple[int, int] = GLIBC_FLOOR) -> list[str]:
    """裝好的套件裡，需要比 ``floor`` 新的 glibc 的那些（``名稱：需要 2.x``）。"""
    problems: list[str] = []
    for wheel in sorted(site_packages.glob("*.dist-info/WHEEL")):
        tags = [
            line.split(":", 1)[1].strip()
            for line in wheel.read_text(encoding="utf-8").splitlines()
            if line.startswith("Tag:")
        ]
        need = wheel_glibc(tags)
        if need is not None and need > floor:
            problems.append(f"{wheel.parent.name}：需要 glibc {need[0]}.{need[1]}")
    return problems


# ---------------------------------------------------------------- 建置


def _run(command: Sequence[str | Path], env: Mapping[str, str] | None = None) -> str:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
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


def managed_python(uv: str, key: str) -> Path:
    """下載（已經有就沿用）uv 管理的 Python，回傳它的安裝資料夾（sys.base_prefix）。"""
    _run([uv, "python", "install", key])
    executable = _run([uv, "python", "find", "--managed-python", key]).strip()
    prefix = _run([executable, "-c", "import sys; print(sys.base_prefix)"]).strip()
    return Path(prefix)


def stage_python(source: Path, target: Path) -> Path:
    """複製 Python；回傳包內的 python3。uv 加的 EXTERNALLY-MANAGED 記號拿掉（這份由我們管理）。"""
    shutil.copytree(source, target, symlinks=True)
    for marker in target.glob("lib/python3*/EXTERNALLY-MANAGED"):
        marker.unlink()
    python = target / "bin" / "python3"
    if not python.exists():
        raise SystemExit(f"{source} 裡沒有 bin/python3")
    return python


def install_packages(uv: str, python: Path, target: Target, work: Path) -> None:
    """照 uv.lock 把 rpa-cli 與相依套件裝進包內的 Python。"""
    requirements = work / "requirements.txt"
    _run(
        [
            uv,
            "export",
            "--locked",
            "--package",
            "rpa-cli",
            "--no-default-groups",
            "--no-emit-workspace",
            "--format",
            "requirements.txt",
            "--no-header",
            "--output-file",
            requirements,
        ]
    )
    wheels = work / "wheels"
    shutil.rmtree(wheels, ignore_errors=True)
    for package in PACKAGES:
        _run([uv, "build", "--wheel", "--package", package, "--out-dir", wheels])
    common: list[str | Path] = [
        uv,
        "pip",
        "install",
        "--python",
        python,
        "--break-system-packages",
        "--python-platform",
        target.platform,
        "--link-mode",
        "copy",
        "--compile-bytecode",
        "--no-deps",
    ]
    _run([*common, "--require-hashes", "-r", requirements])
    _run([*common, *sorted(wheels.glob("*.whl"))])


def site_packages(python: Path) -> Path:
    return Path(
        _run([python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"]).strip()
    )


def remove_scripts(bin_dir: Path, keep: set[str]) -> list[str]:
    """套件安裝時產生的命令（console_scripts）寫死了建置時的路徑，搬家後不能用：刪掉。"""
    removed: list[str] = []
    for entry in sorted(bin_dir.iterdir()):
        if entry.name not in keep:
            entry.unlink()
            removed.append(entry.name)
    return removed


def build_info_text(*, version: str, commit_id: str, target: Target, python: str) -> str:
    """BUILD_INFO：一行一個 KEY=值（install.sh 逐行讀取，不當成腳本執行）。"""
    built_at = datetime.now(UTC).isoformat(timespec="seconds")
    lines = {
        "app": "server",
        "version": version,
        "commit": commit_id,
        "arch": target.machine,
        "python": python,
        "glibc": f"{GLIBC_FLOOR[0]}.{GLIBC_FLOOR[1]}",
        "built_at": built_at,
    }
    return "".join(f"{key}={value}\n" for key, value in lines.items())


def _executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _check(bundle: Path) -> str:
    """用包內的 Python 執行 rpa --version、載入伺服器的程式；回傳版本那一行。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}
    output = _run([bundle / "bin" / "rpa", "--version"], env=env).strip()
    _run(
        [
            bundle / "python" / "bin" / "python3",
            "-c",
            "import sqlite3, ssl; from rpa_server.app import create_app; "
            "from rpa_server.config import Settings",
        ],
        env=env,
    )
    return output


def build(target: Target | None = None) -> Path:
    """建置這台電腦架構的分發包，回傳 tar.gz 的路徑。"""
    if sys.platform != "linux":
        raise SystemExit("伺服器的分發包要在 Linux 上建置")
    target = host_target() if target is None else target
    uv = find_uv()
    version = package_version()
    name = bundle_name(version, target)
    work = WORK / target.label
    bundle = work / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    python_key = target.python(python_version())
    python = stage_python(managed_python(uv, python_key), bundle / "python")
    keep = {entry.name for entry in (bundle / "python" / "bin").iterdir()}
    install_packages(uv, python, target, work)
    removed = remove_scripts(bundle / "python" / "bin", keep)
    if removed:
        print(f"刪掉寫死建置路徑的命令：{', '.join(removed)}")
    problems = too_new_wheels(site_packages(python))
    if problems:
        raise SystemExit("這些套件需要比 glibc 2.28 新的系統：\n" + "\n".join(problems))
    full_version = _run([python, "-c", "import platform; print(platform.python_version())"])

    (bundle / "bin").mkdir()
    shutil.copy2(PACKAGING / "rpa", bundle / "bin" / "rpa")
    shutil.copy2(PACKAGING / "install.sh", bundle / "install.sh")
    for script in (bundle / "bin" / "rpa", bundle / "install.sh"):
        _executable(script)
    shutil.copytree(EXAMPLES, bundle / "scenarios" / "demo")
    (bundle / "BUILD_INFO").write_text(
        build_info_text(
            version=version, commit_id=commit(), target=target, python=full_version.strip()
        ),
        encoding="utf-8",
    )
    print(f"檢查：{_check(bundle)}")

    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / f"{name}.tar.gz"
    archive.unlink(missing_ok=True)
    _run(
        [
            "tar",
            "--owner=0",
            "--group=0",
            "--numeric-owner",
            "-C",
            work,
            "-czf",
            archive,
            name,
        ]
    )
    return archive


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建置 Linux 伺服器的分發包（這台電腦的架構）")
    parser.parse_args(argv)
    archive = build()
    size = archive.stat().st_size / 1024 / 1024
    print(f"artifact: {archive.as_posix()}")
    print(f"大小：{size:.1f} MB")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"artifact={archive.as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
