"""測試網站的登入：兩個示範帳號、帳號頁、登出與讓所有登入失效（不需要瀏覽器）。"""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.cookiejar import CookieJar

import pytest

from testsite.server import ACCOUNTS, SESSION_COOKIE, running


@pytest.fixture
def site() -> Iterator[str]:
    with running() as url:
        yield url


class Browser:
    """帶著 cookie 的簡單用戶端；不自動跟隨轉址，才看得到 302。"""

    def __init__(self) -> None:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: object, **kwargs: object) -> None:
                return None

        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies), NoRedirect()
        )

    def request(self, url: str, data: object | None = None) -> tuple[int, str, dict[str, str]]:
        body = json.dumps(data).encode() if data is not None else None
        method = "POST" if data is not None else "GET"
        request = urllib.request.Request(
            url, data=body, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, response.read().decode(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(), dict(error.headers)


def test_account_page_redirects_to_login_until_logged_in(site: str) -> None:
    browser = Browser()
    status, _, headers = browser.request(f"{site}/account")
    assert status == 302
    assert headers["Location"] == "/login?next=/account"

    status, body, _ = browser.request(f"{site}/api/login", {"username": "user", "password": "x"})
    assert status == 401
    assert "密碼" in json.loads(body)["error"]

    status, body, headers = browser.request(
        f"{site}/api/login", {"username": "user", "password": "user-pass"}
    )
    assert status == 200
    assert json.loads(body) == {"name": "王小明", "role": "一般使用者"}
    assert "HttpOnly" in headers["Set-Cookie"]
    assert SESSION_COOKIE in headers["Set-Cookie"]

    status, page, _ = browser.request(f"{site}/account")
    assert status == 200
    assert 'data-testid="current-user" id="account-name">王小明<' in page
    assert '<span id="todo-count">2</span>' in page


def test_two_accounts_see_different_data(site: str) -> None:
    user, manager = Browser(), Browser()
    user.request(f"{site}/api/login", {"username": "user", "password": "user-pass"})
    manager.request(f"{site}/api/login", {"username": "manager", "password": "manager-pass"})

    assert "王小明" in user.request(f"{site}/account")[1]
    page = manager.request(f"{site}/account")[1]
    assert "林主管" in page
    assert f'<span id="todo-count">{len(ACCOUNTS["manager"].todos)}</span>' in page


def test_logout_and_expire(site: str) -> None:
    first, second = Browser(), Browser()
    first.request(f"{site}/api/login", {"username": "user", "password": "user-pass"})
    second.request(f"{site}/api/login", {"username": "manager", "password": "manager-pass"})

    status, body, _ = first.request(f"{site}/api/logout", {})
    assert (status, json.loads(body)) == (200, {"loggedOut": True})
    assert first.request(f"{site}/account")[0] == 302
    assert second.request(f"{site}/account")[0] == 200

    status, body, _ = Browser().request(f"{site}/api/sessions/expire", {})
    assert (status, json.loads(body)) == (200, {"expired": 1})
    assert second.request(f"{site}/account")[0] == 302


def test_login_page(site: str) -> None:
    status, page, _ = Browser().request(f"{site}/login")
    assert status == 200
    assert 'id="password" name="password" type="password"' in page
    assert "user-pass" in page
