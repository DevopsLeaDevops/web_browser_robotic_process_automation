"""RPA Worker App 的配對結果（M10.1，ADR 0014）：權杖存在作業系統的認證管理員。

- 資料夾裡的 ``pairing.json`` 只放伺服器網址、裝置代號與名稱；權杖放在 Windows 認證管理員
  （macOS 是鑰匙圈），經由 ``keyring``。
- 認證管理員不能用時（沒有後端、被公司政策擋下），權杖退回存在 ``pairing.json``
  （和命令列 worker 相同，只有本人能讀寫），並記在日誌。
- 第一步主控台版（#32）把權杖存在 ``pairing.json``：讀到時搬進認證管理員，檔案裡的權杖刪掉。

主控台版（``--worker``）與視窗版用同一份配對，兩者不會同時執行（:mod:`rpa_desktop.single_instance`）。
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

from rpa_worker.pairing import PAIRING_FILE, PairResult

__all__ = [
    "DEFAULT_DEVICE",
    "SERVICE",
    "Credentials",
    "KeyringStore",
    "MemoryStore",
    "Pairing",
    "TokenStore",
    "TokenStoreError",
    "default_store",
]

logger = logging.getLogger("rpa_desktop.credentials")

SERVICE: Final = "RPA Worker"
"""認證管理員裡的項目名稱（「一般認證」的網際網路或網路位址）。"""


class TokenStoreError(Exception):
    """認證管理員不能用。"""


class TokenStore(Protocol):
    """存放權杖的地方（認證管理員；測試用記憶體裡的替身）。"""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, token: str) -> None: ...

    def delete(self, key: str) -> None: ...


class KeyringStore:
    """經由 ``keyring`` 的認證管理員；任何錯誤都轉成 :class:`TokenStoreError`。"""

    def __init__(self, service: str = SERVICE) -> None:
        self.service = service

    def get(self, key: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.service, key)
        except Exception as error:
            raise TokenStoreError(str(error) or type(error).__name__) from error

    def set(self, key: str, token: str) -> None:
        try:
            import keyring

            keyring.set_password(self.service, key, token)
        except Exception as error:
            raise TokenStoreError(str(error) or type(error).__name__) from error

    def delete(self, key: str) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(self.service, key)
            except PasswordDeleteError:
                return  # 本來就沒有
        except Exception as error:
            raise TokenStoreError(str(error) or type(error).__name__) from error


class MemoryStore:
    """記憶體裡的認證管理員：測試用，不寫進作業系統。"""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def set(self, key: str, token: str) -> None:
        self.items[key] = token

    def delete(self, key: str) -> None:
        self.items.pop(key, None)


def default_store() -> TokenStore:
    return KeyringStore()


@dataclass(frozen=True, slots=True)
class Pairing:
    """配對結果：連哪個管理 Portal、用哪個權杖，以及裝置的代號與名稱。"""

    server: str
    device: str
    name: str
    token: str
    storage: str = "keyring"
    """權杖存在哪裡：``keyring``（認證管理員）或 ``file``（退路）。"""


DEFAULT_DEVICE: Final = "worker"
"""配對檔沒有裝置代號時用的代號（讀取與清除要一致）。"""


def _key(server: str, device: str) -> str:
    return f"{device}@{server}"


def _device(data: dict[str, object]) -> str:
    device = data.get("device")
    return device if isinstance(device, str) and device else DEFAULT_DEVICE


class Credentials:
    """一個資料夾的配對結果。"""

    def __init__(self, folder: Path, store: TokenStore | None = None) -> None:
        self.folder = folder
        self.store = default_store() if store is None else store

    @property
    def path(self) -> Path:
        return self.folder / PAIRING_FILE

    def _read(self) -> dict[str, object] | None:
        try:
            data: object = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            logger.warning("配對檔讀不到：%s", error)
            return None
        return cast("dict[str, object]", data) if isinstance(data, dict) else None

    def _write(self, data: dict[str, object]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        temporary.replace(self.path)

    def load(self) -> Pairing | None:
        """讀回配對；檔案裡還有權杖（主控台版或退路）時試著搬進認證管理員。

        沒有配對時回傳 None；認證管理員讀不到（不是「沒有這一項」）時拋出 :class:`TokenStoreError`，
        讓呼叫的人顯示錯誤、稍後重試，而不是要使用者重新配對。
        """
        data = self._read()
        if data is None:
            return None
        server = data.get("server")
        if not isinstance(server, str) or not server:
            return None
        device_id = _device(data)
        name = data.get("name")
        label = name if isinstance(name, str) and name else device_id
        token = data.get("token")
        key = _key(server, device_id)
        if isinstance(token, str) and token:
            try:
                self.store.set(key, token)
            except TokenStoreError as error:
                logger.warning("認證管理員不能用，權杖仍存在配對檔：%s", error)
                return Pairing(server, device_id, label, token, storage="file")
            self._write({"server": server, "device": device_id, "name": label})
            logger.info("權杖已從配對檔搬到認證管理員")
            return Pairing(server, device_id, label, token)
        try:
            stored = self.store.get(key)
        except TokenStoreError as error:
            logger.warning("認證管理員讀不到權杖：%s", error)
            raise
        if not stored:
            logger.warning("認證管理員裡沒有這次配對的權杖，需要重新配對")
            return None
        return Pairing(server, device_id, label, stored)

    def save(self, result: PairResult) -> Pairing:
        """存下新的配對（換掉舊的）；回傳權杖實際存在哪裡。"""
        self.clear()
        data: dict[str, object] = {
            "server": result.server,
            "device": result.device,
            "name": result.name,
        }
        storage = "keyring"
        try:
            self.store.set(_key(result.server, result.device), result.token)
        except TokenStoreError as error:
            logger.warning("認證管理員不能用，權杖改存在配對檔：%s", error)
            data["token"] = result.token
            storage = "file"
        self._write(data)
        return Pairing(result.server, result.device, result.name, result.token, storage)

    def clear(self) -> None:
        """清除配對（重新配對、權杖被拒時）：認證管理員的項目與配對檔都刪掉。"""
        data = self._read()
        if data is not None:
            server = data.get("server")
            if isinstance(server, str):
                try:
                    self.store.delete(_key(server, _device(data)))
                except TokenStoreError as error:
                    logger.warning("認證管理員的權杖刪不掉：%s", error)
        self.path.unlink(missing_ok=True)
