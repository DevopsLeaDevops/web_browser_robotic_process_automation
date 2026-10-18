"""桌面端測試共用的 fixture。"""

import pytest

from rpa_desktop.credentials import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    """記憶體裡的認證管理員：測試不寫進作業系統的認證管理員。"""
    return MemoryStore()
