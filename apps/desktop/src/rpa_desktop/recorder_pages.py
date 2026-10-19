"""RPA 錄製端 App 自己的頁面（M10.2，ADR 0014）：本機閘道 ``/__desktop/`` 底下。

視窗載入的都是閘道的網址，所以 App 的頁面也放在閘道上，但在**另一個埠**（另一個來源、另一個
密語與 Cookie，見 :class:`rpa_worker.gateway.Gateway`）：管理 Portal 的頁面讀不到這裡的狀態，
寫入的請求也一定要帶這個埠的 Origin，Portal 的頁面（或塞進去的腳本）叫不動 App 的動作。

- ``GET /__desktop/``：狀態、配對、下載瀏覽器、設定（:func:`rpa_desktop.ui.render_page` 的
  ``recorder`` 頁面）。頁面每秒讀一次 ``state``，按鈕呼叫下面的 POST。
- ``GET /__desktop/state``：:meth:`RecorderController.snapshot`，配對好時加上打開管理 Portal 的
  網址（``portalUrl``，帶著 Portal 那邊的密語：只有這個來源讀得到）。
- ``POST /__desktop/pair``（``invite``、``server``、``firefox``）、``retry``、``reset``、
  ``settings``（``name``、``value``）、``logs``、``download``（在預設瀏覽器打開最新的 Release）、
  ``quit``、``ready``（頁面載入了，自我測試用）。

只有帶著這個埠的 Cookie 的請求進得來；內容一律 ``Cache-Control: no-store``。

:func:`offline_page`、:func:`notice_page` 是 Portal 那個埠的說明頁（連不上、還沒配對、配對失效），
不放 App 頁面的網址（帶著密語）：要回到 App 的頁面用選單。
"""

import html
import json
import logging
from collections.abc import Callable, Mapping
from typing import Final, Protocol, cast
from urllib.parse import urlsplit

from rpa_core.i18n import Locale, parse_locale, use_locale
from rpa_desktop.i18n import t
from rpa_desktop.ui import read_asset, render_page
from rpa_worker.gateway import LocalResponse

__all__ = ["DesktopPages", "notice_page", "offline_page"]

logger = logging.getLogger("rpa_desktop.recorder_pages")

JSON_TYPE: Final = "application/json; charset=utf-8"
MAX_TEXT: Final = 4000


class Controller(Protocol):
    """頁面用到的 :class:`rpa_desktop.recorder_controller.RecorderController`。"""

    @property
    def locale(self) -> Locale: ...

    def snapshot(self) -> dict[str, object]: ...

    def pair(self, text: str, server: str | None = None, firefox: bool | None = None) -> bool: ...

    def retry(self) -> bool: ...

    def reset_pairing(self, timeout: float = ...) -> bool: ...

    def set_language(self, language: Locale) -> None: ...

    def set_firefox(self, firefox: bool) -> None: ...

    def set_download_host(self, host: str) -> None: ...


def _json(value: object, status: int = 200) -> LocalResponse:
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return LocalResponse(status=status, body=data, content_type=JSON_TYPE)


def _payload(body: bytes) -> dict[str, object]:
    if not body:
        return {}
    try:
        value: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    return value[:MAX_TEXT] if isinstance(value, str) else ""


