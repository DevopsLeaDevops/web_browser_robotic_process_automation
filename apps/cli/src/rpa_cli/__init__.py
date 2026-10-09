"""rpa_cli：`rpa` 命令列工具。"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__: str = version("rpa-cli")
