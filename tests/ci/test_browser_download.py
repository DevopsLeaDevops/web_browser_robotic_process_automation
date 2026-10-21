"""瀏覽器選源：離線測試真實 HTTP 邊界、安裝環境、快取與失敗回退。"""

import os
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tools import install_browsers as browser

OFFICIAL = "https://cdn.playwright.dev"


def artifact(tmp_path: Path, name: str = "firefox", *, installed: bool = False) -> browser.Artifact:
    location = tmp_path / name
    if installed:
        location.mkdir()
        (location / "INSTALLATION_COMPLETE").touch()
    return browser.Artifact(name, location, (f"{OFFICIAL}/builds/{name}/123/archive.zip",))


def plan(item: browser.Artifact) -> str:
    return (
        f"Browser (playwright {item.name} v123)\n"
        f"  Install location:    {item.location}\n"
        f"  Download url:        {item.urls[0]}\n\n"
    )


@pytest.mark.parametrize(
    ("name", "suffix", "location"),
    [
        ("chromium", "cft/156.0/mac-arm64/chrome-mac-arm64.zip", "/cache/含 空格/chromium-1"),
        (
            "chromium-headless-shell",
            "cft/156.0/win64/chrome-headless-shell-win64.zip",
            r"C:\cache\shell",
        ),
        ("firefox", "firefox/1555/firefox-ubuntu-24.04.zip", "/cache/firefox-1555"),
        ("ffmpeg", "ffmpeg/1013/ffmpeg-win64.zip", r"C:\cache\ffmpeg"),
    ],
)
def test_plan_uses_version_platform_and_paths_from_playwright(
    name: str, suffix: str, location: str
) -> None:
    text = f"""Browser (playwright {name} v123)
  Install location:    {location}
  Download url:        https://cdn.playwright.dev/builds/{suffix}
  Download fallback 1: https://example.test/builds/{suffix}
"""
    (item,) = browser.parse_plan(text)
    assert item.relative_url == "builds/" + suffix
    assert item.location == Path(location)
    assert browser.candidates([item]) == [OFFICIAL, "https://example.test", browser.MIRROR]


@pytest.mark.parametrize(
    "text", ["", "new output format", "Browser\nDownload url: https://example.test/x"]
)
def test_unrecognised_plan_fails_safely(text: str) -> None:
    with pytest.raises(ValueError, match="Playwright"):
        browser.parse_plan(text)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    data = b"PK\x03\x04" + b"x" * 4092
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/range")
                self.end_headers()
                return
            if self.path == "/missing":
                self.send_error(404)
                return
            payload = b"<html>error</html>" if self.path == "/html" else data
            partial = self.path in ("/range", "/bad-range")
            self.send_response(206 if partial else 200)
            self.send_header("Content-Length", str(len(payload)))
            if partial:
                self.send_header(
                    "Content-Range", f"bytes {'1' if self.path == '/bad-range' else '0'}-4095/4096"
                )
            self.end_headers()
            if self.path == "/slow":
                time.sleep(1)
            if self.path == "/truncated":
                payload = b"PK"
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


@pytest.mark.parametrize("path", ["/range", "/no-range", "/redirect"])
def test_probe_accepts_binary_with_or_without_range(server: str, path: str) -> None:
    sample = browser.probe(server + path, 3)
    assert sample is not None
    assert sample.size == sample.total == 4096
    assert len(sample.digest) == 64
    assert sample.elapsed > 0


@pytest.mark.parametrize("path", ["/missing", "/html", "/truncated", "/bad-range"])
def test_probe_rejects_false_success_and_incomplete_content(server: str, path: str) -> None:
    assert browser.probe(server + path, 3) is None


def test_slow_probe_is_killed_at_deadline(server: str) -> None:
    start = time.monotonic()
    assert browser.probe(server + "/slow", 0.2) is None
    assert time.monotonic() - start < 0.8


@pytest.mark.parametrize("bad_mirror", [False, True])
def test_selects_fastest_matching_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_mirror: bool
) -> None:
    item = artifact(tmp_path)

    def probe(url: str, timeout: float) -> browser.Sample:
        mirror = url.startswith(browser.MIRROR)
        return browser.Sample(
            1000, 0.1 if mirror else 1, "bad" if mirror and bad_mirror else "ok", 5000
        )

    monkeypatch.setattr(browser, "probe", probe)
    assert browser.choose_host([item], time.monotonic() + 5) == (
        OFFICIAL if bad_mirror else browser.MIRROR
    )


