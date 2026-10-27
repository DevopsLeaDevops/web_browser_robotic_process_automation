"""tools/desktop_shell.py：依層建置的外殼快取與程式碼層路徑（docs/develop/ci.html#layered）。

真正的 DMG、zip 與打包版的 rpa-child 在 CI 的桌面端建置裡；這裡用假的 App 測金鑰、存取快取、
裝上更新檔與確認。
"""

import base64
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from rpa_update import ed25519
from rpa_update.build import private_to_pem
from rpa_update.layers import Active, write_active
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import Runtime
from tools import desktop_shell

SEED = bytes(range(32))
TARGET = "worker-windows-x64"
RUNTIME = Runtime(TARGET, "0123456789abcdef", (ed25519.public_key(SEED),), release="0.6.3-aaaaaaa")


def test_fixed_key_from_the_secret(tmp_path: Path) -> None:
    out = tmp_path / "update-ci.pem"
    key = desktop_shell.setup_key(out, {"CI_KEY": private_to_pem(SEED)})
    assert key.persistent
    assert key.ident == ed25519.key_id(ed25519.public_key(SEED))
    assert ed25519.private_from_pem(out.read_text(encoding="ascii")) == SEED
    if os.name != "nt":
        assert out.stat().st_mode & 0o077 == 0  # 只有自己讀得到
    # 同一個 Secret，每次都是同一把：快取的外殼才認得之後簽的更新檔
    again = desktop_shell.setup_key(tmp_path / "again.pem", {"CI_KEY": private_to_pem(SEED)})
    assert again.ident == key.ident


def test_temporary_key_without_the_secret(tmp_path: Path) -> None:
    key = desktop_shell.setup_key(tmp_path / "update-ci.pem", {})
    assert not key.persistent
    assert key.ident == desktop_shell.TEMPORARY
    assert len(key.public) == 32


def test_broken_secret_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="RPA_UPDATE_CI_KEY"):
        desktop_shell.setup_key(tmp_path / "x.pem", {"CI_KEY": "not a key"})


def test_key_command_exports_the_public_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, out = tmp_path / "env", tmp_path / "out"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("CI_KEY", private_to_pem(SEED))
    assert desktop_shell.main(["key", "--out", str(tmp_path / "k.pem")]) == 0
    public = base64.b64encode(ed25519.public_key(SEED)).decode("ascii")
    assert f"RPA_UPDATE_EXTRA_KEYS={public}" in env.read_text(encoding="utf-8")
    assert "persistent=true" in out.read_text(encoding="utf-8")


def fake_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """假的完整建置：dist/ 裡的 zip 與 runtime.json，快取與 dist 都放在 tmp_path。"""
    dist, cache = tmp_path / "dist", tmp_path / "cache"
    monkeypatch.setattr(desktop_shell, "DIST", dist)
    monkeypatch.setattr(desktop_shell, "CACHE", cache)
    monkeypatch.setattr(desktop_shell, "executable", lambda app: dist / "rpa-worker" / "rpa-worker")
    monkeypatch.setattr(desktop_shell, "child", lambda app: dist / "rpa-worker" / "rpa-child")
    monkeypatch.setattr(desktop_shell, "runtime_copy", lambda runtime: dist / "runtime-copy.json")
    built = tmp_path / "built"
    built.mkdir()
    archive = built / "RPA-Worker-0.6.3-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("rpa-worker/rpa-worker", "app")
        stream.writestr("rpa-worker/rpa-child", "child")
    runtime_file = built / f"runtime-{TARGET}.json"
    runtime_file.write_text(json.dumps(RUNTIME.to_json()), encoding="utf-8")
    return {"APP_ARTIFACT": str(archive), "APP_RUNTIME_FILE": str(runtime_file)}


