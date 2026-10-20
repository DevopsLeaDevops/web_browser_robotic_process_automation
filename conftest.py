"""整個倉庫共用的 pytest 設定：依測試檔案的路徑加上角色標記（見 tools/ci_roles.py）。"""

import pytest

from tools.ci_roles import markers_for


@pytest.hookimpl(tryfirst=True)  # 在 -m 篩選之前加上標記
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = config.rootpath
    for item in items:
        try:
            path = item.path.relative_to(root).as_posix()
        except ValueError:
            continue
        callspec = getattr(item, "callspec", None)
        params: dict[str, object] = dict(callspec.params) if callspec is not None else {}
        for name in markers_for(path, params):
            item.add_marker(name)
