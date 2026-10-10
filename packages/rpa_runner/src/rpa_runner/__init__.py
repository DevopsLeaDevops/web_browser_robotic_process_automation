"""rpa_runner：執行引擎。

每次執行一個子程序與獨立的瀏覽器；只接收場景、入參與 Secrets，輸出結果與產物，本身不保存狀態。
入口是 :func:`rpa_runner.run.execute`，命令列是 ``rpa run``。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-runner")