def test_save_and_restore_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environ = fake_build(tmp_path, monkeypatch)
    info = json.loads(desktop_shell.save("worker", environ).read_text(encoding="utf-8"))
    assert info["release"] == "0.6.3-aaaaaaa"
    assert info["runtime"] == "0123456789abcdef"
    values = desktop_shell.restore("worker", platform="win32")
    assert Path(values["APP_EXECUTABLE"]).read_text(encoding="utf-8") == "app"
    assert values["APP_RUNTIME"] == f"{TARGET}=0123456789abcdef"
    assert values["SHELL_RELEASE"] == "0.6.3-aaaaaaa"
    assert values["APP_ARTIFACT"] == ""  # 程式碼層路徑沒有新的安裝包
    assert Path(values["APP_RUNTIME_FILE"]).is_file()
    with pytest.raises(SystemExit, match="不是 recorder"):
        desktop_shell.restore("recorder", platform="win32")


def make_update(tmp_path: Path, commit: str = "bbbbbbb") -> Path:
    content = tmp_path / "content"
    (content / "app" / "rpa_core").mkdir(parents=True)
    (content / "app" / "rpa_core" / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
    files = scan_tree(content)
    manifest = Manifest(
        version="0.6.3",
        commit=commit,
        built_at="2026-10-27T00:00:00+00:00",
        fingerprint="f" * 16,
        protocol=1,
        features=(),
        runtimes={TARGET: RUNTIME.id},
        files=files,
    )
    path = tmp_path / "RPA-Update-0.6.3.zip"
    write_update(path, manifest, {name: content / name for name in files}, SEED)
    return path


def test_check_reports_a_layer_that_was_not_used(tmp_path: Path) -> None:
    update = make_update(tmp_path)
    home = tmp_path / "home"
    root = home / "app"
    root.mkdir(parents=True)
    write_active(root, Active(release="0.6.3-bbbbbbb"))
    assert desktop_shell.check("worker", update, home) == []
    write_active(root, Active(release="0.6.3-bbbbbbb", pending=True, attempts=1))
    assert desktop_shell.check("worker", update, home) == ["0.6.3-bbbbbbb 還沒確認（啟動了 1 次）"]
    write_active(root, Active(release=None, failed="0.6.3-bbbbbbb"))
    problems = desktop_shell.check("worker", update, home)
    assert problems[0] == "active.json 用的是 內建的程式，不是 0.6.3-bbbbbbb"
    assert "被退回了" in problems[1]
    report = tmp_path / "self-test.json"
    report.write_text(json.dumps({"ok": True, "build": {"commit": "aaaaaaa"}}), encoding="utf-8")
    write_active(root, Active(release="0.6.3-bbbbbbb"))
    assert desktop_shell.check("worker", update, home, report) == [
        "self-test.json 的提交是 aaaaaaa，不是 bbbbbbb"
    ]


@pytest.mark.skipif(os.name == "nt", reason="假的 rpa-child 是 Python 腳本（shebang）")
@pytest.mark.parametrize(("reported", "ok"), [("bbbbbbb", True), ("aaaaaaa", False)])
def test_install_checks_that_the_launcher_uses_the_layer(
    tmp_path: Path, reported: str, ok: bool
) -> None:
    update = make_update(tmp_path)
    child = tmp_path / "rpa-child"
    child.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        "if sys.argv[1] == '--install-update':\n    print(json.dumps({'version': '0.6.3'}))\n"
        f"else:\n    print(json.dumps({{'version': '0.6.3', 'commit': '{reported}'}}))\n",
        encoding="utf-8",
    )
    child.chmod(0o755)
    if ok:
        info = desktop_shell.install("worker", update, child, tmp_path / "home")
        assert info["commit"] == "bbbbbbb"
    else:
        with pytest.raises(SystemExit, match="啟動器沒有用這一層"):
            desktop_shell.install("worker", update, child, tmp_path / "home")


def test_home_env_points_the_app_at_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RPA_WORKER_HOME", "/somewhere")
    assert desktop_shell.home_env("worker", tmp_path)["RPA_WORKER_HOME"] == str(tmp_path)
    assert "RPA_WORKER_HOME" not in desktop_shell.home_env("worker", None)
