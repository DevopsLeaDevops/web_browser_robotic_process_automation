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
from rpa_desktop.i18n import t
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
    subprocess.run([node, "--check", str(UI / "worker.js")], check=True)


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
