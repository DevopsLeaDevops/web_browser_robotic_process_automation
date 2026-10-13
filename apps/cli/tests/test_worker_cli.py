"""`rpa worker`（M9a）：說明、權杖、事件的文字，以及 `rpa serve` 的 Worker API 選項。

不真的連管理 Portal：遠端任務來源本身在 apps/worker 的測試，完整流程在 apps/server 的端到端測試。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_cli.worker import TOKEN_ENV, describe_event
from rpa_core.i18n import use_locale


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        install_click_translations()
        yield


def invoke(*args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    result = CliRunner().invoke(build_cli(), list(args), env=env)
    return result.exit_code, result.output


def test_help_mentions_the_token_variable() -> None:
    code, output = invoke("worker", "--help")
    assert code == 0
    assert TOKEN_ENV in output
    assert "--server" in output
    assert "--no-testsite" in output


def test_token_is_required(tmp_path: Path) -> None:
    code, output = invoke("worker", "--server", "http://x:8081", env={TOKEN_ENV: ""})
    assert code == 1
    assert TOKEN_ENV in output

    missing = tmp_path / "nope.txt"
    code, output = invoke("worker", "--server", "x:8081", "--token-file", str(missing))
    assert code == 1
    assert str(missing) in output


def test_serve_help_lists_worker_options() -> None:
    code, output = invoke("serve", "--help")
    assert code == 0
    for option in ("--worker-port", "--worker-host", "--no-local-worker"):
        assert option in output


def test_events_are_described() -> None:
    online = describe_event(
        "online",
        {"worker": "win-01", "sameVersion": False, "fingerprint": "a", "serverFingerprint": "b"},
    )
    assert online is not None
    assert "win-01" in online
    assert "git pull" in online
    same = describe_event("online", {"worker": "win-01", "sameVersion": True})
    assert same is not None
    assert "git pull" not in same
    claimed = describe_event("claimed", {"run": "ba-001-x", "headless": False})
    assert claimed is not None
    assert "有頭模式" in claimed
    for event in ("offline", "reported", "abandoned", "report_failed", "rejected"):
        assert describe_event(
            event, {"run": "r", "server": "s", "reason": "x", "status": "passed", "message": "m"}
        )
    assert describe_event("unknown", {}) is None


def test_events_follow_the_language() -> None:
    with use_locale("en"):
        text = describe_event("claimed", {"run": "r1", "headless": True})
    assert text == "Running r1 (headless)"
