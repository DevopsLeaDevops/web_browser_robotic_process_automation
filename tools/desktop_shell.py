"""桌面端建置的外殼快取與程式碼層路徑（docs/develop/ci.html#layered，2026-10-27 起）。

外殼（Python、第三方套件、PyInstaller 收進去的一切與 rpa_update，ADR 0018）沒變時，不必每次
重新打包：完整建置時把下載用的安裝包（macOS 的 DMG、Windows 的 zip）與 runtime.json 存進快取，
之後同一個外殼鍵（tools/ci_changes.py 的 ``shell_key``）的建置直接取出 App，裝上這次的程式碼層
（更新檔）再測。這正是裝置在現場升級的方式：舊的外殼加上新的程式。

    uv run python -m tools.desktop_shell key --out 私鑰.pem      # 測試更新檔用的金鑰
    uv run python -m tools.desktop_shell save recorder            # 完整建置之後：存進 .shell-cache/
    uv run python -m tools.desktop_shell restore recorder         # 從 .shell-cache/ 取出 App
    uv run python -m tools.desktop_shell layer recorder [--home 資料夾]   # 裝上 $UPDATE_ZIP
    uv run python -m tools.desktop_shell check recorder [--home 資料夾] [--report self-test.json]

``key``：環境變數 ``CI_KEY``（GitHub Secrets 的 ``RPA_UPDATE_CI_KEY``，PEM）有值時用它：每次都是
同一把，快取的外殼信任它，之後的建置才簽得出外殼認得的更新檔。沒有值時（還沒設定、或 fork 與
Dependabot 的 PR 拿不到 Secrets）照舊每次產生臨時金鑰，外殼不能重複使用，一律完整建置。
兩種都只給 CI：發布的建置不加任何額外的公鑰（tools/build_update.py --release 會核對）。

``restore`` 與 build_desktop.py 一樣把 App 放在 dist/desktop/，再把位置寫進 ``$GITHUB_ENV``
（``APP_EXECUTABLE``、``APP_CHILD``、``APP_RUNTIME``、``APP_RUNTIME_FILE``），之後的步驟不必
分辨 App 是剛建好的還是快取裡的。
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from rpa_desktop.build_info import APPS, App
from rpa_update import ed25519
from rpa_update.build import EXTRA_KEYS_ENV, private_to_pem
from rpa_update.layers import HOME_ENVS, LAYERS_DIR, app_home, read_active
from rpa_update.manifest import MANIFEST, Manifest
from rpa_update.runtime import load_runtime
from tools.build_desktop import BUNDLES, DIST, ROOT, child, executable, runtime_copy

CACHE: Final = ROOT / ".shell-cache"
"""快取的內容（相對倉庫根目錄，存與取都是同一個位置）。"""
INFO: Final = "shell.json"
KEY_ENV: Final = "CI_KEY"
TEMPORARY: Final = "temporary"


def export(values: Mapping[str, str]) -> None:
    """寫進 ``$GITHUB_ENV``（之後的步驟都看得到）並印出。"""
    target = os.environ.get("GITHUB_ENV")
    if target:
        with Path(target).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())
    for key, value in values.items():
        print(f"{key}={value}")


def output(values: Mapping[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with Path(target).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())


# ---------------------------------------------------------------- 金鑰


@dataclass(frozen=True, slots=True)
class Key:
    ident: str
    """金鑰代號（快取鍵的一部分）；臨時金鑰是 :data:`TEMPORARY`。"""
    persistent: bool
    """是不是 RPA_UPDATE_CI_KEY（每次都同一把，外殼才能重複使用）。"""
    public: bytes


def setup_key(out: Path, environ: Mapping[str, str] | None = None) -> Key:
    """寫出測試更新檔用的私鑰。"""
    env = os.environ if environ is None else environ
    text = env.get(KEY_ENV, "").strip()
    if text:
        try:
            seed = ed25519.private_from_pem(text)
        except ed25519.InvalidKeyError as error:
            raise SystemExit(f"RPA_UPDATE_CI_KEY 不是 Ed25519 的私鑰（PEM）：{error}") from None
        persistent = True
    else:
        seed = os.urandom(32)
        persistent = False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    out.touch(mode=0o600)
    out.write_text(private_to_pem(seed), encoding="ascii")
    public = ed25519.public_key(seed)
    return Key(ed25519.key_id(public) if persistent else TEMPORARY, persistent, public)


def key_command(args: argparse.Namespace) -> int:
    key = setup_key(Path(args.out))
    ident, persistent = key.ident, key.persistent
    export(
        {
            EXTRA_KEYS_ENV: base64.b64encode(key.public).decode("ascii"),
            "UPDATE_KEY": Path(args.out).as_posix(),
        }
    )
    output({"keyid": ident, "persistent": "true" if persistent else "false"})
    if not persistent:
        print(
            "::warning title=外殼快取::沒有 RPA_UPDATE_CI_KEY（還沒設定，或 fork、Dependabot 的 PR"
            " 拿不到 Secrets）：用臨時金鑰，外殼不能快取，一律完整建置。設定方法見"
            " docs/develop/ci.html#ci-key"
        )
    else:
        print(f"::notice title=外殼快取::測試更新檔的金鑰 {ident}（RPA_UPDATE_CI_KEY）")
    return 0


# ---------------------------------------------------------------- 存與取


def save(app: App, environ: Mapping[str, str] | None = None) -> Path:
    """完整建置之後：下載用的安裝包、runtime.json 與說明檔放進 :data:`CACHE`。"""
    env = os.environ if environ is None else environ
    artifact = Path(env["APP_ARTIFACT"])
    runtime_file = Path(env["APP_RUNTIME_FILE"])
    runtime = load_runtime(runtime_file)
    if runtime is None:
        raise SystemExit(f"找不到 {runtime_file}")
    shutil.rmtree(CACHE, ignore_errors=True)
    CACHE.mkdir(parents=True)
    shutil.copy2(artifact, CACHE / artifact.name)
    shutil.copy2(runtime_file, CACHE / runtime_file.name)
    info = {
        "app": app,
        "target": runtime.target,
        "runtime": runtime.id,
        "release": runtime.release,
        "artifact": artifact.name,
        "runtime_file": runtime_file.name,
        "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run": env.get("GITHUB_RUN_ID", ""),
    }
    (CACHE / INFO).write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return CACHE / INFO


def _mac_app(image: Path, app: App) -> None:
    """從 DMG 取出 .app（和使用者打開 DMG、拖進「應用程式」一樣）。"""
    bundle = f"{BUNDLES[app]}.app"
    target = DIST / bundle
    shutil.rmtree(target, ignore_errors=True)
    mount = Path(tempfile.mkdtemp(prefix="rpa-shell-"))
    subprocess.run(
        [
            "hdiutil",
            "attach",
            "-nobrowse",
            "-readonly",
            "-noverify",
            "-mountpoint",
            str(mount),
            str(image),
        ],
        check=True,
        capture_output=True,
    )
    try:
        subprocess.run(["ditto", str(mount / bundle), str(target)], check=True)
    finally:
        subprocess.run(["hdiutil", "detach", str(mount), "-force"], check=False)


def restore(app: App, platform: str = sys.platform) -> dict[str, str]:
    """從 :data:`CACHE` 取出 App 放到 dist/desktop/，回傳要寫進 ``$GITHUB_ENV`` 的位置。"""
    info = cast("dict[str, str]", json.loads((CACHE / INFO).read_text(encoding="utf-8")))
    if info.get("app") != app:
        raise SystemExit(f"快取裡是 {info.get('app')}，不是 {app}")
    image = CACHE / info["artifact"]
    DIST.mkdir(parents=True, exist_ok=True)
    if platform == "darwin":
        _mac_app(image, app)
    else:
        folder = executable(app).parent
        shutil.rmtree(folder, ignore_errors=True)
        with zipfile.ZipFile(image) as archive:
            archive.extractall(DIST)
    runtime = load_runtime(CACHE / info["runtime_file"])
    if runtime is None:
        raise SystemExit(f"快取裡沒有 {info['runtime_file']}")
    copy = runtime_copy(runtime)
    shutil.copy2(CACHE / info["runtime_file"], copy)
    if not executable(app).is_file():
        raise SystemExit(f"取出之後找不到 {executable(app)}")
    return {
        "APP_EXECUTABLE": executable(app).as_posix(),
        "APP_CHILD": child(app).as_posix(),
        "APP_ARTIFACT": "",
        "APP_INSTALLER": "",
        "APP_RUNTIME": f"{runtime.target}={runtime.id}",
        "APP_RUNTIME_FILE": copy.as_posix(),
        "SHELL_RELEASE": info.get("release", ""),
    }


def save_command(args: argparse.Namespace) -> int:
    path = save(cast("App", args.app))
    print(path.read_text(encoding="utf-8"))
    return 0


def restore_command(args: argparse.Namespace) -> int:
    values = restore(cast("App", args.app))
    export(values)
    print(
        f"::notice title=程式碼層路徑::外殼來自快取（內建的程式 {values['SHELL_RELEASE']}，"
        f"{values['APP_RUNTIME']}）：不重新打包，裝上這次的更新檔再測"
    )
    return 0


# ---------------------------------------------------------------- 裝上程式碼層並確認


def manifest_of(update: Path) -> Manifest:
    with zipfile.ZipFile(update) as archive:
        return Manifest.from_bytes(archive.read(MANIFEST))


def home_env(app: App, home: Path | None) -> dict[str, str]:
    """執行打包版用的環境變數：``home`` 是 None 時用預設的資料夾（和雙擊 App 一樣）。"""
    env = dict(os.environ)
    if home is None:
        env.pop(HOME_ENVS[app], None)
    else:
        env[HOME_ENVS[app]] = str(home)
    return env


def install(app: App, update: Path, child_path: Path, home: Path | None) -> dict[str, object]:
    """把更新檔裝進 App 的資料夾，執行一次 ``--version`` 確認換成了這一層（也算確認新的一層）。"""
    manifest = manifest_of(update)
    env = home_env(app, home)
    done = subprocess.run(
        [str(child_path), "--install-update", str(update)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"裝不上更新檔（{done.returncode}）：{done.stdout}{done.stderr}")
    printed = subprocess.run(
        [str(child_path), "--version"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=True,
    )
    info = cast("dict[str, object]", json.loads(printed.stdout))
    if info.get("commit") != manifest.commit:
        raise SystemExit(
            f"裝好之後 --version 的提交是 {info.get('commit')}，更新檔是 {manifest.commit}："
            "啟動器沒有用這一層（看 App 資料夾的 app/boot.log）"
        )
    return info


def check(app: App, update: Path, home: Path | None, report: Path | None = None) -> list[str]:
    """跑完之後：這一層已經確認、沒有被退回；``report``（自我測試的報告）用的也是這一層。"""
    manifest = manifest_of(update)
    problems: list[str] = []
    root = app_home(app, home_env(app, home)) / LAYERS_DIR
    active = read_active(root)
    if active.release != manifest.release:
        using = active.release or "內建的程式"
        problems.append(f"active.json 用的是 {using}，不是 {manifest.release}")
    if active.pending:
        problems.append(f"{manifest.release} 還沒確認（啟動了 {active.attempts} 次）")
    if active.failed == manifest.release:
        problems.append(f"{manifest.release} 被退回了（看 {root / 'boot.log'}）")
    if report is not None:
        data = cast("dict[str, object]", json.loads(report.read_text(encoding="utf-8")))
        build = cast("dict[str, object]", data.get("build") or {})
        if build.get("commit") != manifest.commit:
            problems.append(f"{report.name} 的提交是 {build.get('commit')}，不是 {manifest.commit}")
    return problems


def _update() -> Path:
    value = os.environ.get("UPDATE_ZIP", "")
    if not value:
        raise SystemExit("沒有 UPDATE_ZIP：先建這次的更新檔")
    return Path(value)


def layer_command(args: argparse.Namespace) -> int:
    app = cast("App", args.app)
    home = Path(args.home) if args.home else None
    release = manifest_of(_update()).release
    if release == os.environ.get("SHELL_RELEASE"):
        raise SystemExit(
            f"更新檔和快取外殼內建的程式都是 {release}：啟動器會改回內建的程式，測不到程式碼層。"
            "建更新檔時用完整的提交（tools/build_update.py --commit）"
        )
    info = install(app, _update(), Path(os.environ["APP_CHILD"]), home)
    where = home or app_home(app, home_env(app, None))
    print(f"裝好了：{info.get('version')} {info.get('commit')}（{where}）")
    return 0


def check_command(args: argparse.Namespace) -> int:
    app = cast("App", args.app)
    home = Path(args.home) if args.home else None
    report = Path(args.report) if args.report else None
    problems = check(app, _update(), home, report)
    for problem in problems:
        print(f"::error title=程式碼層（{app}）::{problem}")
    if not problems:
        print(f"程式碼層 {manifest_of(_update()).release} 已確認，沒有退回")
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.desktop_shell")
    commands = parser.add_subparsers(dest="command", required=True)
    key = commands.add_parser("key", help="寫出測試更新檔用的私鑰")
    key.add_argument("--out", required=True)
    key.set_defaults(handler=key_command)
    for name, handler, text in (
        ("save", save_command, "完整建置之後存進快取"),
        ("restore", restore_command, "從快取取出 App"),
        ("layer", layer_command, "裝上 $UPDATE_ZIP"),
        ("check", check_command, "確認程式碼層已確認、沒有退回"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("app", choices=APPS)
        if name in ("layer", "check"):
            command.add_argument("--home", help="App 的資料夾（預設和雙擊 App 時相同）")
        if name == "check":
            command.add_argument("--report", help="自我測試的報告：確認用的是這一層")
        command.set_defaults(handler=handler)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
