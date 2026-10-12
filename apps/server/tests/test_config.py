"""伺服器設定：能不能顯示瀏覽器視窗（有頭模式）、資料目錄。"""

from pathlib import Path

import pytest

from rpa_server.config import Settings, has_display


@pytest.mark.parametrize(
    ("environ", "platform", "expected"),
    [
        ({}, "win32", True),
        ({}, "darwin", True),
        ({}, "linux", False),
        ({"DISPLAY": ":0"}, "linux", True),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", True),
        ({"DISPLAY": ""}, "linux", False),
    ],
)
def test_has_display(environ: dict[str, str], platform: str, expected: bool) -> None:
    assert has_display(environ, platform) is expected


def test_settings_detect_the_display() -> None:
    settings = Settings.from_env(environ={"DISPLAY": ":1"})
    assert settings.display is has_display({"DISPLAY": ":1"})


def test_relative_data_dir_becomes_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rpa serve --data data-m4``：相對路徑以啟動時的資料夾為準，存成絕對路徑。

    錄製的 codegen 在錄製資料夾裡執行，相對路徑會被接在那個資料夾後面而找不到
    （使用者在 Mac 上遇到）。
    """
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env(data_dir=Path("data-m4"), environ={})
    assert settings.data_dir == tmp_path / "data-m4"
    assert Settings.from_env(environ={"RPA_DATA_DIR": "other"}).data_dir == tmp_path / "other"
    assert Settings.from_env(environ={}).data_dir == tmp_path / "data"
