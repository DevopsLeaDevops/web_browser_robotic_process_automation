import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

from rpa_update import boot, ed25519, layers
from rpa_update.errors import UpdateError
from rpa_update.layers import (
    ACTIVE_FILE,
    BUILTIN,
    LAYER_ENV,
    LOG_FILE,
    MAX_ATTEMPTS,
    Active,
    activate,
    confirm,
    install_layer,
    load_layer,
    prune,
    read_active,
)
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import Runtime

SEED = bytes(range(32))
KEY = ed25519.public_key(SEED)
TARGET = "worker-windows-x64"
RUNTIME = Runtime(TARGET, "0123456789abcdef", (KEY,), release="0.5.0-0000001")


def _update(
    tmp_path: Path,
    commit: str,
    *,
    runtimes: dict[str, str] | None = None,
    seed: bytes = SEED,
    code: str = "",
) -> Path:
    """一個只有小套件 fakeapp 的更新檔：``python -m fakeapp`` 印出自己的提交。"""
    source = tmp_path / f"source-{commit}"
    package = source / "app" / "fakeapp"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f"COMMIT = {commit!r}\n")
    (package / "__main__.py").write_text(
        code or "import fakeapp, sys\nsys.stdout.write(fakeapp.COMMIT)\n"
    )
    files = scan_tree(source)
    manifest = Manifest(
        version="0.6.0",
        commit=commit,
        built_at="2026-10-25T09:00:00+00:00",
        fingerprint="f" * 16,
        protocol=1,
        features=(),
        runtimes={TARGET: RUNTIME.id} if runtimes is None else runtimes,
        files=files,
    )
    path = tmp_path / f"RPA-Update-{commit}.zip"
    write_update(path, manifest, {name: source / name for name in files}, seed)
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Worker 的資料夾；sys.path、環境變數與啟動器的狀態在測試後還原。"""
    folder = tmp_path / "home"
    monkeypatch.setenv("RPA_WORKER_HOME", str(folder))
    monkeypatch.setenv(LAYER_ENV, "")
    monkeypatch.delenv(LAYER_ENV)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.setattr(layers, "_current", None)
    for name in [name for name in sys.modules if name.startswith("fakeapp")]:
        monkeypatch.delitem(sys.modules, name)
    return folder / "app"


def _activate() -> tuple[layers.Layer | None, bool]:
    os.environ.pop(LAYER_ENV, None)
    return activate(RUNTIME)


def test_install_then_activate_and_confirm(tmp_path: Path, home: Path) -> None:
    result = install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    assert (result.manifest.release, result.previous, result.already) == (
        "0.6.0-0000002",
        None,
        False,
    )
    assert read_active(home) == Active(
        release="0.6.0-0000002", pending=True, installed_with=RUNTIME.release
    )

    layer, pending = _activate()
    assert layer is not None
    assert pending
    assert sys.path[0] == str(home / "0.6.0-0000002" / "app")
    assert os.environ[LAYER_ENV] == "0.6.0-0000002"
    assert sys.dont_write_bytecode
    assert layers.current_layer() == layer
    assert read_active(home).attempts == 1
    assert importlib.import_module("fakeapp").COMMIT == "0000002"  # 從這一層載入

    assert confirm(home, "0.6.0-0000002")
    assert read_active(home).pending is False
    assert not confirm(home, "0.6.0-0000002")


def test_same_update_twice_is_already_installed(tmp_path: Path, home: Path) -> None:
    update = _update(tmp_path, "0000002")
    install_layer(home, update, RUNTIME)
    assert install_layer(home, update, RUNTIME).already


def test_update_with_builtin_release_goes_back_to_builtin(tmp_path: Path, home: Path) -> None:
    runtime = Runtime(TARGET, RUNTIME.id, (KEY,), release="0.6.0-0000001")
    install_layer(home, _update(tmp_path, "0000002"), runtime)
    builtin = _update(tmp_path, "0000001")
    result = install_layer(home, builtin, runtime)
    assert (result.previous, result.already) == ("0.6.0-0000002", False)
    assert read_active(home) == Active(installed_with=runtime.release)
    assert install_layer(home, builtin, runtime).already


def test_needs_the_same_runtime(tmp_path: Path, home: Path) -> None:
    with pytest.raises(UpdateError) as raised:
        install_layer(home, _update(tmp_path, "0000002", runtimes={TARGET: "f" * 16}), RUNTIME)
    assert raised.value.code == "runtime_changed"
    assert raised.value.params["needed"] == "f" * 16
    with pytest.raises(UpdateError) as raised:
        install_layer(home, _update(tmp_path, "0000003", runtimes={}), RUNTIME)
    assert raised.value.code == "no_build_for_target"
    assert not home.exists() or not any(home.iterdir())


def test_untrusted_update_is_refused(tmp_path: Path, home: Path) -> None:
    with pytest.raises(UpdateError, match="signature_untrusted"):
        install_layer(home, _update(tmp_path, "0000002", seed=bytes(range(1, 33))), RUNTIME)


def test_unconfirmed_layer_rolls_back(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    confirm(home, "0.6.0-0000002")
    install_layer(home, _update(tmp_path, "0000003"), RUNTIME)
    assert read_active(home).previous == "0.6.0-0000002"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        layer, pending = _activate()
        assert layer is not None
        assert layer.release == "0.6.0-0000003"
        assert pending
        assert read_active(home).attempts == attempt
    layer, pending = _activate()
    assert layer is not None
    assert layer.release == "0.6.0-0000002"
    assert not pending
    active = read_active(home)
    assert (active.release, active.failed, active.pending) == (
        "0.6.0-0000002",
        "0.6.0-0000003",
        False,
    )
    assert "0.6.0-0000003" in (home / LOG_FILE).read_text(encoding="utf-8")


def test_unconfirmed_first_layer_goes_back_to_builtin(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    for _ in range(MAX_ATTEMPTS):
        _activate()
    assert _activate() == (None, False)
    assert os.environ[LAYER_ENV] == BUILTIN
    assert read_active(home).failed == "0.6.0-0000002"


def test_changed_file_falls_back(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    (home / "0.6.0-0000002" / "app" / "fakeapp" / "__init__.py").write_text("COMMIT = 'x'\n")
    assert _activate() == (None, False)
    assert read_active(home).failed == "0.6.0-0000002"
    assert "file_mismatch" in (home / LOG_FILE).read_text(encoding="utf-8")


def test_extra_file_falls_back(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    (home / "0.6.0-0000002" / "app" / "fakeapp" / "extra.py").write_text("")
    assert _activate() == (None, False)


def test_reinstalled_app_uses_builtin_code(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    confirm(home, "0.6.0-0000002")
    reinstalled = Runtime(TARGET, RUNTIME.id, (KEY,), release="0.6.1-0000009")
    os.environ.pop(LAYER_ENV, None)
    assert activate(reinstalled) == (None, False)
    assert read_active(home) == Active(installed_with="0.6.1-0000009")


def test_child_uses_the_parent_layer(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    layer, _ = _activate()
    assert layer is not None
    install_layer(home, _update(tmp_path, "0000003"), RUNTIME, protect=[layer.release])
    # 子程序：父程序指定的那一層，不重新選擇，也不計算啟動次數
    os.environ[LAYER_ENV] = layer.release
    attempts = read_active(home).attempts
    child, pending = activate(RUNTIME)
    assert child is not None
    assert child.release == "0.6.0-0000002"
    assert not pending
    assert read_active(home).attempts == attempts
    os.environ[LAYER_ENV] = BUILTIN
    assert activate(RUNTIME) == (None, False)


def test_missing_pinned_layer_chooses_again(tmp_path: Path, home: Path) -> None:
    install_layer(home, _update(tmp_path, "0000002"), RUNTIME)
    os.environ[LAYER_ENV] = "0.6.0-0000009"
    layer, _ = activate(RUNTIME)
    assert layer is not None
    assert layer.release == "0.6.0-0000002"


@pytest.mark.parametrize("release", ["../outside", "a/b", "..", ""])
def test_layer_name_must_be_safe(home: Path, release: str) -> None:
    with pytest.raises(UpdateError, match="unsafe_path"):
        load_layer(home, release, RUNTIME)


def test_bad_active_file_means_builtin(home: Path) -> None:
    home.mkdir(parents=True)
    (home / ACTIVE_FILE).write_text("not json")
    assert read_active(home) == Active()
    assert _activate() == (None, False)


def test_development_environment_does_nothing(home: Path) -> None:
    assert activate(None) == (None, False)  # 開發環境沒有 runtime.json
    server = Runtime("server-linux-x64", RUNTIME.id, (KEY,))
    assert activate(server) == (None, False)
    assert LAYER_ENV not in os.environ


def test_prune_keeps_newest_and_protected(tmp_path: Path, home: Path) -> None:
    for index, commit in enumerate(("0000002", "0000003", "0000004", "0000005")):
        install_layer(home, _update(tmp_path, commit), RUNTIME, keep=10)
        stamp = time.time() - 100 + index
        os.utime(home / f"0.6.0-{commit}", (stamp, stamp))
    staging = home / ".staging-old"
    staging.mkdir()
    os.utime(staging, (time.time() - 7200, time.time() - 7200))
    removed = prune(home, keep=2, protect=["0.6.0-0000002"])
    assert removed == ["0.6.0-0000003"]
    assert not staging.exists()
    names = sorted(path.name for path in home.iterdir() if path.is_dir())
    assert names == ["0.6.0-0000002", "0.6.0-0000004", "0.6.0-0000005"]


def test_boot_install_and_run(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(boot, "load_runtime", lambda: RUNTIME)
    monkeypatch.setattr(layers, "load_runtime", lambda: RUNTIME)
    monkeypatch.setattr(boot, "APP_MODULE", "fakeapp")
    update = _update(tmp_path, "0000002")
    assert boot.main([boot.INSTALL_FLAG, str(update)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "version": "0.6.0",
        "release": "0.6.0-0000002",
        "previous": None,
        "already": False,
    }
    assert boot.main(["--anything"]) == 0
    assert capsys.readouterr().out == "0000002"
    # 正常結束：確認了
    assert read_active(home).pending is False


def test_boot_does_not_confirm_a_failing_run(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(layers, "load_runtime", lambda: RUNTIME)
    monkeypatch.setattr(boot, "APP_MODULE", "fakeapp")
    install_layer(home, _update(tmp_path, "0000002", code="raise SystemExit(3)\n"), RUNTIME)
    assert boot.main([]) == 3
    assert read_active(home).pending


def test_boot_install_reports_errors(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(boot, "load_runtime", lambda: None)
    assert boot.main([boot.INSTALL_FLAG, str(tmp_path / "x.zip")]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "not_packaged"}
    monkeypatch.setattr(boot, "load_runtime", lambda: RUNTIME)
    other = _update(tmp_path, "0000002", runtimes={TARGET: "f" * 16})
    assert boot.main([boot.INSTALL_FLAG, str(other)]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "runtime_changed"
    assert boot.main([boot.INSTALL_FLAG]) == 2