def test_mirror_missing_headless_shell_cannot_win(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [artifact(tmp_path, name) for name in ("chromium", "chromium-headless-shell")]

    def probe(url: str, timeout: float) -> browser.Sample | None:
        if url.startswith(browser.MIRROR) and "headless" in url:
            return None
        return browser.Sample(1000, 0.01 if url.startswith(browser.MIRROR) else 1, "ok", 5000)

    monkeypatch.setattr(browser, "probe", probe)
    assert browser.choose_host(items, time.monotonic() + 5) == OFFICIAL


def test_cached_components_and_exhausted_budget_do_not_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: object) -> None:
        pytest.fail("不應執行網路探測")

    monkeypatch.setattr(browser, "probe", unexpected)
    assert browser.select_hosts([artifact(tmp_path, installed=True)]) == {}
    assert browser.choose_host([artifact(tmp_path)], time.monotonic() - 1) is None


def test_directory_without_completion_marker_is_not_installed(tmp_path: Path) -> None:
    item = artifact(tmp_path)
    item.location.mkdir()
    assert not item.installed


def test_failed_browser_probe_keeps_original_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [artifact(tmp_path, name) for name in ("chromium", "firefox", "ffmpeg")]
    calls: list[str] = []

    def choose(group: Sequence[browser.Artifact], deadline: float) -> str | None:
        calls.append(group[0].name)
        return None if group[0].name == "firefox" else browser.MIRROR

    monkeypatch.setattr(browser, "choose_host", choose)
    assert browser.select_hosts(items) == {"PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST": browser.MIRROR}
    assert calls == ["chromium", "firefox"]


@pytest.mark.parametrize("key", [*browser.HOST_KEYS, "npm_config_playwright_download_host"])
def test_explicit_source_skips_probes_and_is_preserved(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {key: "https://company.example.test/mirror"}
    monkeypatch.setattr(browser.os, "environ", env)

    def run(*args: object, **kwargs: object) -> None:
        pytest.fail("指定來源時不應執行 dry-run 或探測")

    def call(command: Sequence[str], *, env: Mapping[str, str]) -> int:
        assert env == {key: "https://company.example.test/mirror"}
        assert list(command) == browser.COMMAND
        return 7

    monkeypatch.setattr(browser.subprocess, "run", run)
    monkeypatch.setattr(browser.subprocess, "call", call)
    assert browser.install() == 7


def test_install_fallback_does_not_change_callers_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = {
        "HTTPS_PROXY": "http://proxy.example.test",
        "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path),
    }
    monkeypatch.setattr(browser.os, "environ", original)

    def run(command: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, plan(artifact(tmp_path)))

    def select(items: Sequence[browser.Artifact]) -> dict[str, str]:
        return {"PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST": browser.MIRROR}

    monkeypatch.setattr(browser.subprocess, "run", run)
    monkeypatch.setattr(browser, "select_hosts", select)
    calls: list[dict[str, str]] = []

    def call(command: Sequence[str], *, env: Mapping[str, str]) -> int:
        calls.append(dict(env))
        return 1 if len(calls) == 1 else 0

    monkeypatch.setattr(browser.subprocess, "call", call)
    assert browser.install() == 0
    assert calls == [{**original, "PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST": browser.MIRROR}, original]
    assert original == {
        "HTTPS_PROXY": "http://proxy.example.test",
        "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path),
    }


def test_changed_dry_run_format_uses_original_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser.os, "environ", {})

    def run(command: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "changed")

    def call(command: Sequence[str], **kwargs: object) -> int:
        return 0

    monkeypatch.setattr(browser.subprocess, "run", run)
    monkeypatch.setattr(browser.subprocess, "call", call)
    assert browser.install() == 0


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="需要 POSIX Bash")
def test_setup_browser_step_skips_or_runs_shared_installer(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts/setup.sh").read_text(encoding="utf-8")
    source = source.rsplit('\nmain ${1+"$@"}', 1)[0]
    harness = tmp_path / "setup-step.sh"
    harness.write_text(
        source
        + """
run() { printf '%s\\n' "$*" >> "$CALLS"; return 0; }
browser_launches() { return 0; }
SKIP_BROWSER=1
install_browser
test ! -e "$CALLS"
SKIP_BROWSER=0
install_browser
""",
        encoding="utf-8",
    )
    calls = tmp_path / "calls"
    result = subprocess.run(
        [shutil.which("bash") or "bash", str(harness)],
        env={**os.environ, "CALLS": str(calls)},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text().splitlines() == ["uv run python tools/install_browsers.py"]
