"""rpa_server 的訊息目錄（頁面、API 錯誤訊息），規則見 docs/adr/0007-i18n.html。"""

from typing import Final

from rpa_core.i18n import LOCALES, Catalog
from rpa_server.context import via_recorder

__all__ = ["VIA_RECORDER_KEYS", "follow_locale", "page_t", "t"]

t = Catalog("rpa_server")
"""本套件的訊息目錄。"""

VIA_RECORDER_KEYS: Final = {
    "target.local": "target.local_via_recorder",
    "worker.local": "worker.local_via_recorder",
    "target.local_url_warning": "target.local_url_warning_via_recorder",
    # 錄製、逐步調試、人工登入的瀏覽器開在錄製端（操作的那台），不是執行 Portal 的電腦
    "roles.notice": "roles.notice_via_recorder",
    "roles.no_display": "roles.no_display_via_recorder",
    "roles.session_waiting": "roles.session_waiting_via_recorder",
    "roles.login_title": "roles.login_title_via_recorder",
    "recording.active": "recording.active_via_recorder",
    "recording.in_progress": "recording.in_progress_via_recorder",
    "recording.record_hint": "recording.record_hint_via_recorder",
    "recording.no_display": "recording.no_display_via_recorder",
    "debug.window_hint": "debug.window_hint_via_recorder",
    "debug.no_display": "debug.no_display_via_recorder",
    "display.use_recorder": "display.use_recorder_via_recorder",
    "js.recording_started": "js.recording_started_via_recorder",
    # 登入狀態與 Secrets 存在伺服器，不是操作的這台
    "secrets.hint": "secrets.hint_via_recorder",
    "js.role_clear_body": "js.role_clear_body_via_recorder",
    "app.env": "app.env_via_recorder",
    "app.footer_note": "app.footer_note_via_recorder",
}
"""透過錄製端看頁面時換掉的訊息（M10.2）：「本機」指的是伺服器，不是操作的這台；
錄製、逐步調試、人工登入的瀏覽器則開在錄製端。"""


def page_t(key: str, /, **params: object) -> str:
    """頁面上的文字：和 :data:`t` 相同，但透過錄製端看時把「本機」改稱「伺服器」。"""
    if via_recorder() is not None:
        key = VIA_RECORDER_KEYS.get(key, key)
    return t(key, **params)


def follow_locale(value: str | None, key: str) -> str | None:
    """系統建立的文字（例如「測試網站自動化」領域的名稱）跟著目前的語言顯示。

    資料庫裡存的是建立當時語言的版本；只要還等於某種語言的預設文字，就換成目前語言的版本。
    使用者改過的文字不等於任何語言的預設文字，照原樣顯示。
    """
    if value is None:
        return value
    if any(t.messages(locale).get(key) == value for locale in LOCALES) or value in _PREVIOUS.get(
        key, ()
    ):
        return t(key)
    return value


_PREVIOUS: dict[str, tuple[str, ...]] = {
    # 之前版本的預設文字：已經存進資料庫的也當成沒改過，跟著目前的版本與語言顯示
    "domain.testsite_description": (
        "對本機測試網站（rpa serve 一起啟動，http://127.0."
        "0.1:8765）執行的真實案例：建立紀錄、查詢紀錄、查詢不存在的紀錄，"
        "以及 Python 腳本版的建立紀錄。",
        "对本机测试网站（rpa serve 一起启动，http://127.0."
        "0.1:8765）运行的真实案例：创建记录、查询记录、查询不存在的记录，"
        "以及 Python 脚本版的创建记录。",
        "Real cases that run against the local test site (started with rpa serve at http:"
        "//127.0.0.1:8765): create a record, look it up, look up a record that does not e"
        "xist, and the Python script version of creating a record.",
    ),
}
