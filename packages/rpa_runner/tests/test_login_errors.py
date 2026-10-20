"""登入檢查與人工登入的錯誤說明（:func:`rpa_runner.login.describe_error`）。不需要瀏覽器。"""

from collections.abc import Iterator

import pytest

from rpa_core.i18n import use_locale
from rpa_runner.login import describe_error


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def playwright_error(text: str) -> Exception:
    """和 Playwright 的錯誤一樣：第一行是錯誤，後面是呼叫紀錄。"""
    return type("Error", (Exception,), {})(text)


def test_missing_browser_says_what_to_run() -> None:
    error = playwright_error(
        "BrowserType.launch: Executable doesn't exist at "
        "/home/admin/.cache/ms-playwright/firefox-1555/firefox/firefox\n"
        "╔════════════════════════════════╗\n"
        "║ Looks like Playwright was just installed or updated. ║"
    )
    message = describe_error(error)
    assert "Firefox" in message
    assert "uv run playwright install firefox" in message
    assert "Executable" not in message


@pytest.mark.parametrize(
    ("first", "url", "host"),
    [
        ("Page.goto: NS_ERROR_CONNECTION_REFUSED", "http://127.0.0.1:8765/login", "127.0.0.1"),
        (
            "Page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:8765/login",
            "http://localhost:8765/login",
            "localhost",
        ),
        ("Page.goto: Could not connect to server", "http://[::1]:8765/login", "::1"),
        ("Page.goto: NS_ERROR_CONNECTION_REFUSED", "http://0.0.0.0:8765/login", "0.0.0.0"),
    ],
)
def test_refused_local_address_is_this_computer(first: str, url: str, host: str) -> None:
    error = playwright_error(f'{first}\nCall log:\n  - navigating to "{url}", waiting until "load"')
    message = describe_error(error)
    assert url in message
    assert host in message
    assert "開瀏覽器的這台電腦自己" in message


def test_refused_other_address_only_says_it_cannot_connect() -> None:
    url = "http://215.192.222.14:8765/login"
    message = describe_error(playwright_error(": NS_ERROR_CONNECTION_REFUSED"), url=url)
    assert url in message
    assert "連線被拒絕" in message
    assert "這台電腦自己" not in message


def test_given_url_wins_and_unknown_url_keeps_the_error() -> None:
    error = playwright_error(": NS_ERROR_CONNECTION_REFUSED")
    assert "開瀏覽器的這台電腦自己" in describe_error(error, url="http://127.0.0.1:9/login")
    assert describe_error(error) == "Error: : NS_ERROR_CONNECTION_REFUSED"


def test_other_errors_keep_the_first_line_and_mask_secrets() -> None:
    error = RuntimeError("登入失敗 s3cret-pass\n第二行")
    assert describe_error(error, {"PASSWORD": "s3cret-pass"}) == "RuntimeError: 登入失敗 ***"
