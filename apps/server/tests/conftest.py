"""rpa-server 測試共用：每個測試一個暫存資料目錄與 SQLite。

FastAPI 與 SQLAlchemy 在 fixture 裡才載入，不需要它們的測試（樣板、檔案儲存）可以單獨執行。
"""

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rpa_core.i18n import use_locale
from rpa_server.config import Settings, sqlite_url

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx2 import Client

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


@pytest.fixture(autouse=True)
def _browsers_downloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """登入檢查在哪台跑，要看伺服器這台下載了哪些瀏覽器：測試一律當作都有，結果不隨環境而變；
    要測沒有的情況時，測試自己換掉 ``services.roles.local_engines``。"""
    try:
        from rpa_server import roles
    except ImportError:  # 沒有 SQLAlchemy 的環境：只跑樣板與檔案儲存的測試
        return
    monkeypatch.setattr(roles, "_LOCAL_BROWSERS", lambda: frozenset(roles.ENGINES))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    return Settings(
        data_dir=data,
        database_url=sqlite_url(data / "rpa.db"),
        examples_dir=DEMO,
        start_worker=False,
        # 預設不建立領域、不匯入範例；需要的測試自己建立或呼叫 seed_examples_domain
        seed_examples=False,
    )


@pytest.fixture
def app(settings: Settings) -> "FastAPI":
    """沒有背景 worker 的伺服器：測試自己呼叫 ``app.state.worker.run_once()`` 執行佇列。"""
    from rpa_server.app import create_app

    return create_app(settings)


@pytest.fixture
def client(app: "FastAPI") -> Iterator["Client"]:
    """TestClient 是 httpx2.Client 的子類別。"""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client
