"""RPA Worker App 的設定檔（rpa_desktop.settings）。"""

import json
from pathlib import Path

from rpa_desktop.settings import Settings, load_settings, save_settings


def test_defaults_without_a_file(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "settings.json")
    assert settings == Settings()
    assert settings.language == "zh-Hant"  # 預設繁中，不跟隨作業系統（ADR 0007）


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "settings.json"
    chosen = Settings(
        language="en", firefox=True, download_host="http://mirror", tray_hint_shown=True
    )
    save_settings(path, chosen)
    assert load_settings(path) == chosen
    assert not path.with_suffix(".tmp").exists()


def test_bad_values_fall_back_one_by_one(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"language": "fr", "firefox": "yes", "download_host": " http://m ", "x": 1}),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.language == "zh-Hant"
    assert settings.firefox is False
    assert settings.download_host == "http://m"
    path.write_text("{broken", encoding="utf-8")
    assert load_settings(path) == Settings()
    path.write_text('"text"', encoding="utf-8")
    assert load_settings(path) == Settings()
