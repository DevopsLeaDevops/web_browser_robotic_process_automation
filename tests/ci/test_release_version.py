"""產品的版本（tools/release_version.py）：一次改全部套件、發布前的標籤檢查。"""

import shutil
from pathlib import Path

import pytest

from tools import release_version as tool

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """倉庫的 pyproject.toml 與 uv.lock 複本。"""
    for path in [*ROOT.glob("packages/*/pyproject.toml"), *ROOT.glob("apps/*/pyproject.toml")]:
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, target)
    shutil.copy(ROOT / "uv.lock", tmp_path / "uv.lock")
    return tmp_path


def test_repository_versions_are_consistent() -> None:
    version = tool.current()
    assert tool.check(f"v{version}") == []  # 倉庫隨時都可以用目前的版本發布


def test_bump_changes_every_package_and_the_lock(workspace: Path) -> None:
    names = set(tool.packages(workspace))
    assert {"rpa-core", "rpa-runner", "rpa-worker", "rpa-desktop", "rpa-server", "rpa-cli"} <= names
    changed = tool.set_version("9.8.7", workspace)
    assert workspace / "uv.lock" in changed
    assert set(tool.versions(workspace).values()) == {"9.8.7"}
    assert set(tool.lock_versions(workspace).values()) == {"9.8.7"}
    assert set(tool.lock_versions(workspace)) == names
    assert tool.check("v9.8.7", workspace) == []
    # 第三方套件的版本不會被改到
    lock = (workspace / "uv.lock").read_text(encoding="utf-8")
    assert lock.count('version = "9.8.7"') == len(names)
    assert tool.set_version("9.8.7", workspace) == []  # 已經是這個版本：沒有改


def test_check_reports_mismatches(workspace: Path) -> None:
    problems = tool.check("v0.0.1", workspace)
    assert problems
    assert all("0.0.1" in problem for problem in problems)
    assert tool.check("0.2.0", workspace) == ["標籤要是 v主.次.修，例如 v0.2.0：0.2.0"]
    assert tool.check("v0.2", workspace)[0].startswith("標籤要是")


def test_versions_must_be_numeric(workspace: Path) -> None:
    for bad in ("0.2", "0.2.0rc1", "v0.2.0", "0.2.0.1"):
        with pytest.raises(ValueError, match=r"主\.次\.修"):
            tool.set_version(bad, workspace)


def test_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert tool.main(["current"]) == 0
    version = capsys.readouterr().out.strip()
    assert tool.main(["check", f"v{version}"]) == 0
    assert tool.main(["check", "v999.0.0"]) == 1
    assert "::error title=版本::" in capsys.readouterr().out
    assert tool.main(["unknown"]) == 2
