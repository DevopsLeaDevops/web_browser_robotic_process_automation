"""桌面 App 跟著管理 Portal 的版本更新（ADR 0018 第二階段）。

上線時（收到 ``online``，或協定版本不同被拒時）問管理 Portal 有沒有更新：RPA Worker 用
Worker API、RPA 錄製端用 Client API 的 ``POST /update``，回報 App 種類、目標、環境代號、
目前的版本與上次退回的版本。回覆的 ``status``（見 :mod:`rpa_server.device_updates`）：

- ``available``：下載（``GET /update/file``，核對大小與 SHA-256），裝成新的一層
  （:func:`rpa_update.layers.install_layer` 再驗證簽章與每個檔案），重新啟動後使用；
- ``full``：環境代號不同，要重新安裝完整的安裝包；
- ``failed``：這個版本在這台電腦上啟動失敗、退回過，不再自動更新；
- 其他（``current``、``off``、``unavailable``，或舊的管理 Portal 沒有 ``/update``）：不做什麼。

裝好之後怎麼套用由 controller 決定：RPA Worker 的視窗版閒置時重新啟動
（:func:`rpa_update.boot.relaunch`），RPA 錄製端與 ``--no-window`` 下次開啟時套用。
開發環境（沒有 runtime.json）不檢查更新。
"""

import hashlib
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from rpa_update.errors import UpdateError
from rpa_update.layers import current_layer, install_layer, layers_dir, read_active
from rpa_update.runtime import Runtime, load_runtime
from rpa_worker.pairing import App
from rpa_worker.remote import WorkerClient

__all__ = [
    "DOWNLOADS_DIR",
    "MAX_UPDATE_BYTES",
    "Checked",
    "DeviceUpdater",
    "Offer",
    "Updater",
    "detect_updater",
]

logger = logging.getLogger("rpa_desktop.updates")

MAX_UPDATE_BYTES: Final = 256 * 1024 * 1024
"""更新檔最大的大小：管理 Portal 說的再大也不下載。"""
DOWNLOADS_DIR: Final = "downloads"
"""下載中的更新檔放在程式碼層資料夾底下的這裡，裝好就刪掉。"""


@dataclass(frozen=True, slots=True)
class Offer:
    """管理 Portal 對 ``POST /update`` 的回覆。"""

    status: str
    version: str = ""
    release: str = ""
    size: int = 0
    sha256: str = ""

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "Offer":
        def text(key: str) -> str:
            value = data.get(key)
            return value if isinstance(value, str) else ""

        size = data.get("size")
        return cls(
            status=text("status"),
            version=text("version"),
            release=text("release"),
            size=size if isinstance(size, int) and not isinstance(size, bool) else 0,
            sha256=text("sha256").lower(),
        )


@dataclass(frozen=True, slots=True)
class Checked:
    """一次更新檢查的結果。"""

    offer: Offer
    ready: bool = False
    """管理 Portal 的版本已經裝好（這次或之前），重新啟動後使用。"""


class Updater(Protocol):
    """:class:`DeviceUpdater` 的形狀（測試換成替身）。"""

    def check(self, client: WorkerClient) -> Checked: ...


class DeviceUpdater:
    """一個打包的 App（``runtime``）在 ``root``（:func:`rpa_update.layers.layers_dir`）的更新。"""

    def __init__(
        self, app: App, runtime: Runtime, root: Path, *, version: str, current: str
    ) -> None:
        self.app = app
        self.runtime = runtime
        self.root = root
        self.version = version
        self.current = current
        """這個程序用的版本（程式碼層的名稱，用內建的程式時是 runtime.json 的 ``release``）。"""

    @classmethod
    def detect(cls, app: App, version: str) -> "DeviceUpdater | None":
        """打包的 App 才有；開發環境或 runtime.json 讀不了時是 None。"""
        try:
            runtime = load_runtime()
            if runtime is None:
                return None
            root = layers_dir(runtime)
        except UpdateError as error:
            logger.warning("不檢查更新：%s", error)
            return None
        layer = current_layer()
        current = layer.release if layer is not None else runtime.release
        return cls(app, runtime, root, version=version, current=current)

    def report(self) -> dict[str, object]:
        """``POST /update`` 送出的內容。"""
        return {
            "app": self.app,
            "target": self.runtime.target,
            "runtime": self.runtime.id,
            "release": self.current,
            "version": self.version,
            "failed": read_active(self.root).failed,
        }

    def upcoming(self) -> str:
        """下次啟動會用的版本（還沒確認的新一層也算）。"""
        return read_active(self.root).release or self.runtime.release

    def check(self, client: WorkerClient) -> Checked:
        """問管理 Portal；有更新就下載、裝好。

        錯誤：連線與管理 Portal 的錯誤（:class:`rpa_worker.remote.WorkerApiError`、
        :class:`rpa_worker.remote.ConnectionLostError`）、更新檔不能用（:class:`UpdateError`）、
        寫不進資料夾（OSError）。
        """
        offer = Offer.from_json(client.call("POST", "/update", self.report()))
        if offer.status != "available" or not offer.release:
            return Checked(offer)
        if self.upcoming() != offer.release:
            self._install(client, offer)
        return Checked(offer, ready=self.upcoming() == offer.release)

    def _install(self, client: WorkerClient, offer: Offer) -> None:
        if not 0 < offer.size <= MAX_UPDATE_BYTES:
            raise UpdateError("update_too_large", size=offer.size, limit=MAX_UPDATE_BYTES)
        folder = self.root / DOWNLOADS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.glob("*.zip"):  # 上次中斷留下的
            stale.unlink(missing_ok=True)
        path = folder / f"{uuid.uuid4().hex}.zip"
        logger.info("下載更新 %s（%s 位元組）", offer.release, offer.size)
        try:
            size = client.download("/update/file", path, limit=offer.size)
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if size != offer.size or digest.hexdigest() != offer.sha256:
                raise UpdateError("download_mismatch", release=offer.release)
            result = install_layer(self.root, path, self.runtime, protect=[self.current])
        finally:
            path.unlink(missing_ok=True)
        previous = result.previous or "內建的程式"
        logger.info("已裝好 %s（之前是 %s），重新啟動後使用", offer.release, previous)


def detect_updater(app: App, version: str) -> Updater | None:
    """:class:`rpa_desktop.controller.Services` 預設的 ``updater``。"""
    return DeviceUpdater.detect(app, version)
