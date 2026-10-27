"""Linux 伺服器的分發包：包內的 install.sh、bin/rpa 與建置工具（tools/build_server.py）。

install.sh 用假的分發包（python3、rpa 都是小腳本）測安裝、重裝、升級、保留舊版本、
執行環境的共用（runtimes/）、沿用 clone 安裝的設定與 systemd 服務的分支；bin/rpa 測程式碼層的
路徑與 serve 的重新啟動、退回（ADR 0018）。真正的分發包在 Rocky 8 容器裡的安裝、啟動與用更新檔
升級由 CI（server-package.yml）驗證。
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools import build_server

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "apps" / "server" / "packaging" / "install.sh"
WRAPPER = ROOT / "apps" / "server" / "packaging" / "rpa"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(os.name == "nt" or BASH is None, reason="需要 POSIX Bash")

RHEL = (
    'NAME="Rocky Linux"\nVERSION="8.10 (Green Obsidian)"\nID="rocky"\n'
    'ID_LIKE="rhel centos fedora"\n'
)
COMPANY = (
    'NAME=""\nVERSION=""\nID=""\nID_LIKE="rhel fedora centos "\nVERSION_ID="3"\nPRETTY_NAME=""\n'
)
# 安裝器只支援 Linux。macOS 的合成測試用 BSD mv -h 表達 GNU mv -T 的
# 「替換連結本身」語意，仍實際搬移檔案；Linux CI 繼續直接驗證原生 GNU mv。
HOST_TOOLS = (
    'mv() { if [ "$1" = -Tf ]; then shift; command mv -hf "$@"; else command mv "$@"; fi; }; '
    if sys.platform == "darwin"
    else ""
)
STUBS = (
    'uname() { if [ "$1" = -s ]; then echo Linux; else echo "${FAKE_ARCH:-x86_64}"; fi; }; '
    'getconf() { echo "${FAKE_LIBC:-glibc 2.32}"; }; '
    "has_libstdcxx() { return 0; }; has_systemd() { return 1; }; "
) + HOST_TOOLS


RUNTIME = "0123456789abcdef"


def make_bundle(
    folder: Path,
    *,
    version: str = "0.4.0",
    commit: str = "abc1234",
    arch: str = "x86_64",
    runtime: str = RUNTIME,
) -> Path:
    """假的分發包：bin/rpa 把工作目錄與參數寫到 $RPA_TEST_LOG，python3 什麼都不做。"""
    bundle = folder / f"RPA-Server-{version}-{commit}"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "python" / "bin").mkdir(parents=True)
    (bundle / "app" / "rpa_cli").mkdir(parents=True)
    (bundle / "scenarios" / "demo").mkdir(parents=True)
    rpa = bundle / "bin" / "rpa"
    rpa.write_text(
        '#!/usr/bin/env bash\nif [ -n "${RPA_TEST_LOG:-}" ]; then '
        'printf "%s\\n" "$PWD" "$@" > "$RPA_TEST_LOG"; fi\necho "rpa 0.4.0"\n',
        encoding="utf-8",
    )
    python = bundle / "python" / "bin" / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for script in (rpa, python):
        script.chmod(0o755)
    shutil.copy2(INSTALL, bundle / "install.sh")
    (bundle / "BUILD_INFO").write_text(
        f"app=server\nversion={version}\ncommit={commit}\narch={arch}\npython=3.13.9\n"
        f"runtime={runtime}\n",
        encoding="utf-8",
    )
    return bundle


def run(
    code: str,
    *args: str,
    bundle: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """載入 install.sh 的函式（加上替身）後執行 ``code``；``$1`` 起是 ``args``。"""
    script = INSTALL if bundle is None else bundle / "install.sh"
    environ = {key: value for key, value in os.environ.items() if not key.startswith("RPA_")}
    if home is not None:
        environ["HOME"] = str(home)
    environ.update(env or {})
    return subprocess.run(
        [BASH or "bash", "-c", 'source "$1"; shift; ' + STUBS + code, "test", str(script), *args],
        env=environ,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def install(
    tmp_path: Path, bundle: Path, *options: str, before: str = "", env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    release = tmp_path / "os-release"
    if not release.exists():
        release.write_text(RHEL, encoding="utf-8")
    code = (
        f'OS_RELEASE="{release}"; UNIT_PATH="{tmp_path}/unit/rpa-server.service"; '
        f'LEGACY_DIR="{tmp_path}/legacy"; git() {{ :; }}; {before} main "$@"'
    )
    return run(code, *options, bundle=bundle, env=env, home=tmp_path / "home")


def ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


# ---------------------------------------------------------------- 系統與分發包的辨識


def test_build_info_and_os_release_do_not_mix(tmp_path: Path) -> None:
    """os-release 也有 VERSION：不能蓋掉分發包的版本。"""
    bundle = make_bundle(tmp_path)
    release = tmp_path / "os-release"
    release.write_text(RHEL, encoding="utf-8")
    result = run(
        'OS_RELEASE="$1"; read_bundle "$2"; check_system; '
        'printf "%s|%s|%s|%s\\n" "$VERSION" "$COMMIT" "$ARCH" "$RELEASE"',
        str(release),
        str(bundle),
    )
    assert ok(result).splitlines()[-1] == "0.4.0|abc1234|x86_64|0.4.0-abc1234"


@pytest.mark.parametrize(
    ("release", "arch", "libc", "success"),
    [
        (COMPANY, "x86_64", "glibc 2.32", True),
        (RHEL, "x86_64", "glibc 2.28", True),
        (RHEL, "aarch64", "glibc 2.28", False),  # 分發包是 x86_64
        (RHEL, "x86_64", "glibc 2.17", False),
        (RHEL, "x86_64", "musl 1.2.5", False),
        ('ID="debian"\n', "x86_64", "glibc 2.36", False),
    ],
)
def test_system_detection(
    tmp_path: Path, release: str, arch: str, libc: str, success: bool
) -> None:
    bundle = make_bundle(tmp_path)
    path = tmp_path / "os-release"
    path.write_text(release, encoding="utf-8")
    result = run(
        'OS_RELEASE="$1"; read_bundle "$2"; check_system',
        str(path),
        str(bundle),
        env={"FAKE_ARCH": arch, "FAKE_LIBC": libc},
    )
    assert (result.returncode == 0) == success, result.stdout + result.stderr


@pytest.mark.parametrize(
    "build_info",
    [
        f"version=0.4\ncommit=abc\narch=x86_64\nruntime={RUNTIME}\n",
        f"version=0.4.0\ncommit=ABC;rm\narch=x86_64\nruntime={RUNTIME}\n",
        f"version=0.4.0\ncommit=abc\narch=i686\nruntime={RUNTIME}\n",
        # 0.5.0 以前的分發包沒有環境代號（也沒有 app/）
        "version=0.4.0\ncommit=abc\narch=x86_64\n",
        "version=0.4.0\ncommit=abc\narch=x86_64\nruntime=../evil\n",
    ],
)
def test_bad_build_info_stops(tmp_path: Path, build_info: str) -> None:
    bundle = make_bundle(tmp_path)
    (bundle / "BUILD_INFO").write_text(build_info, encoding="utf-8")
    result = run('read_bundle "$1"', str(bundle))
    assert result.returncode != 0
    assert "BUILD_INFO" in result.stderr


@pytest.mark.parametrize("missing", ["python", "app"])
def test_incomplete_bundle_stops(tmp_path: Path, missing: str) -> None:
    bundle = make_bundle(tmp_path)
    shutil.rmtree(bundle / missing)
    result = run('read_bundle "$1"', str(bundle))
    assert result.returncode != 0
    assert "不是完整的" in result.stderr


@pytest.mark.parametrize(
    "args", ["--prefix", "--prefix=", "--keep", "--keep=1", "--keep x", "--import-env", "--nope"]
)
def test_bad_options(args: str) -> None:
    result = run("parse_args " + args)
    assert result.returncode != 0
    assert "錯誤" in result.stderr


def test_relative_prefix_becomes_absolute(tmp_path: Path) -> None:
    result = run('cd "$1"; parse_args --prefix srv/; echo "$PREFIX"', str(tmp_path))
    assert ok(result).splitlines()[-1] == f"{tmp_path}/srv"


# ---------------------------------------------------------------- 系統套件


def test_only_missing_packages_are_installed() -> None:
    result = run(
        'has_libstdcxx() { return 1; }; command() { if [ "${2:-}" = git ]; then return 1; '
        'else builtin command "$@"; fi; }; as_root() { echo "ROOT $*"; }; '
        "PACKAGE_MANAGER=yum; install_system_packages"
    )
    assert "ROOT yum install -y libstdc++ git" in ok(result)


def test_nothing_missing_needs_no_sudo() -> None:
    result = run("as_root() { exit 99; }; PACKAGE_MANAGER=yum; install_system_packages")
    ok(result)


def test_skip_packages_without_git_only_warns() -> None:
    result = run(
        'command() { if [ "${2:-}" = git ]; then return 1; else builtin command "$@"; fi; }; '
        "as_root() { exit 99; }; SKIP_SYSTEM_PACKAGES=1; install_system_packages"
    )
    assert "git 同步" in ok(result)


def test_skip_packages_without_libstdcxx_stops() -> None:
    result = run(
        "has_libstdcxx() { return 1; }; as_root() { exit 99; }; "
        "SKIP_SYSTEM_PACKAGES=1; install_system_packages"
    )
    assert result.returncode == 1
    assert "libstdc++" in result.stderr


# ---------------------------------------------------------------- 安裝、重裝、升級


def test_first_install_layout_and_launcher(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "download")
    prefix = tmp_path / "srv"
    data = tmp_path / "data dir"
    output = ok(install(tmp_path, bundle, "--prefix", str(prefix), env={"RPA_DATA_DIR": str(data)}))
    assert (prefix / "current").is_symlink()
    assert (prefix / "current").readlink().as_posix() == "releases/0.4.0-abc1234"
    release = prefix / "releases" / "0.4.0-abc1234"
    assert (release / "BUILD_INFO").is_file()
    assert (release / "app" / "rpa_cli").is_dir()
    # Python 與第三方套件放在 runtimes/，版本資料夾只有連結
    assert (release / "python").readlink().as_posix() == f"../../runtimes/{RUNTIME}/python"
    assert (prefix / "runtimes" / RUNTIME / "python" / "bin" / "python3").is_file()
    assert not (prefix / "run" / "update.state").exists()  # 第一次安裝沒有上一版可退
    assert (bundle / "BUILD_INFO").is_file()  # 下載的資料夾原樣保留
    env_file = prefix / "rpa-server.env"
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    assert "export RPA_DATA_DIR=" + str(data).replace(" ", "\\ ") in env_file.read_text("utf-8")
    assert "背景服務：未安裝" in output

    # 啟動器：在安裝位置（不停在版本資料夾裡）、以設定檔的埠號與資料目錄執行 rpa serve
    log = tmp_path / "args.txt"
    started = subprocess.run(
        [str(prefix / "bin" / "rpa-server")],
        env={**os.environ, "RPA_TEST_LOG": str(log)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert started.returncode == 0, started.stderr
    cwd, *args = log.read_text("utf-8").splitlines()
    assert Path(cwd).resolve() == prefix.resolve()
    assert args[:3] == ["serve", "--host", "127.0.0.1"]
    assert args[args.index("--port") + 1] == "8080"
    assert args[args.index("--data") + 1] == str(data)
    assert "--no-local-worker" in args
    assert "--no-testsite" in args
    assert data.is_dir()

    unit = (prefix / "rpa-server.service").read_text("utf-8")
    assert f'ExecStart=/bin/bash "{prefix}/bin/rpa-server"' in unit
    assert "User=" in unit
    assert "Restart=on-failure" in unit


def test_reinstall_keeps_settings_and_upgrade_switches(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    first = make_bundle(tmp_path / "a", commit="aaaaaaa")
    ok(install(tmp_path, first, "--prefix", str(prefix)))
    env_file = prefix / "rpa-server.env"
    with env_file.open("a", encoding="utf-8") as handle:
        handle.write("# retain this setting\n")
    before = env_file.read_text("utf-8")

    # 同一個分發包再裝一次：沿用版本資料夾、設定不變
    assert "已經裝過" in ok(install(tmp_path, first, "--prefix", str(prefix)))
    assert env_file.read_text("utf-8") == before

    # 新的版本：current 換過去，舊版本保留；記下上一版（起不來時 bin/rpa 退回），請伺服器重新啟動
    second = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    output = ok(install(tmp_path, second, "--prefix", str(prefix)))
    assert (prefix / "current").readlink().as_posix() == "releases/0.4.1-bbbbbbb"
    assert (prefix / "releases" / "0.4.0-aaaaaaa").is_dir()
    assert env_file.read_text("utf-8") == before
    state = (prefix / "run" / "update.state").read_text("utf-8")
    assert state == "target=0.4.1-bbbbbbb\nprevious=0.4.0-aaaaaaa\n"
    request = (prefix / "run" / "restart.request").read_text("utf-8")
    assert request == "target=0.4.1-bbbbbbb\n"
    assert "自己換成新版本" in output
    # 執行環境相同：共用同一份
    assert [path.name for path in (prefix / "runtimes").iterdir()] == [RUNTIME]


def test_runtimes_are_shared_and_pruned_with_their_releases(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    old = "1" * 16
    new = "2" * 16
    ok(
        install(
            tmp_path,
            make_bundle(tmp_path / "a", commit="aaaaaaa", runtime=old),
            "--prefix",
            str(prefix),
        )
    )
    for number, commit in enumerate(("bbbbbbb", "ccccccc", "ddddddd"), start=1):
        bundle = make_bundle(tmp_path / commit, version=f"0.4.{number}", commit=commit, runtime=new)
        ok(install(tmp_path, bundle, "--prefix", str(prefix), "--keep", "2"))
        runtimes = sorted(path.name for path in (prefix / "runtimes").iterdir())
        # 用舊環境的版本還在（上一版、保留數量內）時，舊環境也留著
        assert runtimes == ([old, new] if number == 1 else [new])


def test_broken_runtime_is_replaced(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    bundle = make_bundle(tmp_path / "a", commit="aaaaaaa")
    ok(install(tmp_path, bundle, "--prefix", str(prefix)))
    python = prefix / "runtimes" / RUNTIME / "python" / "bin" / "python3"
    python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    second = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    ok(install(tmp_path, second, "--prefix", str(prefix)))
    assert python.read_text("utf-8") == "#!/usr/bin/env bash\nexit 0\n"


def test_old_releases_are_pruned_but_current_and_previous_stay(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    for number, commit in enumerate(("1111111", "2222222", "3333333", "4444444", "5555555")):
        bundle = make_bundle(tmp_path / commit, version=f"0.4.{number}", commit=commit)
        ok(install(tmp_path, bundle, "--prefix", str(prefix)))
    names = sorted(path.name for path in (prefix / "releases").iterdir())
    assert names == ["0.4.2-3333333", "0.4.3-4444444", "0.4.4-5555555"]

    # 退回較舊的一版再裝新版：使用中與上一版都留著
    ok(
        install(
            tmp_path, tmp_path / "3333333" / "RPA-Server-0.4.2-3333333", "--prefix", str(prefix)
        )
    )
    assert (prefix / "current").readlink().as_posix() == "releases/0.4.2-3333333"
    six = make_bundle(tmp_path / "6", version="0.4.5", commit="6666666")
    ok(install(tmp_path, six, "--prefix", str(prefix), "--keep", "2"))
    names = sorted(path.name for path in (prefix / "releases").iterdir())
    assert names == ["0.4.2-3333333", "0.4.5-6666666"]


def test_broken_release_does_not_switch_current(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    ok(install(tmp_path, make_bundle(tmp_path / "a", commit="aaaaaaa"), "--prefix", str(prefix)))
    broken = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    (broken / "bin" / "rpa").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    result = install(tmp_path, broken, "--prefix", str(prefix))
    assert result.returncode != 0
    assert "無法執行" in result.stderr
    assert (prefix / "current").readlink().as_posix() == "releases/0.4.0-aaaaaaa"
    assert not (prefix / "releases" / "0.4.1-bbbbbbb").exists()
    assert not [path for path in (prefix / "releases").iterdir() if path.name.startswith(".")]


def test_broken_python_in_a_new_runtime_does_not_switch_current(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    ok(install(tmp_path, make_bundle(tmp_path / "a", commit="aaaaaaa"), "--prefix", str(prefix)))
    broken = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb", runtime="f" * 16)
    (broken / "python" / "bin" / "python3").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    result = install(tmp_path, broken, "--prefix", str(prefix))
    assert result.returncode != 0
    assert "無法執行" in result.stderr
    assert (prefix / "current").readlink().as_posix() == "releases/0.4.0-aaaaaaa"
    assert sorted(path.name for path in (prefix / "runtimes").iterdir()) == [RUNTIME]


# ---------------------------------------------------------------- 沿用 clone 安裝的設定


def legacy_repo(folder: Path) -> Path:
    repo = folder / "my repo$x"
    (repo / ".venv-server" / "bin").mkdir(parents=True)
    (repo / ".rpa-server.env").write_text(
        "export RPA_DATA_DIR=/srv/rpa-data\nexport RPA_PORT=9090\n", encoding="utf-8"
    )
    return repo


def test_imports_settings_of_the_service_from_setup_linux(tmp_path: Path) -> None:
    repo = legacy_repo(tmp_path / "old")
    unit = tmp_path / "unit" / "rpa-server.service"
    unit.parent.mkdir()
    launcher = repo / ".venv-server" / "bin" / "rpa-server"
    # 和 setup-linux.sh 寫的一樣：$ 變成 $$，整段加引號
    quoted = str(launcher).replace("$", "$$")
    unit.write_text(f'[Service]\nExecStart=/bin/bash "{quoted}"\n', encoding="utf-8")
    prefix = tmp_path / "srv"
    output = ok(install(tmp_path, make_bundle(tmp_path / "a"), "--prefix", str(prefix)))
    assert (prefix / "rpa-server.env").read_text("utf-8") == (repo / ".rpa-server.env").read_text(
        "utf-8"
    )
    assert "沿用之前的設定" in output
    # 服務還在用 clone 的那份：不動它，說明怎麼改用分發包
    assert "--install-service" in output
    assert "背景服務：仍是另一份安裝" in output


def test_imports_settings_from_the_default_clone(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / ".rpa-server.env").write_text("export RPA_PORT=9191\n", encoding="utf-8")
    prefix = tmp_path / "srv"
    ok(install(tmp_path, make_bundle(tmp_path / "a"), "--prefix", str(prefix)))
    assert "9191" in (prefix / "rpa-server.env").read_text("utf-8")


def test_explicit_import_and_existing_settings_win(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    chosen = tmp_path / "chosen.env"
    chosen.write_text("export RPA_PORT=7070\n", encoding="utf-8")
    bundle = make_bundle(tmp_path / "a")
    ok(install(tmp_path, bundle, "--prefix", str(prefix), "--import-env", str(chosen)))
    assert (prefix / "rpa-server.env").read_text("utf-8") == "export RPA_PORT=7070\n"
    other = tmp_path / "other.env"
    other.write_text("export RPA_PORT=1\n", encoding="utf-8")
    output = ok(install(tmp_path, bundle, "--prefix", str(prefix), "--import-env", str(other)))
    assert "保留它" in output
    assert (prefix / "rpa-server.env").read_text("utf-8") == "export RPA_PORT=7070\n"
    missing = install(tmp_path, bundle, "--prefix", str(tmp_path / "x"), "--import-env", "/nope")
    assert missing.returncode != 0


# ---------------------------------------------------------------- systemd


SYSTEMD = (
    'has_systemd() { return 0; }; as_root() { echo "ROOT $*" >> "$CALLS"; '
    'if [ "$1" = install ]; then cp "$4" "$5"; fi; }; '
    'systemctl() { [ "${FAKE_ACTIVE:-0}" = 1 ]; }; wait_until_serving() { return 0; }; '
)


def test_install_service(tmp_path: Path) -> None:
    calls = tmp_path / "calls.txt"
    prefix = tmp_path / "srv"
    (tmp_path / "unit").mkdir()
    output = ok(
        install(
            tmp_path,
            make_bundle(tmp_path / "a"),
            "--prefix",
            str(prefix),
            "--install-service",
            before=SYSTEMD,
            env={"CALLS": str(calls)},
        )
    )
    lines = calls.read_text("utf-8").splitlines()
    assert lines[0].startswith("ROOT install -m 644")
    assert lines[1:] == [
        "ROOT systemctl daemon-reload",
        "ROOT systemctl enable rpa-server.service",
        "ROOT systemctl restart rpa-server.service",
    ]
    assert "開機自動啟動" in output


def test_upgrade_restarts_our_running_service(tmp_path: Path) -> None:
    calls = tmp_path / "calls.txt"
    prefix = tmp_path / "srv"
    (tmp_path / "unit").mkdir()
    env = {"CALLS": str(calls), "FAKE_ACTIVE": "1"}
    first = make_bundle(tmp_path / "a", commit="aaaaaaa")
    ok(
        install(
            tmp_path, first, "--prefix", str(prefix), "--install-service", before=SYSTEMD, env=env
        )
    )
    calls.unlink()
    second = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    output = ok(install(tmp_path, second, "--prefix", str(prefix), before=SYSTEMD, env=env))
    assert calls.read_text("utf-8").splitlines() == ["ROOT systemctl restart rpa-server.service"]
    assert "背景服務：已重新啟動" in output
    assert not (prefix / "run" / "restart.request").exists()  # systemd 已經重新啟動


def test_rolled_back_restart_says_so(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    (tmp_path / "unit").mkdir()
    env = {"CALLS": str(tmp_path / "calls.txt"), "FAKE_ACTIVE": "1"}
    first = make_bundle(tmp_path / "a", commit="aaaaaaa")
    ok(
        install(
            tmp_path, first, "--prefix", str(prefix), "--install-service", before=SYSTEMD, env=env
        )
    )
    second = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    # 重新啟動後 bin/rpa serve 退回上一版：current 又指回 0.4.0
    rollback = (
        'as_root() { echo "ROOT $*" >> "$CALLS"; '
        'ln -sfn releases/0.4.0-aaaaaaa "$PREFIX/current"; }; '
    )
    result = install(tmp_path, second, "--prefix", str(prefix), before=SYSTEMD + rollback, env=env)
    assert result.returncode != 0
    assert "已自動退回 0.4.0-aaaaaaa" in result.stderr


def test_failed_restart_explains_how_to_go_back(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    (tmp_path / "unit").mkdir()
    env = {"CALLS": str(tmp_path / "calls.txt"), "FAKE_ACTIVE": "1"}
    first = make_bundle(tmp_path / "a", commit="aaaaaaa")
    ok(
        install(
            tmp_path, first, "--prefix", str(prefix), "--install-service", before=SYSTEMD, env=env
        )
    )
    second = make_bundle(tmp_path / "b", version="0.4.1", commit="bbbbbbb")
    result = install(
        tmp_path,
        second,
        "--prefix",
        str(prefix),
        before=SYSTEMD + "wait_until_serving() { return 1; }; ",
        env=env,
    )
    assert result.returncode != 0
    assert "releases/0.4.0-aaaaaaa" in result.stderr


def test_install_service_needs_systemd(tmp_path: Path) -> None:
    result = install(tmp_path, make_bundle(tmp_path / "a"), "--install-service")
    assert result.returncode != 0
    assert "systemd" in result.stderr


def test_unit_quotes_unusual_paths(tmp_path: Path) -> None:
    prefix = tmp_path / "100% $HOME"
    ok(install(tmp_path, make_bundle(tmp_path / "a"), "--prefix", str(prefix)))
    unit = (prefix / "rpa-server.service").read_text("utf-8")
    expected = str(prefix / "bin" / "rpa-server").replace("$", "$$").replace("%", "%%")
    assert f'ExecStart=/bin/bash "{expected}"' in unit


# ---------------------------------------------------------------- bin/rpa


def make_release(prefix: Path, name: str, python: str) -> Path:
    """裝好的版本資料夾：真的 bin/rpa，python3 是 ``python`` 這段 Bash。"""
    root = prefix / "releases" / name
    (root / "bin").mkdir(parents=True)
    (root / "python" / "bin").mkdir(parents=True)
    (root / "app").mkdir()
    shutil.copy2(WRAPPER, root / "bin" / "rpa")
    stub = root / "python" / "bin" / "python3"
    stub.write_text("#!/usr/bin/env bash\n" + python, encoding="utf-8")
    stub.chmod(0o755)
    return root


def point_current(prefix: Path, name: str) -> None:
    current = prefix / "current"
    if current.is_symlink():
        current.unlink()
    current.symlink_to(f"releases/{name}")


def host_env(folder: Path, environ: dict[str, str]) -> dict[str, str]:
    """執行真的 bin/rpa 時的環境變數。

    bin/rpa 只在 Linux 的分發包裡執行，退回時用 GNU 的 ``mv -Tf`` 換掉 current 連結。macOS 的
    BSD mv 沒有 -T：和上面的 HOST_TOOLS 一樣，在 PATH 最前面放一個 mv，把它換成意思相同的
    ``mv -hf``（2026-10-27，每晚完整測試 issue #80）。Linux 不加，繼續直接驗證 GNU mv。
    """
    if sys.platform != "darwin":
        return environ
    tools = folder / "host-tools"
    tools.mkdir(exist_ok=True)
    mv = tools / "mv"
    mv.write_text(
        '#!/bin/bash\nif [ "$1" = -Tf ]; then shift; exec /bin/mv -hf "$@"; fi\n'
        'exec /bin/mv "$@"\n',
        encoding="utf-8",
    )
    mv.chmod(0o755)
    return {**environ, "PATH": f"{tools}{os.pathsep}{environ.get('PATH', '')}"}


def test_wrapper_uses_the_bundled_python(tmp_path: Path) -> None:
    root = make_release(
        tmp_path,
        "1",
        'printf "%s\\n" "$@" "path=${PYTHONPATH-unset}" "release=$RPA_RELEASE_DIR" '
        '"examples=$RPA_EXAMPLES_DIR" "nouser=$PYTHONNOUSERSITE" "cert=${SSL_CERT_FILE-unset}"\n',
    )
    point_current(tmp_path, "1")
    environ = {**os.environ, "PYTHONPATH": "/evil", "SSL_CERT_FILE": "/my/ca.pem"}
    environ.pop("RPA_EXAMPLES_DIR", None)
    result = subprocess.run(
        [str(tmp_path / "current" / "bin" / "rpa"), "pack", "--x"],
        env=environ,
        capture_output=True,
        text=True,
        check=True,
    )
    real = root.resolve()
    assert result.stdout.splitlines() == [
        "-m",
        "rpa_cli",
        "pack",
        "--x",
        f"path={real}/app",
        f"release={real}",
        f"examples={real}/scenarios/demo",
        "nouser=1",
        "cert=/my/ca.pem",
    ]


def supervise(prefix: Path, *args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("RPA_", "PYTHON"))}
    return subprocess.run(
        [str(prefix / "current" / "bin" / "rpa"), "serve", *args],
        env=host_env(prefix.parent, {**environ, "LOG": str(prefix / "log.txt")}),
        cwd=prefix / "current",
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_serve_restarts_with_the_new_current(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    # 舊版本：像 rpa update 一樣把 current 換成新版本，再以結束碼 75 結束
    make_release(
        prefix,
        "old",
        'echo "old $* $PWD" >> "$LOG"\n'
        'ln -sfn releases/new "$RPA_RELEASE_DIR/../../current"\nexit 75\n',
    )
    make_release(prefix, "new", 'echo "new $* supervised=$RPA_SUPERVISED" >> "$LOG"\nexit 0\n')
    point_current(prefix, "old")
    result = supervise(prefix, "--port", "1")
    assert result.returncode == 0, result.stderr
    assert (prefix / "log.txt").read_text("utf-8").splitlines() == [
        f"old -m rpa_cli serve --port 1 {prefix.resolve()}",  # 不停在版本資料夾裡（會被刪）
        "new -m rpa_cli serve --port 1 supervised=1",
    ]
    assert "重新啟動，使用 new" in result.stderr


def test_serve_rolls_back_when_the_new_version_cannot_start(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    make_release(prefix, "old", 'echo old >> "$LOG"\nexit 0\n')
    make_release(prefix, "new", 'echo new >> "$LOG"\necho "migrated" > "$DB-wal"\nexit 3\n')
    point_current(prefix, "new")
    data = tmp_path / "data"
    data.mkdir()
    database = data / "rpa.db"
    database.write_text("migrated", encoding="utf-8")
    backup = data / "backup.db"
    backup.write_text("before", encoding="utf-8")
    (prefix / "run").mkdir()
    (prefix / "run" / "update.state").write_text(
        f"target=new\nprevious=old\nbackup={backup}\ndatabase={database}\n", encoding="utf-8"
    )
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("RPA_", "PYTHON"))}
    result = subprocess.run(
        [str(prefix / "current" / "bin" / "rpa"), "serve"],
        env=host_env(tmp_path, {**environ, "LOG": str(prefix / "log.txt"), "DB": str(database)}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (prefix / "log.txt").read_text("utf-8").splitlines() == ["new", "old"]
    assert (prefix / "current").readlink().as_posix() == "releases/old"
    assert database.read_text("utf-8") == "before"
    assert not Path(f"{database}-wal").exists()
    assert not (prefix / "run" / "update.state").exists()
    assert "target=new" in (prefix / "run" / "update.failed").read_text("utf-8")
    assert "退回 old" in result.stderr


def test_serve_does_not_roll_back_a_confirmed_version(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    make_release(prefix, "old", 'echo old >> "$LOG"\n')
    make_release(prefix, "new", 'echo new >> "$LOG"\nexit 3\n')
    point_current(prefix, "new")
    # 沒有 update.state：新版本已經開始服務過，之後當掉交給 systemd 之類處理
    result = supervise(prefix)
    assert result.returncode == 3
    assert (prefix / "log.txt").read_text("utf-8").splitlines() == ["new"]
    assert (prefix / "current").readlink().as_posix() == "releases/new"


def test_serve_forwards_term_and_stops_with_it(tmp_path: Path) -> None:
    prefix = tmp_path / "srv"
    make_release(
        prefix,
        "1",
        'trap \'echo "got TERM" >> "$LOG"; exit 0\' TERM\necho started >> "$LOG"\n'
        "while :; do sleep 0.1; done\n",
    )
    point_current(prefix, "1")
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("RPA_", "PYTHON"))}
    log = prefix / "log.txt"
    process = subprocess.Popen(
        [str(prefix / "current" / "bin" / "rpa"), "serve"],
        env={**environ, "LOG": str(log)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if log.exists():
                break
            time.sleep(0.1)
        process.terminate()
        assert process.wait(timeout=20) == -signal.SIGTERM
    finally:
        if process.poll() is None:
            process.kill()
    assert log.read_text("utf-8").splitlines() == ["started", "got TERM"]


def test_bundle_run_in_place_is_not_supervised(tmp_path: Path) -> None:
    root = make_release(tmp_path, "1", 'echo "supervised=${RPA_SUPERVISED-no}"\n')
    # 解壓後還沒安裝：沒有 releases/ 與 current，直接執行
    bundle = tmp_path / "bundle"
    root.rename(bundle)
    result = subprocess.run(
        [str(bundle / "bin" / "rpa"), "serve"],
        env={k: v for k, v in os.environ.items() if not k.startswith("RPA_")},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "supervised=no"


# ---------------------------------------------------------------- tools/build_server.py


@pytest.mark.parametrize(
    ("tag", "need"),
    [
        ("cp313-cp313-manylinux_2_28_x86_64", (2, 28)),
        ("cp313-cp313-manylinux_2_34_aarch64", (2, 34)),
        ("cp313-cp313-manylinux2014_x86_64", (2, 17)),
        ("py3-none-manylinux1_x86_64", (2, 5)),
        ("py3-none-any", None),
        ("cp313-abi3-musllinux_1_2_x86_64", None),
    ],
)
def test_tag_glibc(tag: str, need: tuple[int, int] | None) -> None:
    assert build_server.tag_glibc(tag) == need


def test_wheel_needs_the_lowest_of_its_tags() -> None:
    tags = ["cp313-cp313-manylinux_2_17_x86_64", "cp313-cp313-manylinux2014_x86_64"]
    assert build_server.wheel_glibc(tags) == (2, 17)
    assert build_server.wheel_glibc(["py3-none-any"]) is None
    assert build_server.wheel_glibc([]) is None


def test_too_new_wheels(tmp_path: Path) -> None:
    def wheel(name: str, *tags: str) -> None:
        folder = tmp_path / f"{name}.dist-info"
        folder.mkdir()
        lines = ["Wheel-Version: 1.0", *(f"Tag: {tag}" for tag in tags)]
        (folder / "WHEEL").write_text("\n".join(lines) + "\n", encoding="utf-8")

    wheel("ok-1.0", "cp313-cp313-manylinux_2_28_x86_64")
    wheel("pure-1.0", "py3-none-any")
    wheel("new-1.0", "cp313-cp313-manylinux_2_34_x86_64")
    assert build_server.too_new_wheels(tmp_path) == ["new-1.0.dist-info：需要 glibc 2.34"]


def test_targets_and_names() -> None:
    assert build_server.host_target("x86_64").label == "x64"
    assert build_server.host_target("arm64").machine == "aarch64"
    with pytest.raises(SystemExit):
        build_server.host_target("riscv64")
    target = build_server.TARGETS["aarch64"]
    assert target.platform == "aarch64-manylinux_2_28"
    assert target.python("3.13") == "cpython-3.13-linux-aarch64-gnu"
    assert build_server.bundle_name("0.4.0", target) == "RPA-Server-0.4.0-linux-arm64"


def test_build_info_is_read_by_install_sh(tmp_path: Path) -> None:
    text = build_server.build_info_text(
        version="0.4.0",
        commit_id="df47b14",
        target=build_server.TARGETS["x86_64"],
        python="3.13.9",
        runtime=RUNTIME,
    )
    bundle = make_bundle(tmp_path)
    (bundle / "BUILD_INFO").write_text(text, encoding="utf-8")
    result = run('read_bundle "$1"; echo "$RELEASE $ARCH $RUNTIME"', str(bundle))
    assert ok(result).splitlines()[-1] == f"0.4.0-df47b14 x86_64 {RUNTIME}"


def test_version_comes_from_the_packages() -> None:
    assert build_server.package_version().count(".") == 2
    assert build_server.python_version().startswith("3.")


def test_remove_scripts_keeps_python(tmp_path: Path) -> None:
    for name in ("python3", "python3.13", "uvicorn", "alembic"):
        (tmp_path / name).write_text("", encoding="utf-8")
    removed = build_server.remove_scripts(tmp_path, {"python3", "python3.13"})
    assert removed == ["alembic", "uvicorn"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["python3", "python3.13"]
