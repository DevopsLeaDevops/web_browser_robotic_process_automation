"""`rpa worker`（M9a）：說明、權杖、事件的文字，以及 `rpa serve` 的對外埠選項；
M10.1 的邀請配對（--invite）與存下的配對結果。

不真的連管理 Portal：遠端任務來源本身在 apps/worker 的測試，完整流程在 apps/server 的端到端測試。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpa_cli.i18n import install_click_translations
from rpa_cli.main import build_cli
from rpa_cli.worker import TOKEN_ENV, describe_event, resolve_credentials
from rpa_core.i18n import use_locale
from rpa_worker.pairing import PAIRING_FILE, PairResult, save_pairing

CODE = "abcdefghijklmnopqrstuvwxyz012345"


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
    assert "--invite" in output
    assert "--no-testsite" in output


def test_token_is_required(tmp_path: Path) -> None:
    work = ("--work-dir", str(tmp_path / "work"))
    code, output = invoke("worker", "--server", "http://x:8081", *work, env={TOKEN_ENV: ""})
    assert code == 1
    assert TOKEN_ENV in output
    assert "--invite" in output
    assert not (tmp_path / "work").exists()  # 沒有權杖時不建立工作資料夾

    missing = tmp_path / "nope.txt"
    code, output = invoke("worker", "--server", "x:8081", "--token-file", str(missing), *work)
    assert code == 1
    assert str(missing) in output


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("--invite", "not an invitation"), "這不是邀請"),
        (("--invite", CODE), "伺服器網址不對"),  # 只有代碼時要 --server
        (("--invite", f"rpa://pair?server=ftp://x&code={CODE}"), "伺服器網址不對"),
        (("--invite", f"rpa://pair?server=http://x:8081&app=other&code={CODE}"), "App 種類"),
        (("--invite", "  "), "邀請是空的"),
    ],
)
def test_invite_problems_are_explained(
    tmp_path: Path, args: tuple[str, ...], expected: str
) -> None:
    code, output = invoke("worker", *args, "--work-dir", str(tmp_path), env={TOKEN_ENV: ""})
    assert code == 1
    assert expected in output


def test_pairing_offline_is_explained(tmp_path: Path) -> None:
    """連不上（這裡用不會有服務的埠）：說明要開對外埠，不留下配對檔。"""
    line = f"rpa://pair?server=http://127.0.0.1:9&app=worker&code={CODE}"
    code, output = invoke("worker", "--invite", line, "--work-dir", str(tmp_path))
    assert code == 1
    assert "--worker-port" in output
    assert not (tmp_path / PAIRING_FILE).exists()


def test_saved_pairing_is_used_until_a_token_is_given(tmp_path: Path) -> None:
    save_pairing(
        tmp_path / PAIRING_FILE,
        PairResult(
            server="http://192.168.1.10:8081",
            device="win-01",
            name="Windows",
            app="worker",
            token="saved-token",
            protocol=1,
            fingerprint=None,
            version=None,
        ),
    )
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token\n", encoding="utf-8")

    assert resolve_credentials(None, None, None, tmp_path) == (
        "http://192.168.1.10:8081",
        "saved-token",
    )
    assert resolve_credentials("10.0.0.5:8081", None, None, tmp_path) == (
        "http://10.0.0.5:8081",
        "saved-token",
    )
    assert resolve_credentials(None, token_file, None, tmp_path) == (
        "http://192.168.1.10:8081",
        "file-token",
    )


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
