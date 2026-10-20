"""tools/ci_roles.py：測試依路徑分到網站、Worker、錄製端三個角色。"""

import re
from pathlib import Path

import pytest

from tools.ci_roles import markers_for, role_of

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("apps/server/tests/test_portal.py", "server"),
        ("apps/testsite/tests/test_site_login.py", "server"),
        ("packages/rpa_runner/tests/test_run.py", "worker"),
        ("apps/worker/tests/test_worker.py", "worker"),
        # 更長的前綴優先：rpa_runner 裡的逐步調試屬於錄製端
        ("packages/rpa_runner/tests/test_debug.py", "recorder"),
        ("apps/worker/tests/test_gateway.py", "recorder"),
        ("packages/rpa_core/tests/test_workflow.py", None),
        ("tests/smoke/test_browser.py", None),
    ],
)
def test_role_of(path: str, role: str | None) -> None:
    assert role_of(path) == role


def test_markers_include_firefox_for_the_engine_parameter() -> None:
    path = "apps/server/tests/test_flow.py"
    assert markers_for(path, {"engine": "firefox"}) == ["role_server", "firefox"]
    assert markers_for(path, {"engine": "chromium"}) == ["role_server"]
    assert markers_for("packages/rpa_core/tests/test_x.py", {}) == []


def test_every_browser_test_has_a_role_or_is_a_smoke_test() -> None:
    """瀏覽器測試沒有角色就不會在 PR 上執行（只剩每晚）；新增時要在 ROLES 登記。"""
    browser = re.compile(r"pytest\.mark\.browser")
    orphans = [
        path.relative_to(ROOT).as_posix()
        for top in ("packages", "apps", "tests")
        for path in (ROOT / top).rglob("test_*.py")
        if browser.search(text := path.read_text(encoding="utf-8"))
        and role_of(path.relative_to(ROOT).as_posix()) is None
        and "pytest.mark.smoke" not in text
    ]
    assert orphans == []
