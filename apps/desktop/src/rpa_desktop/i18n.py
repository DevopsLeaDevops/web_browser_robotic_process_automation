"""桌面端的多語言（M10.1）：本套件的訊息目錄與語言。

語言：環境變數 ``RPA_LANG`` → 繁體中文；和命令列相同，不跟隨作業系統語言（ADR 0007）。

有些話各系統的說法不同（Windows 的通知區、認證管理員；macOS 的選單列、鑰匙圈）：訊息目錄裡
``<前綴>.darwin.<名稱>`` 是 macOS 的說法，:func:`platform_key` 依系統選用，狀態視窗的頁面也一樣
（:func:`rpa_desktop.ui.page_strings`）。
"""

import sys
from collections.abc import Mapping
from typing import Final

from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, Catalog, Locale, parse_locale

__all__ = ["PLATFORM_VARIANT", "platform_key", "resolve_locale", "t"]

t = Catalog("rpa_desktop")
"""本套件的訊息目錄。"""

PLATFORM_VARIANT: Final = "darwin"
"""有自己說法的系統（訊息鍵的第二段）。"""


def resolve_locale(environ: Mapping[str, str]) -> Locale:
    value = environ.get(ENV_VAR)
    return (parse_locale(value) if value else None) or DEFAULT_LOCALE


def platform_key(key: str, platform: str = sys.platform) -> str:
    """macOS 上有 ``<前綴>.darwin.<名稱>`` 時改用它；其他情況照原來的鍵。"""
    if platform != PLATFORM_VARIANT:
        return key
    prefix, dot, name = key.partition(".")
    variant = f"{prefix}.{PLATFORM_VARIANT}.{name}"
    return variant if dot and variant in t.messages(DEFAULT_LOCALE) else key
