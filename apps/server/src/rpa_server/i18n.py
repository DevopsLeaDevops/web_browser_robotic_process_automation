"""rpa_server 的訊息目錄（頁面、API 錯誤訊息），規則見 docs/adr/0007-i18n.html。"""

from rpa_core.i18n import LOCALES, Catalog

__all__ = ["follow_locale", "t"]

t = Catalog("rpa_server")
"""本套件的訊息目錄。"""


def follow_locale(value: str | None, key: str) -> str | None:
    """系統建立的文字（例如「測試網站自動化」領域的名稱）跟著目前的語言顯示。

    資料庫裡存的是建立當時語言的版本；只要還等於某種語言的預設文字，就換成目前語言的版本。
    使用者改過的文字不等於任何語言的預設文字，照原樣顯示。
    """
    if value is not None and any(t.messages(locale).get(key) == value for locale in LOCALES):
        return t(key)
    return value
