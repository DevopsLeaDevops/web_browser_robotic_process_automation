"""產生更新檔 ``RPA-Update-<版本>.zip``（ADR 0018）：只有我們的程式，加上清單與簽章。

    uv run python -m tools.build_update --runtime server-linux-x64=<環境代號> [--runtime …]

- 程式碼層：七個工作區套件（不含跟著執行環境走的 rpa-update）建成 wheel、裝進 ``app/``，
  用和分發包相同的方法（tools/build_server.py 的 :func:`build_app_layer`）編譯 .pyc；
- 伺服器另外需要的檔案：``server/bin/rpa``、``server/install.sh``、``server/scenarios/demo``；
- 清單：版本、提交、程式指紋、協定版本、看得懂的 DSL 擴充、每個目標需要的環境代號
  （``--runtime``，來自各平台完整安裝包的建置），以及每個檔案的 SHA-256 與大小；
- 簽章：私鑰（PEM）從環境變數 ``RPA_UPDATE_SIGNING_KEY`` 或 ``--key`` 檔案讀取，兩者都沒有就失敗。

Python 必須和執行環境同一個主、次版本（``.python-version``），.pyc 才載入得了。
``--version``、``--commit`` 只給 CI 測試升級路徑時用（模擬下一個版本）。
產物在 dist/update/；最後印出 ``artifact: …``，在 GitHub Actions 裡同時寫進步驟的輸出。

發布流程（release.yml）改用 ``--runtime-file``：各平台建置時留下的 runtime.json 副本
（``runtime-<目標>.json``），再加上 ``--release`` 確認：

- :data:`rpa_update.keys.RELEASE_KEYS` 不是空的，簽章的私鑰是其中一把；
- 每個安裝包信任的公鑰剛好就是 RELEASE_KEYS（沒有混進 CI 的臨時金鑰）。
"""

import argparse
import base64
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from rpa_update import ed25519
from rpa_update.errors import UpdateError
from rpa_update.keys import RELEASE_KEYS
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import KINDS, PLATFORMS, Runtime, load_runtime
from tools.build_server import (
    EXAMPLES,
    PACKAGING,
    RUNTIME_PACKAGE,
    build_app_layer,
    build_wheels,
    commit,
    find_uv,
    package_version,
    python_version,
)

ROOT: Final = Path(__file__).resolve().parent.parent
DIST: Final = ROOT / "dist" / "update"
WORK: Final = ROOT / "build" / "update"
KEY_ENV: Final = "RPA_UPDATE_SIGNING_KEY"
PACKAGES: Final = (
    "rpa-core",
    "rpa-script",
    "rpa-runner",
    "rpa-worker",
    "rpa-testsite",
    "rpa-server",
    "rpa-cli",
    "rpa-desktop",
)
"""程式碼層的工作區套件：伺服器與桌面 App 共用同一份。"""
TARGETS: Final = frozenset(f"{kind}-{platform}" for kind in KINDS for platform in PLATFORMS)
_RUNTIME_ID: Final = re.compile(r"^[0-9a-f]{16}$")
_COMMIT: Final = re.compile(r"^[0-9a-f]{0,40}$")


def parse_runtimes(values: Sequence[str]) -> dict[str, str]:
    """``目標=環境代號`` → {目標: 環境代號}；格式不對時拋出 SystemExit。"""
    runtimes: dict[str, str] = {}
    for value in values:
        target, sep, ident = value.partition("=")
        if not sep or target not in TARGETS or not _RUNTIME_ID.fullmatch(ident):
            choices = ", ".join(sorted(TARGETS))
            raise SystemExit(f"--runtime 要寫成 目標=16 位十六進位（目標：{choices}）：{value}")
        if runtimes.get(target, ident) != ident:
            raise SystemExit(f"{target} 有兩個不同的環境代號")
        runtimes[target] = ident
    return runtimes


def read_runtime_files(paths: Sequence[Path]) -> list[Runtime]:
    """``--runtime-file``：各平台建置時留下的 runtime.json 副本。"""
    runtimes: list[Runtime] = []
    for path in paths:
        try:
            runtime = load_runtime(path)
        except UpdateError as error:
            raise SystemExit(f"{path} 不是 runtime.json：{error.code}") from None
        if runtime is None:
            raise SystemExit(f"找不到 {path}")
        runtimes.append(runtime)
    return runtimes


def check_release_keys(runtimes: Sequence[Runtime], seed: bytes) -> None:
    """``--release``：簽章的私鑰與每個安裝包信任的公鑰都是發布用的那一組。"""
    release = {base64.b64decode(key) for key in RELEASE_KEYS}
    if not release:
        raise SystemExit(
            "rpa_update/keys.py 的 RELEASE_KEYS 是空的：先產生發布用的金鑰"
            "（docs/develop/ci.html#update-key），把公鑰加進去"
        )
    if ed25519.public_key(seed) not in release:
        raise SystemExit(f"{KEY_ENV} 的私鑰對不上 RELEASE_KEYS 裡的任何一把公鑰")
    for runtime in runtimes:
        if set(runtime.keys) != release:
            raise SystemExit(
                f"{runtime.target} 信任的公鑰和 RELEASE_KEYS 不同（混進了 CI 的臨時金鑰？）"
            )


