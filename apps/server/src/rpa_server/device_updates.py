"""裝置跟著伺服器的版本更新（ADR 0018 第二階段）：Worker API 與 Client API 的 ``/update``。

伺服器正在用的版本資料夾裡的 ``update.zip``（``rpa update`` 裝新版本時留下；用完整的分發包安裝
時，拿同一版的更新檔執行一次 ``rpa update`` 放進去）就是裝置要追的版本。裝置上線時回報 App
種類、目標、環境代號、目前的版本與上次退回的版本，這裡回覆 ``status``：

- ``current``：已經是伺服器的版本；
- ``available``：可以更新（版本、大小、SHA-256），``GET /update/file`` 下載；
- ``full``：環境代號不同（或更新檔沒有這個目標），要用完整的安裝包；
- ``failed``：這個版本在這台裝置上啟動失敗、已經退回，不再自動更新；
- ``off``：管理 Portal 關掉了「自動更新裝置」；
- ``unavailable``：伺服器沒有更新檔（從 clone 執行，或還沒放更新檔）。

回覆的格式固定，也不檢查協定版本：之後協定改變時，舊的 App 也能先更新到伺服器的版本。
裝置回報的狀態只記在記憶體，裝置頁顯示。
"""

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from sqlalchemy.orm import Session, sessionmaker

from rpa_server.errors import invalid
from rpa_server.i18n import t
from rpa_server.models import Setting
from rpa_server.updates import RELEASE_ENV, UPDATE_FILE
from rpa_update.errors import UpdateError
from rpa_update.manifest import Manifest, UpdateFile
from rpa_update.runtime import Runtime, load_runtime

__all__ = ["STATUSES", "DeviceReport", "DeviceUpdates", "Status"]

type Status = Literal["current", "available", "full", "failed", "off", "unavailable"]
STATUSES: Final = ("current", "available", "full", "failed", "off", "unavailable")
_SETTING: Final = "device_updates"
_APPS: Final = ("worker", "recorder")

logger = logging.getLogger("rpa_server.device_updates")


@dataclass(frozen=True, slots=True)
class DeviceReport:
    """裝置上線前回報的內容。"""

    app: str
    target: str
    runtime: str
    release: str
    version: str = ""
    failed: str | None = None

    @classmethod
    def from_json(cls, body: Mapping[str, object]) -> "DeviceReport":
        def text(key: str, limit: int = 100) -> str:
            value = body.get(key)
            return value[:limit] if isinstance(value, str) else ""

        report = cls(
            app=text("app"),
            target=text("target"),
            runtime=text("runtime"),
            release=text("release"),
            version=text("version"),
            failed=text("failed") or None,
        )
        if report.app not in _APPS or not report.target or not report.runtime:
            raise invalid("update_report_invalid", t("error.update_report_invalid"))
        return report


@dataclass(frozen=True, slots=True)
class _Offer:
    manifest: Manifest
    path: Path
    size: int
    sha256: str


class DeviceUpdates:
    """伺服器的更新檔、「自動更新裝置」設定，以及每台裝置最近一次的回報。"""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        release_dir: Path | None,
        runtime: Runtime | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.sessions = sessions
        self.release_dir = release_dir
        self.runtime = runtime
        self.clock = clock
        self._lock = threading.Lock()
        self._cache: tuple[tuple[int, int], _Offer | None] | None = None
        self._reports: dict[tuple[str, str], dict[str, object]] = {}

    @classmethod
    def detect(
        cls, sessions: sessionmaker[Session], environ: Mapping[str, str] | None = None
    ) -> "DeviceUpdates":
        """分發包（bin/rpa 設定了 ``RPA_RELEASE_DIR``）用版本資料夾的更新檔；其他沒有更新檔。"""
        env = os.environ if environ is None else environ
        release = env.get(RELEASE_ENV)
        try:
            runtime = load_runtime()
        except UpdateError as error:
            logger.warning("runtime.json 讀不了：%s", error.code)
            runtime = None
        return cls(sessions, Path(release) if release else None, runtime)

    # ------------------------------------------------------------ 更新檔

    def _offer(self) -> _Offer | None:
        """伺服器的更新檔（驗證過簽章與內容）；沒有或不能用時是 None。檔案沒變就沿用上次的結果。"""
        if self.release_dir is None or self.runtime is None:
            return None
        path = self.release_dir / UPDATE_FILE
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if self._cache is not None and self._cache[0] == key:
                return self._cache[1]
        offer: _Offer | None = None
        try:
            with UpdateFile(path, self.runtime.keys) as update:
                update.check()
                manifest = update.manifest
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            offer = _Offer(manifest, path, stat.st_size, digest.hexdigest())
        except (UpdateError, OSError) as error:
            logger.warning("更新檔 %s 不能用：%s", path, getattr(error, "code", error))
        with self._lock:
            self._cache = (key, offer)
        return offer

    def file(self) -> Path | None:
        offer = self._offer()
        return offer.path if offer is not None else None

    # ------------------------------------------------------------ 設定

    def auto(self) -> bool:
        """「自動更新裝置」：沒設定過是開。"""
        with self.sessions() as session:
            row = session.get(Setting, _SETTING)
            value = row.value.get("auto") if row is not None else None
        return value is not False

    def set_auto(self, enabled: bool) -> bool:
        with self.sessions() as session:
            row = session.get(Setting, _SETTING)
            if row is None:
                session.add(Setting(key=_SETTING, value={"auto": enabled}))
            else:
                row.value = {**row.value, "auto": enabled}
            session.commit()
        return enabled

    # ------------------------------------------------------------ 裝置

    def offer(self, kind: str, device: str, body: Mapping[str, object]) -> dict[str, object]:
        """裝置上線前的更新檢查（格式見模組說明）。"""
        report = DeviceReport.from_json(body)
        offer = self._offer()
        reply: dict[str, object]
        status: Status
        if offer is None:
            status, reply = "unavailable", {}
        else:
            manifest = offer.manifest
            reply = {"version": manifest.version, "release": manifest.release}
            needed = manifest.runtime_for(report.target)
            if report.release == manifest.release:
                status = "current"
            elif needed is None or needed != report.runtime:
                status = "full"
            elif report.failed == manifest.release:
                status = "failed"
            elif not self.auto():
                status = "off"
            else:
                status = "available"
                reply.update(size=offer.size, sha256=offer.sha256)
        with self._lock:
            self._reports[(kind, device)] = {
                "status": status,
                "release": report.release,
                "version": report.version,
                "failed": report.failed,
                "target": report.target,
                "at": self.clock(),
            }
        return {"status": status, **reply}

    def report(self, kind: str, device: str) -> dict[str, object] | None:
        """這台裝置最近一次的更新檢查（裝置頁用）；伺服器啟動後還沒回報過是 None。"""
        with self._lock:
            found = self._reports.get((kind, device))
            return dict(found) if found is not None else None

    def summary(self) -> dict[str, object]:
        """裝置頁的「裝置更新」：設定與伺服器的更新檔。"""
        offer = self._offer()
        info: dict[str, object] = {"auto": self.auto(), "packaged": self.release_dir is not None}
        if offer is not None:
            manifest = offer.manifest
            targets = sorted(manifest.runtimes)
            info.update(
                version=manifest.version, release=manifest.release, size=offer.size, targets=targets
            )
        return info
