"""Linux 安裝的發行版辨識、失敗邊界與重跑；真實 RPM 套件安裝由 CI 驗證。"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/setup-linux.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(os.name == "nt" or BASH is None, reason="需要 POSIX Bash")


def shell(
    code: str, *args: str, cwd: Path | None = None, script: Path = SCRIPT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH or "bash", "-c", 'source "$1"; shift; ' + code, "test", str(script), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("release", "arch", "libc", "success"),
    [
        ('ID=""\nID_LIKE="rhel fedora centos "\nVERSION_ID="3"', "x86_64", "glibc 2.32", True),
        ('ID="centos"', "x86_64", "glibc 2.28", True),
        ('ID="rocky"\nID_LIKE="rhel centos fedora"', "aarch64", "glibc 2.34", True),
        ('ID="centos"', "x86_64", "glibc 2.17", False),
        ('ID="centos"', "i686", "glibc 2.32", False),
        ('ID="centos"', "x86_64", "musl 1.2.5", False),
        ('ID="centos"', "x86_64", "", False),
        ('ID="debian"', "x86_64", "glibc 2.36", False),
        ('ID="not-centos"', "x86_64", "glibc 2.32", False),
    ],
)
def test_system_detection(
    tmp_path: Path, release: str, arch: str, libc: str, success: bool
) -> None:
    path = tmp_path / "os-release"
    path.write_text(release + "\n", encoding="utf-8")
    result = shell(
        'uname() { if [ "$1" = -s ]; then echo Linux; else echo "$ARCH"; fi; }; '
        'getconf() { echo "$LIBC"; }; yum() { :; }; dnf() { :; }; '
        'ARCH="$2"; LIBC="$3"; check_system "$1"; test "$PACKAGE_MANAGER" = yum',
        str(path),
        arch,
        libc,
    )
    assert (result.returncode == 0) == success, result.stdout + result.stderr


@pytest.mark.parametrize("args", ["--dir", "--dir=", "--dir --install-service", "--unknown"])
def test_bad_options_stop_before_install(args: str) -> None:
    result = shell("parse_args " + args)
    assert result.returncode != 0
    assert "錯誤" in result.stderr


def test_dnf_fallback_and_no_privilege_install(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text('ID="fedora"\n', encoding="utf-8")
    result = shell(
        'uname() { if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi; }; '
        'getconf() { echo "glibc 2.32"; }; dnf() { :; }; '
        # 不依賴執行測試的主機是否裝了 yum。
        'command() { if [ "${2:-}" = yum ]; then return 1; else builtin command "$@"; fi; }; '
        'check_system "$1"; test "$PACKAGE_MANAGER" = dnf; '
        "as_root() { exit 99; }; SKIP_SYSTEM_PACKAGES=1; install_system_packages",
        str(release),
    )
    assert result.returncode == 0, result.stderr


def test_running_service_stops_install() -> None:
    result = shell("systemctl() { return 0; }; check_service; echo UNEXPECTED")
    assert result.returncode != 0
    assert "正在執行" in result.stderr
    assert "UNEXPECTED" not in result.stdout


def test_service_requires_running_systemd() -> None:
    result = shell("systemctl() { return 1; }; INSTALL_SERVICE=1; check_service")
    assert result.returncode != 0
    assert "沒有可用的 systemd" in result.stderr


def test_yum_packages_and_failures() -> None:
    result = shell(
        'as_root() { printf "%s\\n" "$@"; }; PACKAGE_MANAGER=yum; install_system_packages'
    )
    assert result.returncode == 0
    assert (
        "yum\ninstall\n-y\ngit\ncurl\nca-certificates\ntar\ngzip\nlibstdc++\nlibgcc"
        in result.stdout
    )
    failure = shell(
        "as_root() { return 42; }; PACKAGE_MANAGER=yum; install_system_packages; echo DONE"
    )
    assert failure.returncode == 42
    assert "DONE" not in failure.stdout


def test_locked_server_runtime(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.uv]\nrequired-version = ">=0.11"\n')
    binaries = tmp_path / ".venv-server/bin"
    binaries.mkdir(parents=True)
    for name in ("python", "rpa"):
        path = binaries / name
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    result = shell(
        'fake_uv() { if [ "$1" = --version ]; then echo "uv 0.12.24"; '
        'else printf "%s\\n" "$UV_PROJECT_ENVIRONMENT" "$@"; fi; }; '
        'find_uv() { UV=fake_uv; }; REPO_DIR="$PWD"; install_runtime',
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert f"{tmp_path}/.venv-server\nsync\n--locked\n--package\nrpa-cli\n" in result.stdout
    assert "--no-default-groups\n--managed-python" in result.stdout
    old = shell(
        'fake_uv() { echo "uv 0.7.6"; }; find_uv() { UV=fake_uv; }; install_runtime', cwd=tmp_path
    )
    assert old.returncode != 0
    assert "太舊" in old.stderr


def test_launchers_preserve_config_and_quote_paths(tmp_path: Path) -> None:
    installer = tmp_path / "setup-linux.sh"
    shutil.copyfile(SCRIPT, installer)
    repo = tmp_path / 'repo space $value %n "quote"'
    binaries = repo / ".venv-server/bin"
    binaries.mkdir(parents=True)
    data = tmp_path / "persistent data"
    data.mkdir()
    marker = data / "keep.txt"
    marker.write_text("keep")
    (repo / "uv.lock").touch()
    (repo / "apps/cli").mkdir(parents=True)
    (repo / "apps/cli/pyproject.toml").touch()
    result = shell(
        'TARGET_DIR="$1"; cd /; prepare_code; '
        'RPA_DATA_DIR="$2"; RPA_PORT=18080; RPA_WORKER_PORT=18081; write_launchers; '
        "cp .rpa-server.env original.env; "
        "RPA_DATA_DIR=/should-not-be-used; RPA_PORT=1; write_launchers; "
        "cmp .rpa-server.env original.env",
        str(repo),
        str(data),
        script=installer,
    )
    assert result.returncode == 0, result.stderr
    assert (repo / ".rpa-server.env").stat().st_mode & 0o777 == 0o600
    fake_rpa = binaries / "rpa"
    fake_rpa.write_text('#!/bin/bash\nprintf "%s\\n" "$RPA_DATA_DIR" "$@"\n')
    fake_rpa.chmod(0o755)
    launch = subprocess.run(
        [str(binaries / "rpa-server")], text=True, capture_output=True, timeout=10, check=False
    )
    assert launch.returncode == 0, launch.stderr
    assert launch.stdout.splitlines() == [
        str(data),
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "18080",
        "--data",
        str(data),
        "--worker-host",
        "0.0.0.0",
        "--worker-port",
        "18081",
        "--no-local-worker",
        "--no-testsite",
    ]
    assert marker.read_text() == "keep"
    unit = (repo / ".venv-server/rpa-server.service").read_text()
    assert 'repo space $$value %%n \\"quote\\"/.venv-server/bin/rpa-server"' in unit
    assert "UMask=0077" in unit
    service = shell(
        'REPO_DIR="$PWD"; INSTALL_SERVICE=1; as_root() { printf "%s\\n" "$@"; }; write_launchers',
        cwd=repo,
    )
    assert service.returncode == 0, service.stderr
    assert (
        "systemctl\ndaemon-reload\nsystemctl\nenable\n--now\nrpa-server.service" in service.stdout
    )


def test_sync_failure_stops_before_writing_launchers(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.uv]\nrequired-version = ">=0.11"\n')
    result = shell(
        'fake_uv() { if [ "$1" = --version ]; then echo "uv 0.12.24"; else return 19; fi; }; '
        'find_uv() { UV=fake_uv; }; REPO_DIR="$PWD"; install_runtime; write_launchers',
        cwd=tmp_path,
    )
    assert result.returncode == 19
    assert not (tmp_path / ".rpa-server.env").exists()