def signing_key(path: Path | None, environ: Mapping[str, str] | None = None) -> bytes:
    """簽章用的私鑰（32 位元組）：``--key`` 檔案優先，否則讀環境變數。"""
    env = os.environ if environ is None else environ
    if path is not None:
        text = path.read_text(encoding="ascii")
    elif env.get(KEY_ENV, "").strip():
        text = env[KEY_ENV]
    else:
        raise SystemExit(f"沒有簽章的私鑰：設定 {KEY_ENV}（PEM）或用 --key 指定檔案")
    try:
        return ed25519.private_from_pem(text)
    except ed25519.InvalidKeyError as error:
        raise SystemExit(f"私鑰不能用：{error}") from None


def stage(uv: str, work: Path) -> Path:
    """組出更新檔的內容（app/ 與 server/），回傳資料夾。"""
    content = work / "content"
    shutil.rmtree(content, ignore_errors=True)
    wheels = build_wheels(uv, PACKAGES, work / "wheels")
    if RUNTIME_PACKAGE in wheels:
        raise SystemExit(f"{RUNTIME_PACKAGE} 跟著執行環境走，不能放進更新檔")
    build_app_layer(uv, Path(sys.executable), wheels.values(), content / "app")
    server = content / "server"
    (server / "bin").mkdir(parents=True)
    shutil.copy2(PACKAGING / "rpa", server / "bin" / "rpa")
    shutil.copy2(PACKAGING / "install.sh", server / "install.sh")
    shutil.copytree(EXAMPLES, server / "scenarios" / "demo")
    for script in (server / "bin" / "rpa", server / "install.sh"):
        script.chmod(0o755)
    return content


def build(
    runtimes: Mapping[str, str],
    seed: bytes,
    *,
    version: str | None = None,
    commit_id: str | None = None,
) -> Path:
    """產生更新檔，回傳路徑。"""
    from rpa_core.dsl.features import FEATURES
    from rpa_worker.environment import PROTOCOL, code_fingerprint

    expected = python_version()
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    if actual != expected:
        raise SystemExit(f"要用 Python {expected} 執行（.pyc 要和執行環境相同），目前是 {actual}")
    if not runtimes:
        raise SystemExit("至少要有一個 --runtime：沒有任何目標能套用這個更新檔")
    version = version or package_version()
    commit_id = commit() if commit_id is None else commit_id
    if not _COMMIT.fullmatch(commit_id):
        raise SystemExit(f"提交的格式不對：{commit_id}")
    content = stage(find_uv(), WORK)
    files = scan_tree(content)
    manifest = Manifest(
        version=version,
        commit=commit_id,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        fingerprint=code_fingerprint(),
        protocol=PROTOCOL,
        features=tuple(sorted(FEATURES)),
        runtimes=dict(runtimes),
        files=files,
    )
    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / f"RPA-Update-{version}.zip"
    archive.unlink(missing_ok=True)
    write_update(archive, manifest, {name: content / name for name in files}, seed)
    return archive


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="產生更新檔（只有我們的程式，加上清單與簽章）")
    parser.add_argument("--runtime", action="append", default=[], metavar="目標=環境代號")
    parser.add_argument(
        "--runtime-file",
        action="append",
        default=[],
        type=Path,
        help="各平台建置留下的 runtime.json 副本（發布流程用）",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="發布用：確認簽章與每個安裝包信任的公鑰都是 RELEASE_KEYS",
    )
    parser.add_argument("--key", type=Path, help=f"私鑰的 PEM 檔案（預設讀 {KEY_ENV}）")
    parser.add_argument("--version", help="只給測試用：換掉版本")
    parser.add_argument("--commit", help="只給測試用：換掉提交")
    args = parser.parse_args(argv)
    files = read_runtime_files(args.runtime_file)
    runtimes = parse_runtimes([*args.runtime, *(f"{item.target}={item.id}" for item in files)])
    seed = signing_key(args.key)
    if args.release:
        if args.runtime or args.version or args.commit:
            raise SystemExit("--release 只接受 --runtime-file（目標與信任的公鑰要能核對）")
        check_release_keys(files, seed)
    archive = build(runtimes, seed, version=args.version, commit_id=args.commit)
    key = ed25519.key_id(ed25519.public_key(seed))
    size = archive.stat().st_size / 1024 / 1024
    print(f"artifact: {archive.as_posix()}")
    print(f"簽章的金鑰：{key}；大小：{size:.1f} MB")
    for target, ident in sorted(runtimes.items()):
        print(f"runtime: {target}={ident}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"artifact={archive.as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
