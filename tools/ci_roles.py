"""測試的角色分組：CI 依生產環境裡各系統的角色挑選要跑的瀏覽器測試。

短期的主要運行路徑（2026-10-19 使用者確認，見 docs/develop/ci.html）：

- Linux 只跑網站（管理 Portal；setup-linux.sh 用 --no-local-worker --no-testsite，不裝瀏覽器）
- macOS 只跑錄製端（RPA 錄製端 App）
- Windows 只跑 Worker（RPA Worker App）

根目錄的 conftest.py 依測試檔案的路徑加上 ``role_server``、``role_worker`` 或 ``role_recorder``；
``engine`` 參數是 firefox 的測試另外加上 ``firefox``。CI 再用 ``-m`` 依角色挑測試，例如：

    -m "not browser or ((smoke or role_server or role_recorder) and not firefox)"   # Linux
    -m "browser and (role_worker or smoke)"                                          # Windows

最長的路徑前綴優先。沒有對應角色的測試（核心、命令列、桌面端的共用部分）不加角色標記；
它們不需要瀏覽器，每個 PR 都在 Linux 上跑。新增測試檔案時，依它驗證的是哪個角色的路徑，
在 ``ROLES`` 加上路徑；整個目錄已經登記的不用另外加。
"""

from collections.abc import Mapping
from typing import Final

ROLES: Final[Mapping[str, str]] = {
    # 網站：管理 Portal 的頁面、API、佇列與組合場景的調度；測試網站是場景的目標
    "apps/server/": "server",
    "apps/testsite/": "server",
    # Worker：執行場景（子程序、瀏覽器、登入、Firefox 設定檔範本）、領取任務
    "packages/rpa_runner/": "worker",
    "apps/worker/": "worker",
    "apps/desktop/tests/test_selftest.py": "worker",
    # 錄製端：逐步調試、錄製、互動子程序、本機閘道
    "packages/rpa_runner/tests/test_debug.py": "recorder",
    "apps/worker/tests/test_recorder.py": "recorder",
    "apps/worker/tests/test_interactive.py": "recorder",
    "apps/worker/tests/test_gateway.py": "recorder",
}
"""測試路徑的前綴（相對倉庫根目錄、用 /）→ 角色。"""

FIREFOX: Final = "firefox"


def role_of(path: str) -> str | None:
    """測試檔案屬於哪個角色；最長的前綴優先，沒有對應時回傳 None。"""
    matches = [prefix for prefix in ROLES if path.startswith(prefix)]
    return ROLES[max(matches, key=len)] if matches else None


def markers_for(path: str, params: Mapping[str, object]) -> list[str]:
    """測試要加上的標記：角色（``role_…``），以及用 Firefox 執行的 ``firefox``。"""
    markers: list[str] = []
    if role := role_of(path):
        markers.append(f"role_{role}")
    if params.get("engine") == FIREFOX:
        markers.append(FIREFOX)
    return markers
