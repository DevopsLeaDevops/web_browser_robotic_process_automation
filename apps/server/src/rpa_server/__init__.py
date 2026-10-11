"""rpa_server：管理 Portal。

FastAPI 提供 ``/api`` 與 Jinja 頁面（ADR 0011）；SQLite 存場景、版本與執行紀錄（ADR 0008），
場景版本的檔案與每次執行的目錄放在資料目錄。執行交給同一個程序裡的背景 worker（rpa-worker）。
啟動：``rpa serve``。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-server")
