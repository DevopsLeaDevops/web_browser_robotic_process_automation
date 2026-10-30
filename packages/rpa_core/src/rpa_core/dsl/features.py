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

from rpa_core.dsl.dynamic import FEATURE as DYNAMIC_VALUES
from rpa_core.dsl.dynamic import uses_dynamic
from rpa_core.dsl.files import attachment_names, uploaded_ids
from rpa_core.dsl.scenario import Scenario

__all__ = [
    "FEATURES",
    "FILE_INPUTS",
    "JSON_INPUTS",
    "PYTHON_NODES",
    "UPLOAD",
    "data_features",
    "input_features",
    "missing_features",
    "scenario_features",
]

UPLOAD: Final = "upload"
"""``upload`` 步驟（M7c）。"""
FILE_INPUTS: Final = "fileInputs"
"""``type: file`` 的入參、檔案入參的值與下載入參檔案（M7c）。"""
PYTHON_NODES: Final = "pythonNodes"
"""Python 節點的新寫法（ADR 0020）：``script`` 的 ``runtime``、``files``、``platforms``，
以及沒有 ``assertion``（改用 ``verify``）的 Python 節點。"""
JSON_INPUTS: Final = "jsonInputs"
"""``type: array``、``type: object`` 的入參（ADR 0020）。"""

FEATURES: Final[frozenset[str]] = frozenset(
    {
        "frame",
        "anyFrame",
        "page",
        "popup",
        DYNAMIC_VALUES,
        UPLOAD,
        FILE_INPUTS,
        PYTHON_NODES,
        JSON_INPUTS,
    }
)
"""這份程式看得懂的擴充：定位器的 ``frame``、``anyFrame``（M7a，iframe）；
步驟的 ``page``、``popup``（M7b，新分頁）；入參的 ``dynamicValues``（日期、隨機數）；
``upload`` 步驟與 ``fileInputs``（M7c，上傳檔案）；
``pythonNodes`` 與 ``jsonInputs``（Python 節點，ADR 0020）。"""


def data_features(data: object) -> frozenset[str]:
    """DSL 資料（camelCase 的 dict／list，例如場景、角色的登入檢查與自動登入步驟）用到的擴充。

    任何一層的 dict 有 ``frame: {…}`` 就是 ``frame``，有 ``anyFrame: true`` 就是 ``anyFrame``；
    有 ``page: 名稱``、``popup: 名稱``（步驟）就是 ``page``、``popup``；``action: upload`` 就是
    ``upload``。
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
            for key in ("page", "popup"):
                if isinstance(values.get(key), str):
                    found.add(key)
            if values.get("action") == UPLOAD:
                found.add(UPLOAD)
            pending.extend(values.values())
        elif isinstance(item, list | tuple):
            pending.extend(cast("Iterable[object]", item))
    return frozenset(found)


def scenario_features(scenario: Scenario) -> frozenset[str]:
    """場景用到的擴充；入參的預設值用了動態值時加上 ``dynamicValues``，有檔案入參時加上
    ``fileInputs``，有 array、object 入參時加上 ``jsonInputs``，用了 Python 節點的新寫法時
    加上 ``pythonNodes``。"""
    found = data_features(scenario.model_dump(mode="json", by_alias=True, exclude_none=True))
    if uses_dynamic(spec.default for spec in scenario.inputs.values()):
        found |= {DYNAMIC_VALUES}
    if any(spec.type == "file" for spec in scenario.inputs.values()):
        found |= {FILE_INPUTS}
    if any(spec.type in ("array", "object") for spec in scenario.inputs.values()):
        found |= {JSON_INPUTS}
    script = scenario.script
    if script is not None and (
        script.runtime is not None
        or script.files is not None
        or script.platforms is not None
        or script.assertion is None
    ):
        found |= {PYTHON_NODES}
    return found


def input_features(values: Mapping[str, object] | None) -> frozenset[str]:
    """一次執行給的入參用到的擴充：有動態值就是 ``dynamicValues``（求值在執行的那台裝置）；
    有上傳檔或場景附件就是 ``fileInputs``。"""
    found: set[str] = set()
    if values and uses_dynamic(values.values()):
        found.add(DYNAMIC_VALUES)
    if values and (uploaded_ids(values.values()) or attachment_names(values.values())):
        found.add(FILE_INPUTS)
    return frozenset(found)


def missing_features(required: Iterable[str], reported: object) -> list[str]:
    """要用到、但裝置沒有回報看得懂的擴充（排序過）。

    ``reported`` 是裝置上線時回報的 ``features``；不是清單（M7a 之前的 App 沒有這一項）時
    當作一個都不懂。
    """
    known: set[str] = set()
    if isinstance(reported, list | tuple):
        known = {str(item) for item in cast("Iterable[object]", reported)}
    return sorted(set(required) - known)
