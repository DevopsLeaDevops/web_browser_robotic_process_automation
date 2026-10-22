"""伺服器設定：從環境變數讀取，命令列參數可以覆寫。

| 環境變數 | 預設 | 說明 |
|---|---|---|
| ``RPA_DATA_DIR`` | ``data`` | 資料目錄：SQLite 檔、場景版本、執行目錄 |
| ``RPA_DATABASE_URL`` | ``sqlite:///<資料目錄>/rpa.db`` | 正式環境改成 PostgreSQL（M8，ADR 0008） |
| ``RPA_LANG`` | ``zh-Hant`` | 頁面的預設語言，也是執行報告的語言 |
| ``RPA_EXAMPLES_DIR`` | ``scenarios/demo``（存在時） | 「測試網站自動化」領域的範例場景 |

Worker API 的埠與要不要跑本機 worker（M9a）由 ``rpa serve --worker-port``、
``--no-local-worker`` 決定。

第一次啟動（還沒有任何領域）時，建立「測試網站自動化」領域並匯入範例場景（seed_examples）。

執行時預設用有頭模式（headed，顯示瀏覽器視窗）；這台電腦沒有圖形介面時（例如沒有 DISPLAY 的
Linux 伺服器）只能用無頭模式（headless），見 :func:`has_display`。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rpa_core.i18n import DEFAULT_LOCALE, Locale, parse_locale
from rpa_worker.environment import has_display as worker_has_display

__all__ = [
    "COMPOSITES_DOMAIN",
    "DEFAULT_EXAMPLES",
    "EXAMPLES_DOMAIN",
    "RECORDER_MENUS",
    "Settings",
    "has_display",
    "sqlite_url",
]

DEFAULT_EXAMPLES = Path("scenarios") / "demo"
EXAMPLES_DOMAIN = "testsite"
"""範例場景所屬的領域代號：「測試網站自動化」，案例都對本機測試網站執行。"""
COMPOSITES_DOMAIN = "composites"
"""「組合場景」領域：只放組合場景的領域；遷移的與沒指定領域的新組合場景放這裡（M11 D1、D7）。
左側選單不列它，組合場景在「組合場景自動化」管理。"""
RECORDER_MENUS = ("cluster", "admin")
"""透過錄製端打開管理 Portal 時預設不顯示的第一級選單：叢集管理、管理後台（三段分工，
2026-10-22）。裝置頁可以替個別錄製端打開；伺服器本機（8080）全部顯示。"""


def sqlite_url(path: Path) -> str:
    """SQLite 檔案的連線字串（絕對路徑，Windows 也適用）。"""
    return f"sqlite:///{path.resolve().as_posix()}"


def has_display(environ: Mapping[str, str] | None = None, platform: str | None = None) -> bool:
    """這台電腦能不能顯示瀏覽器視窗（有頭模式）；與遠端 worker 用同一套判斷。

    Windows 與 macOS 視為有桌面；其他系統要有 X11（DISPLAY）或 Wayland（WAYLAND_DISPLAY）。
    """
    return worker_has_display(environ, platform)


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_url: str
    locale: Locale = DEFAULT_LOCALE
    examples_dir: Path | None = None
    start_worker: bool = True
    """測試可以關掉背景 worker，改成手動 ``worker.run_once()``。"""
    seed_examples: bool = True
    """還沒有任何領域時，建立「測試網站自動化」並匯入範例場景。"""
    display: bool = False
    """能不能顯示瀏覽器視窗；能的話執行預設用有頭模式。from_env 會自動偵測，測試預設不顯示。"""
    worker_port: int | None = None
    """對外埠（M9a 的 Worker API 埠；M10 起也提供 Client API）；None 代表不開放。"""
    worker_host: str = "0.0.0.0"
    """對外埠綁定的位址；裝置邀請用它決定伺服器網址（M10.1）。"""
    local_worker: bool = True
    """要不要在這台電腦執行（本機 worker）；False 時只有遠端 worker 執行。"""
    portal_port: int | None = None
    """管理頁面實際聽的埠（``rpa serve`` 填入）；用來擋下把 Portal 自己當成錄製的起始網址。"""

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @classmethod
    def from_env(
        cls,
        *,
        data_dir: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        env = os.environ if environ is None else environ
        # 一律用絕對路徑：子程序（例如錄製）的工作目錄不同，相對路徑會指到別的地方
        data = (data_dir or Path(env.get("RPA_DATA_DIR") or "data")).expanduser().absolute()
        examples = env.get("RPA_EXAMPLES_DIR")
        if examples:
            examples_dir: Path | None = Path(examples)
        else:
            examples_dir = DEFAULT_EXAMPLES if DEFAULT_EXAMPLES.is_dir() else None
        return cls(
            data_dir=data,
            database_url=env.get("RPA_DATABASE_URL") or sqlite_url(data / "rpa.db"),
            locale=parse_locale(env.get("RPA_LANG", "")) or DEFAULT_LOCALE,
            examples_dir=examples_dir,
            display=has_display(env),
        )
