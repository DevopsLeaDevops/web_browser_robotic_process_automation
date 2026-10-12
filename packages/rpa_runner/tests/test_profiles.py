"""Firefox 預熱設定檔：範本只建立一次、每次執行用自己的複本、用完刪除、做不到時照舊啟動。

不需要瀏覽器的部分用假的「初始化」函式；最後一個測試用真的 Firefox 跑 BA-001。
"""

import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from playwright.sync_api import Playwright

from rpa_core.i18n import use_locale
from rpa_runner.profiles import (
    MIN_BUDGET_SECONDS,
    READY,
    cache_dir,
    copy_profile,
    ensure_template,
    firefox_profile,
    prune,
    template_key,
)
from rpa_runner.run import execute
from testsite.browsers import require_engine
from testsite.server import running

ROOT = Path(__file__).resolve().parents[3]
BA_001 = ROOT / "scenarios" / "demo" / "ba-001.yaml"


class Warm:
    """假的初始化：寫幾個 Firefox 設定檔會有的檔案，記錄被呼叫幾次。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, folder: Path) -> None:
        self.calls += 1
        (folder / "prefs.js").write_text("// prefs", encoding="utf-8")
        (folder / "storage").mkdir()
        (folder / "storage" / "ls-archive.sqlite").write_bytes(b"db")
        (folder / "parent.lock").write_bytes(b"")


def fake_playwright(executable: Path) -> Playwright:
    return cast("Playwright", SimpleNamespace(firefox=SimpleNamespace(executable_path=executable)))


@pytest.fixture
def executable(tmp_path: Path) -> Path:
    path = tmp_path / "firefox" / "firefox.exe"
    path.parent.mkdir()
    path.write_bytes(b"firefox")
    return path


# ---------------------------------------------------------------- 快取資料夾


@pytest.mark.parametrize(
    ("environ", "platform", "expected"),
    [
        ({"RPA_CACHE_DIR": "/srv/cache"}, "linux", "/srv/cache"),
        ({"LOCALAPPDATA": "/w/AppData/Local"}, "win32", "/w/AppData/Local/rpa/cache"),
        ({}, "win32", "/home/u/AppData/Local/rpa/cache"),
        ({}, "darwin", "/home/u/Library/Caches/rpa"),
        ({"XDG_CACHE_HOME": "/x"}, "linux", "/x/rpa"),
        ({}, "linux", "/home/u/.cache/rpa"),
    ],
)
def test_cache_dir(environ: dict[str, str], platform: str, expected: str) -> None:
    assert cache_dir(environ, platform, Path("/home/u")) == Path(expected)


def test_template_key_follows_the_firefox_build(executable: Path) -> None:
    first = template_key(executable)
    assert first == template_key(executable)
    executable.write_bytes(b"firefox, a newer build")
    assert template_key(executable) != first
    assert len(template_key(executable.parent / "missing.exe")) == 16


# ---------------------------------------------------------------- 範本


def test_template_is_created_once_and_reused(tmp_path: Path) -> None:
    warm = Warm()
    first = ensure_template(tmp_path, "k", warm)
    second = ensure_template(tmp_path, "k", warm)

    assert first == second == tmp_path / "k"
    assert warm.calls == 1
    assert (first / READY).is_file()
    assert (first / "prefs.js").is_file()
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["k"]  # 暫存資料夾已清掉


def test_incomplete_template_is_rebuilt(tmp_path: Path) -> None:
    (tmp_path / "k").mkdir()
    (tmp_path / "k" / "half-written").write_text("?", encoding="utf-8")
    warm = Warm()

    template = ensure_template(tmp_path, "k", warm)

    assert warm.calls == 1
    assert not (template / "half-written").exists()
    assert (template / READY).is_file()


def test_another_run_finishing_first_wins(tmp_path: Path) -> None:
    """兩個執行同時建立：先完成的被採用，後完成的丟掉自己的暫存資料夾。"""

    def warm(folder: Path) -> None:
        other = tmp_path / "k"
        other.mkdir()
        (other / "from-the-other-run").write_text("1", encoding="utf-8")
        (other / READY).write_text("k", encoding="utf-8")
        (folder / "from-this-run").write_text("2", encoding="utf-8")

    template = ensure_template(tmp_path, "k", warm)

    assert (template / "from-the-other-run").is_file()
    assert not (template / "from-this-run").exists()
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["k"]


def test_failed_warmup_leaves_nothing_behind(tmp_path: Path) -> None:
    def warm(folder: Path) -> None:
        (folder / "prefs.js").write_text("", encoding="utf-8")
        raise RuntimeError("Firefox 無法啟動")

    with pytest.raises(RuntimeError):
        ensure_template(tmp_path, "k", warm)
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- 複本


def test_copy_has_the_profile_but_no_lock_or_marker(tmp_path: Path) -> None:
    template = ensure_template(tmp_path / "templates", "k", Warm())

    first = copy_profile(template, tmp_path / "runs")
    second = copy_profile(template, tmp_path / "runs")

    assert first != second
    assert (first / "prefs.js").is_file()
    assert (first / "storage" / "ls-archive.sqlite").is_file()
    assert not (first / "parent.lock").exists()
    assert not (first / READY).exists()


def test_prune_removes_only_stale_entries(tmp_path: Path) -> None:
    old, recent = tmp_path / "old", tmp_path / "recent"
    for folder in (old, recent):
        folder.mkdir()
        (folder / "prefs.js").write_text("", encoding="utf-8")
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))

    prune(tmp_path)

    assert not old.exists()
    assert recent.exists()


# ---------------------------------------------------------------- 一次執行


def test_each_run_gets_its_own_copy_and_it_is_removed(tmp_path: Path, executable: Path) -> None:
    warm = Warm()
    playwright = fake_playwright(executable)
    runs = tmp_path / "firefox-profile" / "runs"

    with firefox_profile(playwright, budget_seconds=45, root=tmp_path, warm=warm) as first:
        assert first is not None
        assert first.parent == runs
        assert (first / "prefs.js").is_file()
        with firefox_profile(playwright, budget_seconds=45, root=tmp_path, warm=warm) as second:
            assert second is not None
            assert second != first
    assert warm.calls == 1
    assert list(runs.iterdir()) == []


def test_short_deadline_does_not_build_the_template(tmp_path: Path, executable: Path) -> None:
    warm = Warm()
    playwright = fake_playwright(executable)
    short = MIN_BUDGET_SECONDS - 1

    with firefox_profile(playwright, budget_seconds=short, root=tmp_path, warm=warm) as profile:
        assert profile is None
    assert warm.calls == 0

    # 範本已經在時，期限短也照樣用
    with firefox_profile(playwright, budget_seconds=45, root=tmp_path, warm=warm):
        pass
    with firefox_profile(playwright, budget_seconds=short, root=tmp_path, warm=warm) as profile:
        assert profile is not None
    assert warm.calls == 1


def test_problems_fall_back_to_a_fresh_profile(
    tmp_path: Path, executable: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def warm(folder: Path) -> None:
        raise OSError("磁碟已滿")

    playwright = fake_playwright(executable)
    with firefox_profile(playwright, budget_seconds=45, root=tmp_path, warm=warm) as profile:
        assert profile is None
    assert "改用全新設定檔：磁碟已滿" in capsys.readouterr().err


# ---------------------------------------------------------------- 真的 Firefox


@pytest.mark.browser
def test_firefox_run_uses_a_copy_of_the_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_engine("firefox")
    cache = tmp_path / "cache"
    monkeypatch.setenv("RPA_CACHE_DIR", str(cache))  # 子程序繼承環境變數

    with running() as site, use_locale("zh-Hant"):
        first = execute(
            BA_001,
            {"title": "預熱設定檔", "quantity": 2},
            out_root=tmp_path,
            base_url=site,
            engine="firefox",
        )
        second = execute(
            BA_001,
            {"title": "第二次", "quantity": 3},
            out_root=tmp_path,
            base_url=site,
            engine="firefox",
        )

    assert first.status == "passed", first.error
    assert second.status == "passed", second.error
    profiles = cache / "firefox-profile"
    templates = [entry for entry in profiles.iterdir() if (entry / READY).is_file()]
    assert len(templates) == 1  # 第二次沿用第一次建立的範本
    assert list((profiles / "runs").iterdir()) == []  # 每次的複本都刪掉了
    assert "改用全新設定檔" not in (first.directory / "automation.log").read_text(encoding="utf-8")
