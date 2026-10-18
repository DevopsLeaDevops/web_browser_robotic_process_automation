"""配對結果的存放（rpa_desktop.credentials）：權杖在認證管理員、不能用時的退路、主控台版的搬移。"""

import json
import sys
import uuid
from pathlib import Path

import pytest

from rpa_desktop.credentials import (
    Credentials,
    KeyringStore,
    MemoryStore,
    TokenStoreError,
)
from rpa_worker.pairing import PairResult, save_pairing

SERVER = "http://192.168.1.10:8081"


class BrokenStore:
    """不能用的認證管理員（沒有後端、被公司政策擋下）。"""

    def get(self, key: str) -> str | None:
        raise TokenStoreError("no backend")

    def set(self, key: str, token: str) -> None:
        raise TokenStoreError("no backend")

    def delete(self, key: str) -> None:
        raise TokenStoreError("no backend")


def result(token: str = "tok", device: str = "win-01") -> PairResult:
    return PairResult(SERVER, device, "Windows", "worker", token, 1, "f", "0.1.0")


def test_token_goes_to_the_store_not_the_file(tmp_path: Path, store: MemoryStore) -> None:
    credentials = Credentials(tmp_path, store)
    saved = credentials.save(result())

    assert saved.storage == "keyring"
    data = json.loads(credentials.path.read_text(encoding="utf-8"))
    assert data == {"server": SERVER, "device": "win-01", "name": "Windows"}
    assert store.items == {f"win-01@{SERVER}": "tok"}
    loaded = credentials.load()
    assert loaded is not None
    assert (loaded.server, loaded.device, loaded.name, loaded.token) == (
        SERVER,
        "win-01",
        "Windows",
        "tok",
    )


def test_console_pairing_file_is_migrated(tmp_path: Path, store: MemoryStore) -> None:
    save_pairing(tmp_path / "pairing.json", result(token="old-file"))  # #32 主控台版的格式

    loaded = Credentials(tmp_path, store).load()

    assert loaded is not None
    assert loaded.token == "old-file"
    assert loaded.storage == "keyring"
    assert store.items == {f"win-01@{SERVER}": "old-file"}
    assert "token" not in json.loads((tmp_path / "pairing.json").read_text(encoding="utf-8"))


def test_falls_back_to_the_file_when_the_store_fails(tmp_path: Path) -> None:
    credentials = Credentials(tmp_path, BrokenStore())

    saved = credentials.save(result())

    assert saved.storage == "file"
    assert json.loads(credentials.path.read_text(encoding="utf-8"))["token"] == "tok"
    loaded = credentials.load()
    assert loaded is not None
    assert (loaded.token, loaded.storage) == ("tok", "file")
    credentials.clear()  # 認證管理員刪不掉也不影響清除檔案
    assert not credentials.path.exists()


def test_missing_token_means_not_paired(tmp_path: Path, store: MemoryStore) -> None:
    credentials = Credentials(tmp_path, store)
    credentials.save(result())
    store.items.clear()  # 例如使用者在認證管理員裡刪掉了
    assert credentials.load() is None


def test_new_pairing_replaces_the_old_one(tmp_path: Path, store: MemoryStore) -> None:
    credentials = Credentials(tmp_path, store)
    credentials.save(result(token="a", device="win-01"))
    credentials.save(result(token="b", device="win-02"))
    assert store.items == {f"win-02@{SERVER}": "b"}
    credentials.clear()
    assert store.items == {}
    assert credentials.load() is None


def test_bad_files_are_not_paired(tmp_path: Path, store: MemoryStore) -> None:
    credentials = Credentials(tmp_path, store)
    assert credentials.load() is None
    credentials.path.write_text("{not json", encoding="utf-8")
    assert credentials.load() is None
    credentials.path.write_text('["a"]', encoding="utf-8")
    assert credentials.load() is None
    credentials.path.write_text('{"device": "x", "token": "t"}', encoding="utf-8")
    assert credentials.load() is None  # 沒有伺服器網址


def test_real_keyring_round_trip_or_clear_error() -> None:
    """真的認證管理員：Windows 上要能存取；其他環境沒有後端時要變成 TokenStoreError。"""
    pytest.importorskip("keyring")
    keys = KeyringStore(service="RPA Worker test")
    key = f"test-{uuid.uuid4().hex}"
    try:
        keys.set(key, "secret")
    except TokenStoreError:
        if sys.platform == "win32":
            raise
        return
    try:
        assert keys.get(key) == "secret"
    finally:
        keys.delete(key)
    assert keys.get(key) is None
    keys.delete(key)  # 刪除不存在的項目不算錯
