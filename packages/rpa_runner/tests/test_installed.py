"""瀏覽器還沒下載：說明要執行的命令，而不是 Playwright 的英文提示框。

用 PLAYWRIGHT_BROWSERS_PATH 指向空資料夾模擬「還沒下載」，不需要真的瀏覽器。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.files import AUTOMATION_LOG, OUTPUT, RESULT
from rpa_runner.installed import missing_browser_hint, missing_browsers
from rpa_runner.run import execute

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"
BA_001_SCRIPT = ROOT / "scenarios" / "demo" / "ba-001-script" / "scenario.yaml"
NOWHERE = "http://127.0.0.1:9/"

# 使用者在 macOS 上實際看到的錯誤（Playwright 1.63）
MACOS_FIREFOX = (
    "BrowserType.launch: Executable doesn't exist at "
    "/Users/someone/Library/Caches/ms-playwright/firefox-1543/firefox/Nightly.app/Contents/MacOS/firefox\n"
    "╔════════════════════════════════════════════════════════════╗\n"
    "║ Looks like Playwright was just installed or updated.       ║\n"
    "║ Please run the following command to download new browsers: ║\n"
    "║                                                            ║\n"
    "║     playwright install                                     ║\n"
    "╚════════════════════════════════════════════════════════════╝"
)


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


@pytest.fixture
def no_browsers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """這台電腦「還沒下載」任何瀏覽器（子程序繼承環境變數）。"""
    empty = tmp_path / "ms-playwright"
    empty.mkdir()
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(empty))
    return empty


# ---------------------------------------------------------------- 認出錯誤


def test_hint_names_the_browser_and_the_command() -> None:
    hint = missing_browser_hint(MACOS_FIREFOX)

    assert hint is not None
    assert "還沒有下載 Firefox" in hint
    assert "uv run playwright install firefox" in hint
    assert "╔" not in hint


@pytest.mark.parametrize(
    ("path", "command"),
    [
        (
            "/home/u/.cache/ms-playwright/chromium_headless_shell-1200/chrome-linux/headless_shell",
            "uv run playwright install chromium",
        ),
        # 使用者名稱裡的字不算：只看「名稱-版本號」資料夾
        (
            r"C:\Users\firefox\AppData\Local\ms-playwright\chromium-1200\chrome-win\chrome.exe",
            "uv run playwright install chromium",
        ),
        ("/opt/pw-browsers/webkit-2200/pw_run.sh", "uv run playwright install webkit"),
        # 認不出是哪個瀏覽器時，兩個都下載
        ("/opt/browsers/unknown/bin/browser", "uv run playwright install chromium firefox"),
    ],
)
def test_hint_reads_the_browser_from_the_path(path: str, command: str) -> None:
    error = f"BrowserType.launch_persistent_context: Executable doesn't exist at {path}"
    hint = missing_browser_hint(error)

    assert hint is not None
    assert command in hint


def test_other_errors_are_left_alone() -> None:
    assert missing_browser_hint("TimeoutError: Locator.click: Timeout 10000ms exceeded.") is None
    assert missing_browser_hint("") is None


def test_hint_in_english() -> None:
    with use_locale("en"):
        hint = missing_browser_hint(MACOS_FIREFOX)

    assert hint is not None
    assert hint.startswith("Firefox has not been downloaded")


# ---------------------------------------------------------------- 事先檢查


@pytest.mark.usefixtures("no_browsers")
def test_missing_browsers_without_launching() -> None:
    assert missing_browsers() == ["chromium", "firefox"]


def test_missing_browsers_never_raises() -> None:
    assert missing_browsers(["no-such-browser"]) == []


# ---------------------------------------------------------------- 執行場景


@pytest.mark.usefixtures("no_browsers")
@pytest.mark.parametrize("scenario", [BA_001, BA_001_SCRIPT], ids=["dsl", "script"])
def test_run_explains_how_to_download_the_browser(scenario: Path, tmp_path: Path) -> None:
    result = execute(
        scenario,
        {"title": "缺瀏覽器", "quantity": 1},
        out_root=tmp_path / "runs",
        base_url=NOWHERE,
        engine="firefox",
    )

    automation = result.stage("automation")
    assert result.status == "failed"
    assert automation.status == "failed"
    assert automation.message is not None
    assert "還沒有下載 Firefox" in automation.message
    assert "uv run playwright install firefox" in automation.message
    # 管理 Portal 顯示的錯誤只有怎麼修，沒有結束碼與英文提示框
    assert result.error == automation.message
    assert result.stage("verify").status == "skipped"
    assert not (result.directory / OUTPUT).exists()
    assert (result.directory / RESULT).is_file()
    # 原始錯誤仍留在日誌
    log = (result.directory / AUTOMATION_LOG).read_text(encoding="utf-8", errors="replace")
    assert "Executable doesn't exist" in log
