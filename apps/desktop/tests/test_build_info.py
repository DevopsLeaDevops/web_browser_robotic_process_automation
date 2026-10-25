"""建置資訊：建置時寫出、打包後讀回；開發環境當場計算（M10.0）。"""

import json
import sys
from pathlib import Path

import pytest

from rpa_desktop.build_info import BuildInfo, current, load, shell_file, write
from rpa_update import layers
from rpa_update.manifest import Manifest
from rpa_worker.environment import PROTOCOL, code_fingerprint


def test_development_info_is_computed() -> None:
    info = load()
    assert info.app == "development"
    assert info.fingerprint == code_fingerprint()
    assert info.protocol == PROTOCOL
    assert info.built_at == ""


def test_written_info_is_read_back_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rpa_desktop" / "build_info.json"
    written = write(path, "worker", commit="abc1234")
    assert written.app == "worker"
    assert written.built_at
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["commit"] == "abc1234"

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert load().app == "development"  # 開發環境不讀打包的檔案
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert shell_file("build_info.json") == path
    assert load() == written


def test_code_layer_changes_version_but_not_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用更新檔裝的程式碼層（ADR 0018）：App 種類照舊，版本與指紋用那一層的清單。"""
    written = write(tmp_path / "rpa_desktop" / "build_info.json", "recorder", commit="abc1234")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    manifest = Manifest(
        version="0.6.0",
        commit="0000002",
        built_at="2026-10-25T09:00:00+00:00",
        fingerprint="f" * 16,
        protocol=PROTOCOL + 1,
        features=(),
        runtimes={},
        files={},
    )
    monkeypatch.setattr(layers, "_current", layers.Layer(tmp_path / "0.6.0-0000002", manifest))
    info = load()
    assert info == BuildInfo(
        app="recorder",
        version="0.6.0",
        fingerprint="f" * 16,
        protocol=PROTOCOL + 1,
        commit="0000002",
        built_at="2026-10-25T09:00:00+00:00",
    )
    assert written.app == info.app


def test_unknown_values_fall_back() -> None:
    info = BuildInfo.from_json({"app": "server", "protocol": 2})
    assert info.app == "development"
    assert info.protocol == 2
    assert info.version == ""
    assert current("recorder").app == "recorder"
