"""命令列的多語言：決定語言、本套件的訊息目錄，以及 click 內建文字的翻譯。

語言的優先順序：``--lang`` 參數 → 環境變數 ``RPA_LANG`` → 繁體中文。
不跟隨作業系統語言（見 docs/adr/0007-i18n.html）。
"""

import gettext
import json
import sys
from collections.abc import Mapping, Sequence
from importlib.resources import files
from typing import Final, cast

from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, Catalog, Locale, get_locale, parse_locale

__all__ = ["LANG_OPTION", "install_click_translations", "resolve_locale", "t"]

LANG_OPTION: Final = "--lang"

t = Catalog("rpa_cli")
"""本套件的訊息目錄。"""


def resolve_locale(args: Sequence[str], environ: Mapping[str, str]) -> Locale:
    """在 click 解析參數之前先決定語言，說明文字與錯誤訊息才能一開始就用對語言。

    只認得 ``--lang 值`` 與 ``--lang=值``；值無效時略過，交給 click 回報錯誤。
    """
    value: str | None = None
    for index, arg in enumerate(args):
        if arg == "--":
            break
        if arg == LANG_OPTION and index + 1 < len(args):
            value = args[index + 1]
        elif arg.startswith(LANG_OPTION + "="):
            value = arg.partition("=")[2]
    for candidate in (value, environ.get(ENV_VAR)):
        if candidate and (locale := parse_locale(candidate)) is not None:
            return locale
    return DEFAULT_LOCALE


# ------------------------------------------------------------ click 內建文字
#
# click 用標準函式庫的 gettext 標記自己的文字（Usage:、Options、錯誤訊息等），
# 每個模組各自 `from gettext import gettext as _`。這裡把那些模組的 `_` 與 `ngettext`
# 換成依目前語言查表的版本；查不到時保留 click 原本的英文。
# 翻譯放在 locales/click.<語言>.json，鍵是 click 原文；英文不需要翻譯檔。

_click_messages: dict[Locale, dict[str, str]] = {}


def _click_catalog(locale: Locale) -> Mapping[str, str]:
    if locale not in _click_messages:
        resource = files("rpa_cli").joinpath("locales", f"click.{locale}.json")
        raw = cast("dict[str, str]", json.loads(resource.read_text(encoding="utf-8")))
        _click_messages[locale] = raw
    return _click_messages[locale]


def _click_gettext(message: str) -> str:
    locale = get_locale()
    if locale == "en":
        return message
    return _click_catalog(locale).get(message, message)


def _click_ngettext(singular: str, plural: str, n: int) -> str:
    message = singular if n == 1 else plural
    locale = get_locale()
    if locale == "en":
        return message
    return _click_catalog(locale).get(message, message)


_REPLACEMENTS: Final = (
    ("_", gettext.gettext, _click_gettext),
    ("ngettext", gettext.ngettext, _click_ngettext),
)


def install_click_translations() -> None:
    """讓 click 已載入的模組改用本套件的翻譯。可以重複呼叫。"""
    for name, module in list(sys.modules.items()):
        if name != "click" and not name.startswith("click."):
            continue
        for attr, original, replacement in _REPLACEMENTS:
            if getattr(module, attr, None) is original:
                setattr(module, attr, replacement)
