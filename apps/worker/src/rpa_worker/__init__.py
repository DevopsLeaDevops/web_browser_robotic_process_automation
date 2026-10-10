"""rpa_worker：背景 worker。

從任務來源領取待執行的任務，以子程序呼叫 rpa-runner（總期限、取消），把結果交回任務來源。
本身不碰資料庫：任務來源由使用的一方實作（M3 是 rpa-server 的 SQLite，M9 換成分散式佇列）。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-worker")