class DesktopPages:
    """閘道的 ``local``：(方法, ``/__desktop/`` 之後的路徑, 查詢參數, 內容) → 回應。"""

    def __init__(
        self,
        controller: Controller,
        *,
        on_quit: Callable[[], object] | None = None,
        on_logs: Callable[[], object] | None = None,
        on_download: Callable[[], object] | None = None,
        on_ready: Callable[[str], object] | None = None,
        on_language: Callable[[Locale], object] | None = None,
        portal_url: Callable[[], str] | None = None,
    ) -> None:
        self.controller = controller
        self.portal_url = portal_url
        self.on_quit = on_quit
        self.on_logs = on_logs
        self.on_download = on_download
        self.on_ready = on_ready
        self.on_language = on_language

    def __call__(
        self, method: str, path: str, query: Mapping[str, list[str]], body: bytes
    ) -> LocalResponse:
        try:
            return self._route(method, path.strip("/"), body)
        except Exception:
            logger.exception("App 的頁面 %s %s 出錯", method, path)
            return _json({"ok": False}, 500)

    def _route(self, method: str, path: str, body: bytes) -> LocalResponse:
        controller = self.controller
        if method in ("GET", "HEAD"):
            if path in ("", "index.html"):
                page = render_page(controller.locale, "recorder")
                return LocalResponse(body=page.encode("utf-8"))
            if path == "state":
                state = controller.snapshot()
                paired = state.get("paired") is True
                state["portalUrl"] = self.portal_url() if paired and self.portal_url else None
                return _json(state)
            return _json({"ok": False}, 404)
        if method != "POST":
            return _json({"ok": False}, 405)
        values = _payload(body)
        if path == "pair":
            firefox = values.get("firefox")
            started = controller.pair(
                _text(values, "invite"),
                _text(values, "server").strip() or None,
                firefox if isinstance(firefox, bool) else None,
            )
            return _json({"ok": started})
        if path == "retry":
            return _json({"ok": controller.retry()})
        if path == "reset":
            return _json({"ok": controller.reset_pairing()})
        if path == "settings":
            return _json({"ok": self._setting(_text(values, "name"), values.get("value"))})
        if path == "logs" and self.on_logs is not None:
            self.on_logs()
            return _json({"ok": True})
        if path == "download" and self.on_download is not None:
            self.on_download()
            return _json({"ok": True})
        if path == "quit" and self.on_quit is not None:
            self.on_quit()
            return _json({"ok": True})
        if path == "ready":
            if self.on_ready is not None:
                self.on_ready(_text(values, "userAgent"))
            return _json({"ok": True})
        return _json({"ok": False}, 404)

    def _setting(self, name: str, value: object) -> bool:
        controller = self.controller
        if name == "firefox" and isinstance(value, bool):
            controller.set_firefox(value)
            return True
        if name == "download_host" and isinstance(value, str):
            host = value.strip()[:MAX_TEXT]
            if host and urlsplit(host).scheme not in ("http", "https"):
                return False  # 只接受 http(s) 的鏡像網址
            controller.set_download_host(host)
            return True
        if name == "language" and isinstance(value, str):
            language = parse_locale(value)
            if language is None:
                return False
            controller.set_language(language)
            if self.on_language is not None:
                self.on_language(language)
            return True
        return False


def _page(locale: str, title: str, text: str, actions: str) -> str:
    """Portal 那個埠的小說明頁（設計系統的 CSS 內嵌）。"""
    return (
        f'<!doctype html><html lang="{html.escape(locale)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{read_asset('portal.css')}</style>"
        f"<style>{read_asset('worker.css')}</style></head>"
        '<body class="worker-app"><main id="main"><div class="stack">'
        f'<div class="notice warn" role="alert"><strong>{html.escape(title)}</strong>'
        f"<p>{html.escape(text)}</p></div>"
        f'<div class="form-actions">{actions}</div></div></main></body></html>'
    )


def notice_page(locale: Callable[[], Locale], *, window: bool = True) -> Callable[[str], str]:
    """還沒配對（``unpaired``）或配對失效（``unauthorized``）時，Portal 那個埠的說明頁。

    ``window`` 是 False 時（``--no-window``）沒有 App 的選單可以點，改說明用 ``--invite`` 重新啟動。
    """
    suffix = "" if window else "_no_window"

    def render(kind: str) -> str:
        language = locale()
        key = (
            "recorder.notice_unauthorized" if kind == "unauthorized" else "recorder.notice_unpaired"
        ) + suffix
        with use_locale(language):
            return _page(language, t("recorder.title"), t(key), "")

    return render


def offline_page(
    locale: Callable[[], Locale], server: Callable[[], str | None]
) -> Callable[[str], str]:
    """閘道連不上管理 Portal 時的頁面：說明原因，可以重新整理。"""

    def render(reason: str) -> str:
        language = locale()
        with use_locale(language):
            title = t("recorder.offline_title")
            text = t("recorder.offline_body", server=server() or "", reason=reason)
            reload = t("recorder.offline_reload")
        button = (
            '<button class="button primary" type="button" onclick="location.reload()">'
            f"{html.escape(reload)}</button>"
        )
        return _page(language, title, text, button)

    return render
