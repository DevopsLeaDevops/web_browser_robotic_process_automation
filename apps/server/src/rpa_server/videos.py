"""運行的錄影（M12，ADR 0016）：設定、運行結束時的紀錄、保留與清理、釘選。

- 設定存在 settings 表的 ``video``：要不要錄、通過的運行留幾天、其他結果留幾天、全部錄影最多多大。
  預設照使用者 2026-10-20 的決定（D1）：驗證、執行、組合場景的節點全部錄；通過的留 7 天，失敗、
  逾時、取消、需要登入的留 30 天；全部最多 20 GB。
- 運行結束時讀執行目錄的 video.json，把長度與大小記在 runs（清單、篩選與清理用）。
- 清理只刪影片（video.webm 與所有分頁片段）：運行紀錄、報告、截圖、日誌都留著；
  runs 記下刪除的時間與原因，
  執行目錄的 run.json（M11）同步拿掉這個檔案。釘選的不刪。超過保留天數的先刪；總量還是超過上限，
  從最舊的刪起。伺服器啟動時、每小時、改設定後各清理一次。
"""

import contextlib
import json
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_runner.files import VIDEO
from rpa_runner.video import read_info, video_files
from rpa_server.domain import now
from rpa_server.models import Run, Setting
from rpa_server.storage import Storage

__all__ = [
    "DeleteReason",
    "VideoService",
    "VideoSettings",
    "load_settings",
    "video_details",
]

logger = logging.getLogger("rpa_server.videos")

_SETTING_KEY: Final = "video"
_SWEEP_SECONDS: Final = 3600.0
"""每隔這麼久清理一次過期的錄影。"""
_RUN_MANIFEST: Final = "run.json"
_GB: Final = 1024**3
DeleteReason = Literal["expired", "quota"]


