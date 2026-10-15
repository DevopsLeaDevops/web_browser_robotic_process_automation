"""建置資訊：建置時寫出、打包後讀回；開發環境當場計算（M10.0）。"""

import json
import sys
from pathlib import Path

import pytest

import rpa_desktop.build_info as build_info
from rpa_desktop.build_info import BuildInfo, current, load, write
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
    path = tmp_path / "build_info.json"
    written = write(path, "worker", commit="abc1234")
    assert written.app == "worker"
    assert written.built_at
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["commit"] == "abc1234"

    monkeypatch.setattr(build_info, "_bundled", lambda: path)
    assert load().app == "development"  # 開發環境不讀打包的檔案
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert load() == written


def test_unknown_values_fall_back() -> None:
    info = BuildInfo.from_json({"app": "server", "protocol": 2})
    assert info.app == "development"
    assert info.protocol == 2
    assert info.version == ""
    assert current("recorder").app == "recorder"
