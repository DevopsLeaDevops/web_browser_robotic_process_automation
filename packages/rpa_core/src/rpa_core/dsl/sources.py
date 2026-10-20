"""場景由哪些檔案組成，以及場景內容的雜湊。

雜湊每次執行都記在 result.json 的 scenarioHash；管理 Portal 的發布門檻與領域資料夾的版本說明檔
（M11）都用它確認「通過驗證的就是要發布的版本」。放在 rpa-core，資料夾的校驗不必依賴瀏覽器；
rpa-runner 沿用同一組函式。演算法改了會讓所有既有的雜湊對不上，不能修改。
"""

import hashlib
from pathlib import Path

from rpa_core.dsl.scenario import Scenario

__all__ = ["scenario_digest", "scenario_sources"]


def scenario_sources(path: Path, scenario: Scenario) -> list[str]:
    """場景由哪些檔案組成（相對於場景檔所在的資料夾）：場景檔，加上腳本場景的兩支腳本。"""
    sources = [path.name]
    if scenario.script is not None:
        sources += [scenario.script.automation, scenario.script.assertion]
    return sources


def scenario_digest(path: Path, scenario: Scenario) -> str:
    """場景內容的雜湊（sha256）：依序串起每個檔案的相對路徑與位元組。"""
    digest = hashlib.sha256()
    for relative in scenario_sources(path, scenario):
        digest.update(relative.encode() + b"\0" + (path.parent / relative).read_bytes() + b"\0")
    return digest.hexdigest()
