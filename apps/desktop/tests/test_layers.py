"""啟動器（rpa_update.layers）和兩個 App 用同一個資料夾（ADR 0018）。

啟動器不能匯入 rpa_desktop，所以另外寫了一份找資料夾的規則；這裡核對兩份一致。
"""

from pathlib import Path

import pytest

from rpa_desktop.recorder_gui import ENV_HOME as RECORDER_HOME
from rpa_desktop.recorder_gui import recorder_dir
from rpa_desktop.worker_app import ENV_HOME as WORKER_HOME
from rpa_desktop.worker_app import data_dir
from rpa_update.layers import HOME_ENVS, app_home

ENVIRONS = [
    {"LOCALAPPDATA": r"C:\Users\amy\AppData\Local", "USERPROFILE": r"C:\Users\amy"},
    {"USERPROFILE": r"C:\Users\amy", "HOME": "/home/other"},
    {"HOME": "/Users/amy"},
    {"HOME": "/home/amy", "XDG_DATA_HOME": "/data/amy"},
    {WORKER_HOME: "~/w", RECORDER_HOME: "/tmp/r", "HOME": "/home/amy"},
]


def test_home_variables_match() -> None:
    assert HOME_ENVS == {"worker": WORKER_HOME, "recorder": RECORDER_HOME}


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("environ", ENVIRONS)
def test_same_folder_as_the_apps(platform: str, environ: dict[str, str]) -> None:
    assert app_home("worker", environ, platform) == data_dir(environ, platform)
    assert app_home("recorder", environ, platform) == recorder_dir(environ, platform)
    assert isinstance(app_home("worker", environ, platform), Path)
