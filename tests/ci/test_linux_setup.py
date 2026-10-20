"""Linux 安裝的發行版辨識、失敗邊界與重跑；真實 RPM 套件安裝由 CI 驗證。"""

import hashlib
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


@pytest.mark.parametrize(
    "args", ["--dir", "--dir=", "--dir --install-service", "--unknown", "--mirror", "--mirror="]
)
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
    # 測試網站：預設空白（不啟動）；設成 0.0.0.0 時對其他電腦開放；舊的設定檔沒有這一行也照舊
    env_file = repo / ".rpa-server.env"
    settings = env_file.read_text()
    assert "export RPA_TESTSITE_HOST=''\n" in settings
    for line, expected in (
        ("export RPA_TESTSITE_HOST=0.0.0.0\n", ["--testsite-host", "0.0.0.0"]),
        ("", ["--no-testsite"]),
    ):
        env_file.write_text(settings.replace("export RPA_TESTSITE_HOST=''\n", line))
        relaunch = subprocess.run(
            [str(binaries / "rpa-server")], text=True, capture_output=True, timeout=10, check=False
        )
        assert relaunch.returncode == 0, relaunch.stderr
        assert relaunch.stdout.splitlines()[-len(expected) :] == expected
        assert "--no-local-worker" in relaunch.stdout.splitlines()
    env_file.write_text(settings)
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


# ---------------------------------------------------------------- 套件來源

WHEEL = b"wheel-bytes"
LOCK = (
    'version = 1\n\n[[package]]\nname = "pygments"\nversion = "2.21.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
    "wheels = [\n"
    '    { url = "https://files.pythonhosted.org/packages/71/46/aa/pygments-2.21.0-py3-none-any.whl"'
    f', hash = "sha256:{hashlib.sha256(WHEEL).hexdigest()}", size = 1250147'
    ', upload-time = "2026-01-01T00:00:00Z" },\n]\n'
)
# 假的 curl：依網址決定下載到的內容與速度；ustc 最快但內容不符，tencent、huawei 連不上
FAKE_CURL = (
    'curl() { local out="" url=""; while [ $# -gt 0 ]; do case "$1" in '
    '-o|-w|--connect-timeout|--max-time) [ "$1" = -o ] && out="$2"; shift 2 ;; '
    '-*) shift ;; *) url="$1"; shift ;; esac; done; '
    'printf "%s\\n" "$url" >> "$CURL_LOG"; case "$url" in '
    '*tuna*) printf wheel-bytes > "$out"; printf 900000.000 ;; '
    '*aliyun*) printf wheel-bytes > "$out"; printf 300000 ;; '
    '*ustc*) printf tampered > "$out"; printf 5000000 ;; '
    '*pythonhosted*) printf wheel-bytes > "$out"; printf 100000 ;; '
    "*) return 7 ;; esac; }; "
)


def runtime_project(tmp: Path) -> None:
    """install_runtime 需要的專案：pyproject、uv.lock、裝好之後要能執行的 .venv-server。"""
    (tmp / "pyproject.toml").write_text('[tool.uv]\nrequired-version = ">=0.11"\n')
    (tmp / "uv.lock").write_text(LOCK, encoding="utf-8")
    binaries = tmp / ".venv-server/bin"
    binaries.mkdir(parents=True)
    for name in ("python", "rpa"):
        path = binaries / name
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)


# 假的 uv：記下參數、看到的 uv.lock 與 UV_INDEX_URL；FAIL_MIRROR=1 時用鏡像的那次失敗
FAKE_UV = (
    'fake_uv() { if [ "$1" = --version ]; then echo "uv 0.12.24"; return; fi; '
    'printf "%s\\n" "$@" "index=${UV_INDEX_URL:-unset}" >> "$UV_ARGS"; '
    'cp uv.lock "$LOCK_SEEN.$#"; '
    'case " $* " in *" --default-index "*) [ "${FAIL_MIRROR:-0}" = 1 ] && return 1 ;; esac; '
    'return 0; }; find_uv() { UV=fake_uv; }; REPO_DIR="$PWD"; '
)


