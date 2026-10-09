"""rpa_core：場景 DSL 的模型、校驗與表達式引擎。

M0 只提供版本資訊；DSL 模型在 M1 加入。
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-core")
