"""桌面端的多語言（M10.1）：本套件的訊息目錄與語言。

語言：環境變數 ``RPA_LANG`` → 繁體中文；和命令列相同，不跟隨作業系統語言（ADR 0007）。
"""

from collections.abc import Mapping

from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, Catalog, Locale, parse_locale

__all__ = ["resolve_locale", "t"]

t = Catalog("rpa_desktop")
"""本套件的訊息目錄。"""


def resolve_locale(environ: Mapping[str, str]) -> Locale:
    value = environ.get(ENV_VAR)
    return (parse_locale(value) if value else None) or DEFAULT_LOCALE
