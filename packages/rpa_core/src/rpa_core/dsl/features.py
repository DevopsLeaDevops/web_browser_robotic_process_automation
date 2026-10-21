"""DSL 的擴充（M7a 起）：要交出去的內容用到哪些，這份程式看得懂哪些。

錄製端與 Worker 是各自安裝的 App，可能比管理 Portal 舊。舊的 App 讀到看不懂的欄位，
只會回一句「場景校驗失敗」（例如 M7a 之前的 App 讀到定位器的 ``frame``）。所以：

- App 上線時回報它看得懂的擴充（:data:`FEATURES`，經由 ``WorkerInfo.to_json()`` 的 ``features``）；
- 管理 Portal 把場景、登入設定交給某台裝置之前，用 :func:`missing_features` 比對，
  缺少時直接說明要更新哪個 App。沒有回報 ``features`` 的（M7a 之前的 App）當作一個都不懂。

之後新增會讓舊程式讀不懂的 DSL 欄位時，在 :data:`FEATURES` 加上名稱，並在 :func:`data_features`
認出它。
"""

from collections.abc import Iterable, Mapping
from typing import Final, cast

from rpa_core.dsl.scenario import Scenario

__all__ = ["FEATURES", "data_features", "missing_features", "scenario_features"]

FEATURES: Final[frozenset[str]] = frozenset({"frame", "anyFrame"})
"""這份程式看得懂的擴充：定位器的 ``frame``、``anyFrame``（M7a，iframe）。"""


def data_features(data: object) -> frozenset[str]:
    """DSL 資料（camelCase 的 dict／list，例如場景、角色的登入檢查與自動登入步驟）用到的擴充。

    任何一層的 dict 有 ``frame: {…}`` 就是 ``frame``，有 ``anyFrame: true`` 就是 ``anyFrame``。
    """
    found: set[str] = set()
    pending: list[object] = [data]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            values = cast("Mapping[object, object]", item)
            if isinstance(values.get("frame"), Mapping):
                found.add("frame")
            if values.get("anyFrame") is True:
                found.add("anyFrame")
            pending.extend(values.values())
        elif isinstance(item, list | tuple):
            pending.extend(cast("Iterable[object]", item))
    return frozenset(found)


def scenario_features(scenario: Scenario) -> frozenset[str]:
    """場景用到的擴充。"""
    return data_features(scenario.model_dump(mode="json", by_alias=True, exclude_none=True))


def missing_features(required: Iterable[str], reported: object) -> list[str]:
    """要用到、但裝置沒有回報看得懂的擴充（排序過）。

    ``reported`` 是裝置上線時回報的 ``features``；不是清單（M7a 之前的 App 沒有這一項）時
    當作一個都不懂。
    """
    known: set[str] = set()
    if isinstance(reported, list | tuple):
        known = {str(item) for item in cast("Iterable[object]", reported)}
    return sorted(set(required) - known)
