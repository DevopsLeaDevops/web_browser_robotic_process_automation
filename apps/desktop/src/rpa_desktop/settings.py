"""RPA Worker App 的設定（M10.1）：存在資料夾裡的 ``settings.json``。

只放使用者在「設定」裡的選擇；配對結果在 :mod:`rpa_desktop.credentials`，自動啟動的狀態以
Windows 登錄檔為準（:mod:`rpa_desktop.autostart`），這裡只記「問過了沒有」。
檔案壞掉或缺欄位時用預設值，不讓 App 開不起來。
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast

from rpa_core.i18n import DEFAULT_LOCALE, Locale, parse_locale

__all__ = ["SETTINGS_FILE", "Settings", "load_settings", "save_settings"]

logger = logging.getLogger("rpa_desktop.settings")

SETTINGS_FILE: Final = "settings.json"


@dataclass(frozen=True, slots=True)
class Settings:
    """使用者的選擇。"""

    language: Locale = DEFAULT_LOCALE
    """介面語言；預設繁中，不跟隨作業系統（ADR 0007）。環境變數 ``RPA_LANG`` 優先。"""
    firefox: bool = False
    """也下載 Firefox（只有用 Firefox 的場景需要）。"""
    download_host: str = ""
    """下載瀏覽器的內部鏡像（``PLAYWRIGHT_DOWNLOAD_HOST``）；空白用 Playwright 預設的下載站。"""
    autostart_offered: bool = False
    """第一次配對成功時已經依預設開啟過自動啟動；之後只照使用者在設定裡的選擇。"""
    tray_hint_shown: bool = False
    """第一次關閉視窗時已經提示過「仍在通知區執行」。"""


def load_settings(path: Path) -> Settings:
    """讀回設定；沒有檔案、格式不對或欄位型別不對時，那一項用預設值。"""
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as error:
        logger.warning("設定檔讀不到，改用預設值：%s", error)
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    values = cast("dict[str, object]", data)
    defaults = Settings()

    def flag(name: str, default: bool) -> bool:
        value = values.get(name)
        return value if isinstance(value, bool) else default

    language = values.get("language")
    host = values.get("download_host")
    return Settings(
        language=(parse_locale(language) if isinstance(language, str) else None)
        or defaults.language,
        firefox=flag("firefox", defaults.firefox),
        download_host=host.strip() if isinstance(host, str) else defaults.download_host,
        autostart_offered=flag("autostart_offered", defaults.autostart_offered),
        tray_hint_shown=flag("tray_hint_shown", defaults.tray_hint_shown),
    )


def save_settings(path: Path, settings: Settings) -> None:
    """寫入設定（先寫暫存檔再改名，寫到一半關機也不會留下壞掉的檔案）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(path)
