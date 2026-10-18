"""RPA Worker 的安裝檔（apps/desktop/packaging/rpa_worker.iss、tools/build_desktop.py）。

真的用 ISCC 編譯、安裝、升級、解除安裝在 CI 的 Windows（桌面端建置）。這裡在任何系統上確認
安裝檔和 App 用的名稱、路徑、旗標一致，以及安裝檔的訊息從訊息目錄正確產生。
"""

import re
from pathlib import Path

import pytest

from rpa_core.i18n import LOCALES
from rpa_desktop import autostart, entry, gui, release, single_instance
from rpa_desktop.i18n import t
from rpa_desktop.worker_app import data_dir
from tools import build_desktop as build

SCRIPT = build.INSTALLER_SCRIPT.read_text(encoding="utf-8")


def define(name: str) -> str:
    match = re.search(rf'^#define {name} "([^"]*)"$', SCRIPT, re.MULTILINE)
    assert match is not None, name
    return match.group(1)


def test_names_match_the_app() -> None:
    assert define("AppMutexName") == single_instance.APP_MUTEX
    assert define("StopFile") == single_instance.STOP_FILE
    assert define("RunKey") == autostart.RUN_KEY
    assert define("RunValue") == autostart.VALUE_NAME
    assert define("WebView2Client") == gui._WEBVIEW2_CLIENT  # pyright: ignore[reportPrivateUsage]
    assert define("AppExe") == build.EXECUTABLES["worker"] + ".exe"
    assert define("ChildExe") == "rpa-child.exe"
    assert define("Repository") == release.REPOSITORY
    assert f"'{entry.FORGET_FLAG}'" in SCRIPT
    assert "--background" not in SCRIPT  # 自動啟動由 App 自己寫，安裝檔只負責刪除


def test_data_folder_matches_the_app() -> None:
    expected = data_dir({"LOCALAPPDATA": r"C:\Users\amy\AppData\Local"}, platform="win32")
    assert str(expected).replace("/", "\\").endswith(r"rpa\worker")
    assert r"ExpandConstant('{localappdata}\rpa\worker')" in SCRIPT
    assert "GetEnv('RPA_WORKER_HOME')" in SCRIPT  # 和 App 一樣，環境變數優先


def test_defines_and_languages_match_the_build_tool(tmp_path: Path) -> None:
    defines = build.iscc_defines(
        version="1.2.3",
        source=tmp_path,
        output=tmp_path,
        icon=tmp_path / "a.ico",
        languages=tmp_path,
        webview2=tmp_path / build.WEBVIEW2_FILE,
        messages=tmp_path / "messages.iss",
    )
    names = {item.removeprefix("/D").split("=", 1)[0] for item in defines}
    used = set(re.findall(r"\{#(\w+)\}", SCRIPT)) | set(re.findall(r"#include (\w+)", SCRIPT))
    used |= set(re.findall(r"ExtractFileName\((\w+)\)", SCRIPT))
    defined_here = set(re.findall(r"^#define (\w+)", SCRIPT, re.MULTILINE))
    assert used - defined_here == names  # 每個用到的外部定義都由建置工具給
    languages = re.findall(r'^Name: "(\w+)"; MessagesFile:', SCRIPT, re.MULTILINE)
    assert languages == ["zht", "zhs", "en"]  # 繁中排第一：預設語言（ADR 0007）
    assert set(languages) == set(build.INNO_LANGUAGES.values())
    for name in build.TRANSLATIONS:
        assert f"{{#LangDir}}\\{name}" in SCRIPT
    assert "OutputBaseFilename=RPA-Worker-Setup-{#AppVersion}-windows-x64" in SCRIPT
    assert build.installer_path("1.2.3").name.startswith("RPA-Worker-Setup-1.2.3-")


def test_installer_messages_cover_every_language() -> None:
    text = build.installer_messages({locale: t.messages(locale) for locale in LOCALES})
    lines = text.splitlines()
    assert lines[1] == "[CustomMessages]"
    used = set(re.findall(r"CustomMessage\('(\w+)'\)", SCRIPT))
    assert used == {
        "Stopping",
        "StillRunning",
        "WebView2Installing",
        "WebView2Failed",
        "RemoveData",
    }
    for language in build.INNO_LANGUAGES.values():
        defined = {
            line.split("=", 1)[0].split(".", 1)[1]
            for line in lines
            if line.startswith(f"{language}.")
        }
        assert used <= defined, language
    english = dict(line.split("=", 1) for line in lines if line.startswith("en."))
    assert "%1" in english["en.WebView2Failed"]  # Inno Setup 的參數照原樣保留
    assert "%n%n" in english["en.RemoveData"]


def test_installer_messages_reject_bad_entries() -> None:
    with pytest.raises(ValueError, match="英數字"):
        build.installer_messages({"zh-Hant": {"installer.bad-name": "x"}, "zh-Hans": {}, "en": {}})
    with pytest.raises(ValueError, match="換行"):
        build.installer_messages({"zh-Hant": {"installer.Two": "a\nb"}, "zh-Hans": {}, "en": {}})


def test_translations_are_pinned() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", build.ISSRC_COMMIT)
    for name, digest in build.TRANSLATIONS.items():
        assert name.endswith(".isl")
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
