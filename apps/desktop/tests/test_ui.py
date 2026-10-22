"""狀態視窗的頁面（rpa_desktop.ui）與圖示（rpa_desktop.icon）。

真的在 WebView2 裡打開視窗是 CI 的桌面端建置（``rpa-worker.exe --smoke-test``）。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import get_args

import pytest

from rpa_core.i18n import LOCALES
from rpa_desktop.controller import Phase
from rpa_desktop.i18n import platform_key, t
from rpa_desktop.icon import ICO_SIZES, draw, save_ico, status_color
from rpa_desktop.ui import page_strings, render_page

ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "apps" / "desktop" / "src" / "rpa_desktop" / "ui"
RUN_STATUSES = (
    "running",
    "passed",
    "failed",
    "timed_out",
    "cancelled",
    "needs_login",
    "crashed",
    "abandoned",
)


def test_portal_css_is_the_design_system_original() -> None:
    """改樣式先改 docs/design-system 再複製（和 Portal 相同的規則）。"""
    original = ROOT / "docs" / "design-system" / "assets" / "portal.css"
    assert (UI / "portal.css").read_bytes() == original.read_bytes()


@pytest.mark.parametrize("locale", LOCALES)
def test_page_is_complete_in_every_language(locale: str) -> None:
    html = render_page(locale)  # type: ignore[arg-type]
    assert f'<html lang="{locale}">' in html
    assert not re.search(r"__[A-Z_]+__", html)  # 標記都換掉了
    match = re.search(r'<script id="strings" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    strings = json.loads(match.group(1))
    assert strings == page_strings(locale)  # type: ignore[arg-type]
    keys = set(re.findall(r'data-(?:text|placeholder)="([^"]+)"', html))
    keys |= set(
        re.findall(r'text\("(window\.[a-z_.]+)"', (UI / "worker.js").read_text(encoding="utf-8"))
    )
    # 結尾是「.」的是動態鍵的前綴（window.phase.…），由下一個測試逐一確認
    missing = sorted(key for key in keys if key not in strings and not key.endswith("."))
    assert missing == []


def test_every_phase_and_result_has_a_label() -> None:
    strings = page_strings("en")
    for phase in get_args(Phase):
        assert f"window.phase.{phase}" in strings
    for status in RUN_STATUSES:
        assert f"window.status.{status}" in strings


def test_strings_cannot_close_the_script_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    original = t.messages

    def messages(locale: str) -> dict[str, str]:
        return {**original(locale), "window.title": "</script><b>x</b>"}  # type: ignore[arg-type]

    monkeypatch.setattr(t, "messages", messages)
    html = render_page("en")
    assert "</script><b>" not in html
    assert "<\\/script><b>x<\\/b>" in html


def test_page_script_parses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("沒有 Node.js")
    for script in ("worker.js", "recorder.js"):
        subprocess.run([node, "--check", str(UI / script)], check=True)


def test_icon_sizes_and_status_colors(tmp_path: Path) -> None:
    assert draw(64).size == (64, 64)
    assert draw(16, status_color("online")).size == (16, 16)
    assert status_color("online") != status_color("paused") != status_color("offline")
    assert status_color("downloading") == status_color("starting")
    from PIL import Image

    path = save_ico(tmp_path / "app.ico")
    with Image.open(path) as ico:
        sizes = ico.info["sizes"]
    assert set(ICO_SIZES) <= set(sizes)


# ---------------------------------------------------------------- 各系統的說法


@pytest.mark.parametrize("locale", LOCALES)
def test_every_macos_wording_replaces_an_existing_message(locale: str) -> None:
    """``前綴.darwin.名稱`` 一定有對應的 ``前綴.名稱``（否則在 Windows 上就缺字）。"""
    messages = t.messages(locale)  # type: ignore[arg-type]
    variants = [key for key in messages if ".darwin." in key]
    assert variants
    for key in variants:
        prefix, _, name = key.partition(".darwin.")
        assert f"{prefix}.{name}" in messages, key
        assert set(re.findall(r"{(\w+)}", messages[key])) == set(
            re.findall(r"{(\w+)}", messages[f"{prefix}.{name}"])
        ), key


def test_macos_page_says_menu_bar_and_keychain() -> None:
    mac = page_strings("zh-Hant", platform="darwin")
    windows = page_strings("zh-Hant", platform="win32")
    assert mac["window.storage_keyring"] == "macOS 鑰匙圈"
    assert windows["window.storage_keyring"] == "Windows 認證管理員"
    assert "選單列" in mac["window.autostart_label"]
    assert "Windows" in windows["window.autostart_label"]
    assert "鑰匙圈" in mac["window.keyring_failed"]
    english = page_strings("en", platform="darwin")
    assert english["window.storage_keyring"] == "macOS Keychain"


def test_platform_key() -> None:
    assert platform_key("window.close_hint", "darwin") == "window.darwin.close_hint"
    assert platform_key("worker.already_running", "darwin") == "worker.darwin.already_running"
    assert platform_key("window.close_hint", "win32") == "window.close_hint"
    assert platform_key("window.title", "darwin") == "window.title"  # 沒有 macOS 的說法
    assert platform_key("nodot", "darwin") == "nodot"
