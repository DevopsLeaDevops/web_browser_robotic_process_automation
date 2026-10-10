"""多語言：語言代碼、目前語言與訊息目錄。

支援繁體中文（預設）、簡體中文與英文，決策背景見 docs/adr/0007-i18n.html。

- 使用者看得到的文字一律放在套件的 ``locales/<語言>.json``，程式碼裡只寫訊息鍵。
- 繁中與英文由人維護；簡中由 ``tools/i18n.py sync`` 從繁中自動產生，不要手改。
- 目前語言存在 ContextVar 裡：命令列在入口設定一次，伺服器之後可以每個請求各自設定。
"""

import json
import re
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from importlib.resources import files
from typing import Final, Literal, cast

__all__ = [
    "DEFAULT_LOCALE",
    "ENV_VAR",
    "LOCALES",
    "NATIVE_NAMES",
    "Catalog",
    "Locale",
    "get_locale",
    "parse_locale",
    "set_locale",
    "use_locale",
]

Locale = Literal["zh-Hant", "zh-Hans", "en"]

LOCALES: Final[tuple[Locale, ...]] = ("zh-Hant", "zh-Hans", "en")
"""支援的語言，依介面上的排列順序。"""

DEFAULT_LOCALE: Final[Locale] = "zh-Hant"
"""沒有指定語言時一律用繁體中文，不跟隨系統語言。"""

ENV_VAR: Final = "RPA_LANG"
"""長期指定語言的環境變數。"""

NATIVE_NAMES: Final[Mapping[Locale, str]] = {
    "zh-Hant": "繁體中文",
    "zh-Hans": "简体中文",
    "en": "English",
}
"""語言切換選單上的名稱：每種語言用自己的文字顯示，不翻譯。"""

# 地區代碼對應到文字系統：台灣、香港、澳門用繁體，中國大陸、新加坡用簡體。
_HANT_REGIONS: Final = frozenset({"tw", "hk", "mo"})
_HANS_REGIONS: Final = frozenset({"cn", "sg", "my"})

_current: ContextVar[Locale] = ContextVar("rpa_locale", default=DEFAULT_LOCALE)


def parse_locale(value: str) -> Locale | None:
    """把使用者輸入的語言代碼轉成支援的語言；不認得時回傳 None。

    不分大小寫，``-`` 與 ``_`` 皆可，忽略 ``.UTF-8`` 之類的編碼後綴。
    只寫 ``zh`` 無法判斷繁簡，視為不認得。
    """
    parts = [p for p in re.split(r"[-_]", value.strip().split(".")[0].lower()) if p]
    if not parts:
        return None
    language, rest = parts[0], parts[1:]
    if language == "en":
        return "en"
    if language != "zh" or not rest:
        return None
    if "hant" in rest or rest[0] in _HANT_REGIONS:
        return "zh-Hant"
    if "hans" in rest or rest[0] in _HANS_REGIONS:
        return "zh-Hans"
    return None


def get_locale() -> Locale:
    """目前的語言。"""
    return _current.get()


def set_locale(locale: Locale) -> None:
    """設定目前的語言；命令列入口在解析參數前呼叫一次。"""
    _current.set(locale)


@contextmanager
def use_locale(locale: Locale) -> Generator[None, None, None]:
    """在 with 區塊內暫時切換語言，離開時還原。"""
    token = _current.set(locale)
    try:
        yield
    finally:
        _current.reset(token)


class Catalog:
    """一個套件的訊息目錄，讀取 ``<套件>/locales/<語言>.json``。

    用法::

        _ = Catalog("rpa_cli")
        _("cli.version", version="0.1.0")

    訊息用 ``str.format`` 的具名佔位符，例如 ``{version}``；文字本身的大括號要寫成 ``{{``、``}}``。
    """

    def __init__(self, package: str) -> None:
        self.package = package
        self._loaded: dict[Locale, dict[str, str]] = {}

    def messages(self, locale: Locale) -> Mapping[str, str]:
        """某個語言的全部訊息（讀過一次就快取）。"""
        if locale not in self._loaded:
            self._loaded[locale] = self._load(locale)
        return self._loaded[locale]

    def __call__(self, key: str, /, **params: object) -> str:
        """取出目前語言的訊息並代入參數。

        目前語言缺少這個鍵時改用繁中；繁中也沒有代表程式寫錯，直接拋出 KeyError。
        測試會確保三種語言的鍵完全一致，正常情況不會走到後備。
        """
        template = self.messages(get_locale()).get(key)
        if template is None:
            template = self.messages(DEFAULT_LOCALE).get(key)
        if template is None:
            raise KeyError(f"{self.package} 的訊息目錄沒有 {key!r}")
        return template.format_map(params)

    def _load(self, locale: Locale) -> dict[str, str]:
        resource = files(self.package).joinpath("locales", f"{locale}.json")
        raw: object = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError(f"{self.package}/locales/{locale}.json 必須是物件")
        messages: dict[str, str] = {}
        for key, value in cast("dict[object, object]", raw).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError(f"{self.package}/locales/{locale}.json 的鍵與值都必須是字串")
            messages[key] = value
        return messages
