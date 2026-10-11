"""伺服器設定：從環境變數讀取，命令列參數可以覆寫。

| 環境變數 | 預設 | 說明 |
|---|---|---|
| ``RPA_DATA_DIR`` | ``data`` | 資料目錄：SQLite 檔、場景版本、執行目錄 |
| ``RPA_DATABASE_URL`` | ``sqlite:///<資料目錄>/rpa.db`` | 正式環境改成 PostgreSQL（M8，ADR 0008） |
| ``RPA_LANG`` | ``zh-Hant`` | 頁面的預設語言，也是執行報告的語言 |
| ``RPA_EXAMPLES_DIR`` | ``scenarios/demo``（存在時） | 「匯入範例」從這裡讀取場景 |
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rpa_core.i18n import DEFAULT_LOCALE, Locale, parse_locale

__all__ = ["DEFAULT_EXAMPLES", "Settings", "sqlite_url"]

DEFAULT_EXAMPLES = Path("scenarios") / "demo"


def sqlite_url(path: Path) -> str:
    """SQLite 檔案的連線字串（絕對路徑，Windows 也適用）。"""
    return f"sqlite:///{path.resolve().as_posix()}"


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_url: str
    locale: Locale = DEFAULT_LOCALE
    examples_dir: Path | None = None
    start_worker: bool = True
    """測試可以關掉背景 worker，改成手動 ``worker.run_once()``。"""

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
        data = data_dir or Path(env.get("RPA_DATA_DIR") or "data")
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
        )
