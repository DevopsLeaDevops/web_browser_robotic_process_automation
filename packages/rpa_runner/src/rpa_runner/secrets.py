"""Secrets：M2 從同名的環境變數讀取（例如 ERP_PASSWORD），M8 改為加密存放。

值只放在記憶體與子程序的環境變數裡，不寫進入參、事實、日誌、報告或執行目錄；
錯誤訊息裡出現的值一律遮罩。
"""

import os
from collections.abc import Mapping
from typing import Final

from rpa_core.dsl import Scenario

__all__ = ["MASK", "mask", "missing_secrets", "read_secrets"]

MASK: Final = "***"


def read_secrets(scenario: Scenario, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """場景宣告的 secrets 中，環境變數有設定的那些。"""
    source = os.environ if environ is None else environ
    return {name: source[name] for name in scenario.secrets if name in source}


def missing_secrets(scenario: Scenario, environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [name for name in scenario.secrets if name not in source]


def mask(text: str, secrets: Mapping[str, str]) -> str:
    """把文字中出現的 secret 值換成 ***（長度 3 以下的值不遮罩，避免把一般文字也蓋掉）。"""
    for value in sorted(secrets.values(), key=len, reverse=True):
        if len(value) > 3:
            text = text.replace(value, MASK)
    return text
