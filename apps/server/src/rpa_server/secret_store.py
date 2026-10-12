"""Secrets 的值：管理 Portal 保存在資料目錄的 secrets.json（M4）。

- 只有本人能讀寫（0600）；M8 改成加密存放。
- 頁面與 API 只看得到名稱與更新時間，永遠不回傳值。
- 執行時把場景與登入角色用到的值交給 rpa-runner；沒有保存的名稱再從同名的環境變數找。
"""

import json
import os
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from rpa_server.domain import now

__all__ = ["SECRET_NAME", "SecretInfo", "SecretStore"]

SECRET_NAME: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
"""Secrets 名稱的規則（與 DSL 相同）：大寫英文字母、數字與 _，例如 ERP_PASSWORD。"""


@dataclass(frozen=True, slots=True)
class SecretInfo:
    name: str
    updated_at: datetime

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "updatedAt": self.updated_at.isoformat(timespec="seconds")}


class SecretStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            data: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return cast("dict[str, dict[str, str]]", data) if isinstance(data, dict) else {}

    def _write(self, data: Mapping[str, Mapping[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(self.path)

    def names(self) -> list[SecretInfo]:
        with self._lock:
            data = self._read()
        return [
            SecretInfo(name, datetime.fromisoformat(item.get("updatedAt") or now().isoformat()))
            for name, item in sorted(data.items())
        ]

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._read()

    def set(self, name: str, value: str) -> SecretInfo:
        moment = now()
        with self._lock:
            data = self._read()
            data[name] = {"value": value, "updatedAt": moment.isoformat(timespec="seconds")}
            self._write(data)
        return SecretInfo(name, moment.replace(microsecond=0))

    def delete(self, name: str) -> bool:
        with self._lock:
            data = self._read()
            if name not in data:
                return False
            del data[name]
            self._write(data)
            return True

    def values(self) -> dict[str, str]:
        """全部的值：只交給執行用，不要顯示或寫進日誌。"""
        with self._lock:
            return {name: item.get("value", "") for name, item in self._read().items()}
