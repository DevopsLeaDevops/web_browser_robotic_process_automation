"""伺服器設定：能不能顯示瀏覽器視窗（有頭模式）。"""

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
