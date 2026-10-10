"""rpa_core：場景 DSL 的模型、校驗與表達式引擎。

場景 DSL 在 rpa_core.dsl（M1）；表達式引擎在 M3 加入。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-core")