def test_auto_picks_the_fastest_mirror_with_the_right_content(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(LOCK, encoding="utf-8")
    log = tmp_path / "curl.log"
    result = shell(
        FAKE_CURL + 'CURL_LOG="$1"; choose_mirror; echo "CHOSEN $MIRROR_NAME $MIRROR_SIMPLE"',
        str(log),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "CHOSEN tuna https://pypi.tuna.tsinghua.edu.cn/simple" in result.stdout
    assert "ustc     無法使用" in result.stderr  # 最快但內容不符：不用
    assert "huawei   無法使用" in result.stderr
    assert "tuna          878 KB/s" in result.stderr
    urls = log.read_text(encoding="utf-8").splitlines()
    assert (
        "https://pypi.tuna.tsinghua.edu.cn/packages/71/46/aa/pygments-2.21.0-py3-none-any.whl"
        in urls
    )
    assert len(urls) == 6  # 每個內建來源各下載一次


def test_without_a_probe_file_auto_uses_pypi(tmp_path: Path) -> None:
    result = shell('curl() { exit 99; }; choose_mirror; echo "CHOSEN $MIRROR_NAME"', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "CHOSEN pypi" in result.stdout


def test_mirror_install_rewrites_the_lock_only_while_syncing(tmp_path: Path) -> None:
    runtime_project(tmp_path)
    result = shell(
        FAKE_UV + 'UV_ARGS="$1"; LOCK_SEEN="$2"; UV_INDEX_URL=https://ignored/simple; '
        "MIRROR=tuna; install_runtime",
        str(tmp_path / "args"),
        str(tmp_path / "seen"),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    args = (tmp_path / "args").read_text(encoding="utf-8")
    assert "sync\n--locked\n--default-index\nhttps://pypi.tuna.tsinghua.edu.cn/simple\n" in args
    assert "--package\nrpa-cli\n--no-default-groups\n--managed-python\nindex=unset\n" in args
    seen = next(tmp_path.glob("seen.*")).read_text(encoding="utf-8")
    assert 'registry = "https://pypi.tuna.tsinghua.edu.cn/simple"' in seen
    assert "https://pypi.tuna.tsinghua.edu.cn/packages/71/46/aa/pygments" in seen
    assert "pythonhosted" not in seen
    assert seen.replace("pypi.tuna.tsinghua.edu.cn/packages", "x") == LOCK.replace(
        "files.pythonhosted.org/packages", "x"
    ).replace("pypi.org/simple", "pypi.tuna.tsinghua.edu.cn/simple")  # 只換網址
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == LOCK  # 裝完還原


def test_a_failing_mirror_falls_back_to_pypi(tmp_path: Path) -> None:
    runtime_project(tmp_path)
    result = shell(
        FAKE_UV + 'UV_ARGS="$1"; LOCK_SEEN="$2"; FAIL_MIRROR=1; MIRROR=aliyun; install_runtime',
        str(tmp_path / "args"),
        str(tmp_path / "seen"),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "從 aliyun 安裝失敗，改用 PyPI 再試一次" in result.stdout
    assert "安裝失敗（第" not in result.stderr
    calls = (tmp_path / "args").read_text(encoding="utf-8").split("sync\n")[1:]
    assert len(calls) == 2
    assert calls[1].startswith("--locked\n--package\nrpa-cli\n")
    # 假的 uv 用參數個數區分兩次：鏡像那次多了 --default-index 與網址
    assert "https://mirrors.aliyun.com/pypi/packages/" in (tmp_path / "seen.8").read_text()
    assert (tmp_path / "seen.6").read_text(encoding="utf-8") == LOCK  # PyPI 重試用原本的鎖檔
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == LOCK


def test_company_index_url_is_used_without_probing(tmp_path: Path) -> None:
    runtime_project(tmp_path)
    result = shell(
        FAKE_UV + 'curl() { exit 99; }; UV_ARGS="$1"; LOCK_SEEN="$2"; '
        "UV_INDEX_URL=https://nexus.example/repository/pypi/simple/; install_runtime",
        str(tmp_path / "args"),
        str(tmp_path / "seen"),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    args = (tmp_path / "args").read_text(encoding="utf-8")
    assert "--default-index\nhttps://nexus.example/repository/pypi/simple\n" in args
    assert "index=unset" in args
    seen = next(tmp_path.glob("seen.*")).read_text(encoding="utf-8")
    assert "https://nexus.example/repository/pypi/packages/71/46/aa/" in seen


@pytest.mark.parametrize(
    "value", ["nope", "ftp://mirror/simple", "https://mirror/simple#x", "https://a b/simple"]
)
def test_unknown_mirror_stops(value: str) -> None:
    result = shell('MIRROR="$1"; choose_mirror', value)
    assert result.returncode != 0
    assert "套件來源" in result.stderr


def test_lock_is_restored_when_the_install_is_interrupted(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(LOCK, encoding="utf-8")
    result = shell(
        "MIRROR_SIMPLE=https://m/simple; MIRROR_FILES=https://m/; use_mirror_lock; "
        "grep -q https://m/packages uv.lock; exit 3",
        cwd=tmp_path,
    )
    assert result.returncode == 3, result.stderr
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == LOCK
