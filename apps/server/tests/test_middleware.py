"""ASGI 中介層：每個請求的語言、擋掉跨站的寫入請求。直接呼叫 ASGI 介面，不需要 HTTP 用戶端。"""

import asyncio

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rpa_core.i18n import get_locale
from rpa_server.middleware import LocaleMiddleware, SameOriginMiddleware


async def _echo_locale(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": get_locale().encode()})


def _call(
    app: ASGIApp, *, method: str = "GET", query: str = "", headers: dict[str, str] | None = None
) -> tuple[int, bytes]:
    sent: list[Message] = []
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def main() -> None:
        await app(scope, receive, send)

    asyncio.run(main())
    status: int = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m["body"] for m in sent if m["type"] == "http.response.body")
    return status, body


@pytest.mark.parametrize(
    ("query", "cookie", "expected"),
    [
        ("", None, b"zh-Hant"),
        ("lang=en", None, b"en"),
        ("", "rpa_lang=zh-Hans", b"zh-Hans"),
        ("lang=en", "rpa_lang=zh-Hans", b"en"),
        ("lang=xx", "other=1; rpa_lang=en", b"en"),
        ("", "rpa_lang=zh", b"zh-Hant"),
        ("", 'bad"cookie', b"zh-Hant"),
    ],
)
def test_locale_from_query_then_cookie(query: str, cookie: str | None, expected: bytes) -> None:
    app = LocaleMiddleware(_echo_locale, default="zh-Hant")
    headers = {"Cookie": cookie} if cookie else {}

    assert _call(app, query=query, headers=headers) == (200, expected)
    assert get_locale() == "zh-Hant"


def test_server_default_locale() -> None:
    app = LocaleMiddleware(_echo_locale, default="en")
    assert _call(app) == (200, b"en")


@pytest.mark.parametrize(
    ("method", "headers", "status"),
    [
        ("GET", {"Origin": "https://evil.example", "Host": "127.0.0.1:8000"}, 200),
        ("POST", {"Host": "127.0.0.1:8000"}, 200),
        ("POST", {"Origin": "http://127.0.0.1:8000", "Host": "127.0.0.1:8000"}, 200),
        ("POST", {"Origin": "https://evil.example", "Host": "127.0.0.1:8000"}, 403),
        ("PATCH", {"Origin": "null", "Host": "127.0.0.1:8000"}, 403),
    ],
)
def test_cross_origin_writes_are_blocked(method: str, headers: dict[str, str], status: int) -> None:
    app = SameOriginMiddleware(_echo_locale)
    assert _call(app, method=method, headers=headers)[0] == status
