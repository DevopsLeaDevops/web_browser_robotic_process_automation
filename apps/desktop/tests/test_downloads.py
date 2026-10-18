"""下載瀏覽器（rpa_desktop.downloads）：進度解析、輸出與結束碼。不真的下載。"""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from rpa_desktop import downloads
from rpa_desktop.downloads import download_browser, driver_command, parse_percent
from rpa_desktop.logs import redact

BAR = "|■■■■■■■■                                                                        |"


def test_parse_percent() -> None:
    assert parse_percent(f"{BAR}  10% of 167.3 MiB") == 10
    assert parse_percent(f"{BAR}  10% of 1 MiB\r{BAR} 100% of 167.3 MiB") == 100
    assert (
        parse_percent("Downloading Chromium 140.0 (playwright build v1187) from https://x") is None
    )
    assert parse_percent("50% done") is None  # 不是 Playwright 的進度列


def test_driver_command_points_at_the_bundled_driver() -> None:
    command = driver_command(["install", "chromium"])
    assert command[-2:] == ["install", "chromium"]
    assert len(command) == 4 or command[1:3] == ["-m", "playwright"]


def test_progress_lines_are_reported_and_other_lines_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "fake_driver.py"
    script.write_text(
        "import sys\n"
        "w = sys.stdout.write\n"
        "w('Downloading Chromium 140.0 from https://example\\n')\n"
        f"w('{BAR}  10% of 167.3 MiB\\r')\n"
        f"w('{BAR}  10% of 167.3 MiB\\r')\n"
        f"w('{BAR}  60% of 167.3 MiB\\n')\n"
        f"w('{BAR} 100% of 167.3 MiB\\n')\n"
        "w('Chromium downloaded to /x\\n')\n"
        "sys.exit(int(sys.argv[-1] == 'firefox'))\n",
        encoding="utf-8",
    )

    def fake_driver(args: list[str]) -> list[str]:
        return [sys.executable, str(script), *args]

    monkeypatch.setattr(downloads, "driver_command", fake_driver)
    seen: list[int | None] = []

    result = download_browser("chromium", seen.append, {"PATH": ""})

    assert result.code == 0
    assert seen == [None, 10, 60, 100]  # 同一個百分比只報一次
    assert "Downloading Chromium" in result.tail
    assert "downloaded to" in result.tail
    assert "%" not in result.tail
    assert download_browser("firefox", seen.append, {}).code == 1


def test_environment_is_passed_and_no_console_flag_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def popen(command: Sequence[str], **kwargs: object) -> subprocess.Popen[bytes]:
        captured.update(kwargs)
        return subprocess.Popen(
            [sys.executable, "-c", "pass"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

    def fake_driver(args: list[str]) -> list[str]:
        return ["driver", *args]

    monkeypatch.setattr(downloads, "driver_command", fake_driver)
    download_browser(
        "chromium", lambda percent: None, {"PLAYWRIGHT_DOWNLOAD_HOST": "http://m"}, popen=popen
    )
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PLAYWRIGHT_DOWNLOAD_HOST"] == "http://m"
    assert captured["creationflags"] == 0  # 只有打包後的 Windows 才不開主控台


def test_logs_never_contain_invite_codes_or_tokens() -> None:
    line = "pair rpa://pair?server=http://x:8081&app=worker&code=abcdefghijklmnop failed"
    assert "abcdefghijklmnop" not in redact(line)
    assert "server=http://x:8081" in redact(line)
    assert "s3cr3t-token-value" not in redact("Authorization: Bearer s3cr3t-token-value")
    assert "abcdef123456" not in redact('{"token": "abcdef123456"}')
    assert redact("nothing secret here") == "nothing secret here"