@dataclass(frozen=True, slots=True)
class VideoSettings:
    """錄影設定（管理 Portal 的「運行回看」頁）。"""

    enabled: bool = True
    keep_passed_days: int = 7
    """通過的運行，錄影保留幾天（0 代表運行結束就刪）。"""
    keep_other_days: int = 30
    """失敗、逾時、取消、需要登入的運行，錄影保留幾天。"""
    max_total_gb: float = 20.0
    """全部錄影最多佔多少空間；超過時從最舊的刪起（釘選的不算在內、也不刪）。"""

    def to_json(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "keepPassedDays": self.keep_passed_days,
            "keepOtherDays": self.keep_other_days,
            "maxTotalGb": self.max_total_gb,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "VideoSettings":
        """讀設定；缺少或不合理的值用預設值（設定由 API 寫入時已經校驗過）。"""
        base = cls()
        enabled = data.get("enabled")
        passed = data.get("keepPassedDays")
        other = data.get("keepOtherDays")
        total = data.get("maxTotalGb")
        return cls(
            enabled=enabled if isinstance(enabled, bool) else base.enabled,
            keep_passed_days=_days(passed, base.keep_passed_days),
            keep_other_days=_days(other, base.keep_other_days),
            max_total_gb=float(total)
            if isinstance(total, int | float) and not isinstance(total, bool) and total > 0
            else base.max_total_gb,
        )

    def keep_days(self, status: str) -> int:
        return self.keep_passed_days if status == "passed" else self.keep_other_days


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def _days(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3650:
        return value
    return default


def load_settings(session: Session) -> VideoSettings:
    row = session.get(Setting, _SETTING_KEY)
    return VideoSettings.from_json(row.value) if row is not None else VideoSettings()


def video_details(run: Run, settings: VideoSettings | None = None) -> dict[str, object] | None:
    """一次運行的錄影狀態（API 與頁面用）；從來沒有錄影時回傳 None。

    ``settings`` 有給時加上依保留規則會保留到何時（釘選的是 None）。
    """
    if run.video_seconds is None and run.video_deleted_at is None:
        return None
    details: dict[str, object] = {
        "seconds": run.video_seconds,
        "bytes": run.video_bytes,
        "pinned": run.video_pinned,
        "deletedAt": _iso(run.video_deleted_at),
        "deletedReason": run.video_deleted_reason,
        "url": f"/runs/{run.id}/files/{VIDEO}" if run.video_deleted_at is None else None,
    }
    if settings is not None:
        keep = None
        if run.video_deleted_at is None and not run.video_pinned and run.finished_at is not None:
            keep = run.finished_at + timedelta(days=settings.keep_days(run.status))
        details["keepUntil"] = _iso(keep)
    return details


class VideoService:
    """錄影的設定、紀錄、釘選與清理。"""

    def __init__(self, sessions: sessionmaker[Session], storage: Storage) -> None:
        self.sessions = sessions
        self.storage = storage
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.on_deleted: Callable[[str], None] = lambda run_id: None
        """一段錄影被刪除後呼叫（測試用）。"""

    # ------------------------------------------------------------ 設定

    def settings(self) -> VideoSettings:
        with self.sessions() as session:
            return load_settings(session)

    def save_settings(self, settings: VideoSettings) -> VideoSettings:
        with self.sessions() as session:
            row = session.get(Setting, _SETTING_KEY)
            if row is None:
                session.add(Setting(key=_SETTING_KEY, value=settings.to_json()))
            else:
                row.value = settings.to_json()
            session.commit()
        self.sweep()
        return settings

    def record_video(self) -> bool:
        """新的任務要不要錄影。"""
        return self.settings().enabled

    def usage(self) -> dict[str, int]:
        """目前保存的錄影：幾段、共多大、其中釘選幾段。"""
        with self.sessions() as session:
            rows = session.execute(
                select(Run.video_bytes, Run.video_pinned).where(
                    Run.video_seconds.is_not(None), Run.video_deleted_at.is_(None)
                )
            ).all()
        return {
            "count": len(rows),
            "bytes": sum(size or 0 for size, _ in rows),
            "pinned": sum(1 for _, pinned in rows if pinned),
        }

    # ------------------------------------------------------------ 運行結束

    def record_finished(self, run: Run) -> None:
        """運行結束時（在呼叫端的資料庫交易裡）：依 video.json 記下錄影的長度與大小。"""
        info = read_info(self.storage.run_dir(run.id))
        if info is None or info.get("file") != VIDEO:
            return
        path = self.storage.run_dir(run.id) / VIDEO
        if not path.is_file():
            return
        duration = info.get("timelineDurationMs", info.get("durationMs"))
        run.video_seconds = (
            round(float(duration) / 1000, 3)
            if isinstance(duration, int | float) and not isinstance(duration, bool)
            else 0.0
        )
        run.video_bytes = sum(
            (path.parent / name).stat().st_size
            for name in video_files(info)
            if (path.parent / name).is_file()
        )
        run.video_deleted_at = None
        run.video_deleted_reason = None

    # ------------------------------------------------------------ 釘選

    def set_pinned(self, run_id: str, pinned: bool) -> Run | None:
        """釘選或取消釘選；運行不存在時回傳 None。"""
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run is None:
                return None
            run.video_pinned = pinned
            session.commit()
        if not pinned:
            self.sweep()
        with self.sessions() as session:
            return session.get(Run, run_id)

    # ------------------------------------------------------------ 清理

    def sweep(self, moment: datetime | None = None) -> list[str]:
        """刪掉過期與超過總量的錄影，回傳被刪的運行編號。"""
        moment = moment or now()
        deleted: list[str] = []
        with self._lock, self.sessions() as session:
            settings = load_settings(session)
            runs = list(
                session.scalars(
                    select(Run)
                    .where(
                        Run.video_seconds.is_not(None),
                        Run.video_deleted_at.is_(None),
                        Run.finished_at.is_not(None),
                    )
                    .order_by(Run.finished_at, Run.id)
                )
            )
            kept: list[Run] = []
            for run in runs:
                finished = cast("datetime", run.finished_at)
                expired = finished + timedelta(days=settings.keep_days(run.status)) <= moment
                if expired and not run.video_pinned:
                    self._delete(run, "expired", moment)
                    deleted.append(run.id)
                else:
                    kept.append(run)
            limit = settings.max_total_gb * _GB
            total = sum(run.video_bytes or 0 for run in kept if not run.video_pinned)
            for run in kept:  # 從最舊的刪起
                if total <= limit:
                    break
                if run.video_pinned:
                    continue
                total -= run.video_bytes or 0
                self._delete(run, "quota", moment)
                deleted.append(run.id)
            session.commit()
        for run_id in deleted:
            self.on_deleted(run_id)
        if deleted:
            logger.info("刪除了 %d 段錄影（保留規則）", len(deleted))
        return deleted

    def _delete(self, run: Run, reason: DeleteReason, moment: datetime) -> None:
        folder = self.storage.run_dir(run.id)
        for name in video_files(read_info(folder) or {"file": VIDEO}):
            with contextlib.suppress(FileNotFoundError):
                (folder / name).unlink()
            _forget_in_manifest(folder / _RUN_MANIFEST, name, moment, reason)
        run.video_deleted_at = moment
        run.video_deleted_reason = reason

    # ------------------------------------------------------------ 背景

    def start(self) -> None:
        """啟動時清理一次，之後每小時一次。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="video-sweeper", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sweep()
            except Exception:
                logger.exception("清理錄影失敗")
            self._stop.wait(_SWEEP_SECONDS)


def _forget_in_manifest(path: Path, name: str, moment: datetime, reason: str) -> None:
    """run.json（M11）的檔案清單拿掉被刪的檔案，記在 removed；讀不到或寫不進去就算了。"""
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    manifest = cast("dict[str, object]", data)
    files = manifest.get("files")
    if isinstance(files, list):
        manifest["files"] = [
            item
            for item in cast("list[object]", files)
            if not (isinstance(item, dict) and cast("dict[str, object]", item).get("path") == name)
        ]
    removed = manifest.get("removed")
    entries = cast("list[object]", removed) if isinstance(removed, list) else []
    entries.append({"path": name, "at": _iso(moment), "reason": reason})
    manifest["removed"] = entries
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
