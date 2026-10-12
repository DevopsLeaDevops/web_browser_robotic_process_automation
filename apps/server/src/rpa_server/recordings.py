"""錄製（M4）：Playwright codegen 錄製稿 → DSL 草稿 → 新的場景或新版本。

- **在這台電腦錄製**：啟動 ``playwright codegen``，瀏覽器視窗開在執行 Portal 的電腦上；
  使用者操作完關掉視窗即結束。錄製中的原始稿（可能含密碼）放在暫存檔，轉換後刪除。
- **貼上錄製稿**：用 ``rpa record`` 或在別台電腦錄好的 codegen 原始稿，直接轉換。
- 轉換結果一律是草稿版本，之後一樣要驗證通過才能發布；原始錄製稿遮罩密碼後保存，只當來源。
- 選了登入角色時，錄製前載入該角色的登入狀態，草稿寫上 ``login: { role: … }``。
"""

import re
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.i18n import Locale, use_locale
from rpa_core.recording import Conversion, ConversionError, convert_recording
from rpa_server.domain import DOMAIN_ID, RecordingRecord, now
from rpa_server.errors import ServiceError, conflict, invalid, not_found
from rpa_server.i18n import t
from rpa_server.models import Recording
from rpa_server.processes import child_env, launch, stop
from rpa_server.storage import SCENARIO_FILE, Storage

if TYPE_CHECKING:
    from rpa_server.roles import RoleService
    from rpa_server.services import Services

__all__ = ["RAW_FILE", "RecordingService", "RecordingTarget", "codegen_command"]

RAW_FILE: Final = "raw.py"
"""遮罩過密碼的原始錄製稿。"""
_UNMASKED: Final = ".recording.py"
"""錄製中 codegen 寫入的原始稿（可能含密碼）；轉換後刪除。"""
ENGINES: Final = ("chromium", "firefox")
LIST_LIMIT: Final = 50

type Launch = Callable[..., subprocess.Popen[str]]


@dataclass(frozen=True, slots=True)
class RecordingTarget:
    """轉換結果放到哪裡：新場景（代號、名稱、領域）或既有場景的新版本。"""

    scene_id: str
    new: bool
    name: str | None = None
    domain_id: str | None = None
    category: str | None = None


def codegen_command(output: Path, url: str, engine: str, storage: Path | None) -> list[str]:
    """``python -m playwright codegen``：瀏覽器視窗與 Playwright Inspector 開在這台電腦上。"""
    command = [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--target",
        "python",
        "--output",
        str(output),
        "--browser",
        engine,
    ]
    if storage is not None:
        command += ["--load-storage", str(storage)]
    return [*command, url]


def _record(row: Recording) -> RecordingRecord:
    return RecordingRecord(
        id=row.id,
        scene_id=row.scene_id,
        scene_name=row.scene_name,
        new_scene=row.new_scene,
        domain_id=row.domain_id,
        revision_number=row.revision_number,
        source=row.source,
        url=row.url,
        engine=row.engine,
        role_id=row.role_id,
        status=row.status,
        warnings=list(row.warnings),
        error=row.error,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


def _new_id(moment: datetime) -> str:
    return f"rec-{moment.astimezone(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _check_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise invalid("recording_url_invalid", t("error.recording_url_invalid", value=value))
    return value


class RecordingService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: Storage,
        services: "Services",
        roles: "RoleService",
        *,
        display: bool,
        locale: Locale,
        launcher: Launch | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.services = services
        self.roles = roles
        self.display = display
        self.locale: Locale = locale
        self.launcher: Launch = launcher or launch
        """啟動 codegen 的方式；測試換成不開瀏覽器的假程式。"""
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[str]] = {}

    # ------------------------------------------------------------ 查詢

    def list_recordings(self, limit: int = LIST_LIMIT) -> list[RecordingRecord]:
        with self.sessions() as session:
            rows = session.scalars(
                select(Recording)
                .order_by(Recording.created_at.desc(), Recording.id.desc())
                .limit(limit)
            )
            return [_record(row) for row in rows]

    def get_recording(self, recording_id: str) -> RecordingRecord:
        with self.sessions() as session:
            row = session.get(Recording, recording_id)
            if row is None:
                raise not_found(
                    "recording_not_found", t("error.recording_not_found", id=recording_id)
                )
            return _record(row)

    def files(self, recording_id: str) -> dict[str, str]:
        """遮罩過的原始錄製稿與轉換結果（有的話）。"""
        self.get_recording(recording_id)
        found: dict[str, str] = {}
        for name in (RAW_FILE, SCENARIO_FILE):
            path = self.storage.recording_file(recording_id, name)
            if path is not None:
                found[name] = path.read_text(encoding="utf-8")
        return found

    @property
    def active(self) -> list[str]:
        with self._lock:
            return [key for key, process in self._processes.items() if process.poll() is None]

    # ------------------------------------------------------------ 目標

    def _target(self, target: RecordingTarget) -> RecordingTarget:
        """檢查目標並補上名稱與分類：新場景不能已經存在，既有場景要存在而且沒有封存。"""
        scene_id = target.scene_id.strip()
        if target.new:
            if not DOMAIN_ID.fullmatch(scene_id):
                raise invalid("scene_id_invalid", t("error.scene_id_invalid", id=scene_id))
            name = (target.name or "").strip()
            if not name:
                raise invalid("scene_name_missing", t("error.scene_name_missing"))
            if self.services.scene_exists(scene_id):
                raise conflict("scene_exists", t("error.scene_exists", id=scene_id))
            if target.domain_id:
                self.services.get_domain(target.domain_id)
            category = (target.category or "").strip() or None
            return RecordingTarget(scene_id, True, name[:200], target.domain_id or None, category)
        scene = self.services.get_scene(scene_id)
        if scene.archived:
            raise conflict("scene_archived", t("error.scene_archived", id=scene_id))
        return RecordingTarget(scene_id, False, scene.name, scene.domain_id, scene.category)

    def _role(self, role_id: str | None) -> str | None:
        role_id = (role_id or "").strip() or None
        if role_id is not None and not self.roles.exists(role_id):
            raise not_found("role_not_found", t("error.role_not_found", id=role_id))
        return role_id

    # ------------------------------------------------------------ 錄製

    def start(
        self,
        target: RecordingTarget,
        *,
        url: str | None,
        engine: str = "chromium",
        role_id: str | None = None,
    ) -> RecordingRecord:
        """在這台電腦開瀏覽器錄製；使用者關掉視窗時轉換成草稿。"""
        if not self.display:
            raise invalid("display_unavailable", t("error.record_display_unavailable"))
        if engine not in ENGINES:
            raise invalid("engine_invalid", t("error.role_engine_invalid", engine=engine))
        start_url = _check_url(url)
        if start_url is None:
            raise invalid("recording_url_invalid", t("error.recording_url_invalid", value=""))
        checked = self._target(target)
        role = self._role(role_id)
        storage = self.storage.role_state(role) if role is not None else None
        if storage is not None and not storage.is_file():
            storage = None  # 角色還沒登入過：照樣錄製，從登入頁開始
        with self._lock:
            if any(process.poll() is None for process in self._processes.values()):
                raise conflict("recording_active", t("error.recording_active"))
            moment = now()
            recording_id = _new_id(moment)
            folder = self.storage.recording_dir(recording_id)
            folder.mkdir(parents=True)
            row = self._row(recording_id, checked, "codegen", start_url, engine, role, moment)
            with self.sessions() as session:
                session.add(row)
                session.commit()
                record = _record(row)
            process = self.launcher(
                codegen_command(folder / _UNMASKED, start_url, engine, storage),
                env=child_env(self.locale),
                log=folder / "codegen.log",
                cwd=folder,
                pipes=False,
            )
            self._processes[recording_id] = process
        threading.Thread(
            target=self._wait, args=(recording_id, process), name=recording_id, daemon=True
        ).start()
        return record

    @staticmethod
    def _row(
        recording_id: str,
        target: RecordingTarget,
        source: str,
        url: str | None,
        engine: str,
        role: str | None,
        moment: datetime,
    ) -> Recording:
        return Recording(
            id=recording_id,
            scene_id=target.scene_id,
            scene_name=target.name or target.scene_id,
            new_scene=target.new,
            domain_id=target.domain_id,
            category=target.category,
            revision_number=None,
            source=source,
            url=url,
            engine=engine,
            role_id=role,
            status="recording",
            warnings=[],
            error=None,
            created_at=moment,
        )

    def _wait(self, recording_id: str, process: subprocess.Popen[str]) -> None:
        process.wait()
        with self._lock:
            self._processes.pop(recording_id, None)
        with use_locale(self.locale):
            folder = self.storage.recording_dir(recording_id)
            unmasked = folder / _UNMASKED
            with self.sessions() as session:
                row = session.get(Recording, recording_id)
                if row is None or row.status != "recording":
                    unmasked.unlink(missing_ok=True)
                    return
            try:
                source = unmasked.read_text(encoding="utf-8")
            except OSError:
                source = ""
            finally:
                unmasked.unlink(missing_ok=True)
            if not source.strip():
                tail = _tail(folder / "codegen.log")
                message = t("recording.nothing_recorded")
                self._fail(recording_id, f"{message} {tail}".strip())
                return
            try:
                self._convert(recording_id, source, require_actions=True)
            except ServiceError as error:
                self._fail(recording_id, error.message)

    def cancel(self, recording_id: str) -> RecordingRecord:
        with self._lock:
            process = self._processes.get(recording_id)
        record = self.get_recording(recording_id)
        if record.status != "recording":
            raise conflict("recording_finished", t("error.recording_finished", id=recording_id))
        with self.sessions() as session:
            row = session.get(Recording, recording_id)
            if row is not None:
                row.status = "cancelled"
                row.finished_at = now()
                session.commit()
        if process is not None:
            threading.Thread(target=stop, args=(process,), daemon=True).start()
        return self.get_recording(recording_id)

    # ------------------------------------------------------------ 匯入

    def import_source(
        self,
        source: str,
        target: RecordingTarget,
        *,
        url: str | None = None,
        engine: str = "chromium",
        role_id: str | None = None,
    ) -> RecordingRecord:
        """貼上的錄製稿：馬上轉換，成功時建立場景或新版本。"""
        if engine not in ENGINES:
            raise invalid("engine_invalid", t("error.role_engine_invalid", engine=engine))
        if not source.strip():
            raise invalid("recording_empty", t("error.recording_empty"))
        checked = self._target(target)
        role = self._role(role_id)
        start_url = _check_url(url)
        conversion = self._conversion(source, checked, start_url, engine, role)
        moment = now()
        recording_id = _new_id(moment)
        self.storage.recording_dir(recording_id).mkdir(parents=True)
        with self.sessions() as session:
            session.add(self._row(recording_id, checked, "import", start_url, engine, role, moment))
            session.commit()
        try:
            self._save(recording_id, checked, conversion)
        except ServiceError as error:
            self._fail(recording_id, error.message)
            raise
        return self.get_recording(recording_id)

    # ------------------------------------------------------------ 轉換與存檔

    def _conversion(
        self,
        source: str,
        target: RecordingTarget,
        url: str | None,
        engine: str,
        role: str | None,
    ) -> Conversion:
        try:
            return convert_recording(
                source,
                scene_id=target.scene_id,
                name=target.name or target.scene_id,
                url=url,
                engine=engine,
                role=role,
                category=target.category,
            )
        except ConversionError as error:
            raise invalid("recording_unconvertible", str(error)) from error

    def _convert(self, recording_id: str, source: str, *, require_actions: bool) -> None:
        record = self.get_recording(recording_id)
        target = RecordingTarget(
            record.scene_id,
            record.new_scene,
            record.scene_name,
            record.domain_id,
            self._category(recording_id),
        )
        if not target.new:
            target = self._target(RecordingTarget(record.scene_id, False))
        conversion = self._conversion(source, target, record.url, record.engine, record.role_id)
        if require_actions and conversion.steps <= 1 and not conversion.warnings:
            folder = self.storage.recording_dir(recording_id)
            (folder / RAW_FILE).write_text(conversion.masked_source, encoding="utf-8")
            raise invalid("recording_no_actions", t("recording.no_actions"))
        self._save(recording_id, target, conversion)

    def _category(self, recording_id: str) -> str | None:
        with self.sessions() as session:
            row = session.get(Recording, recording_id)
            return row.category if row is not None else None

    def _save(self, recording_id: str, target: RecordingTarget, conversion: Conversion) -> None:
        folder = self.storage.recording_dir(recording_id)
        (folder / RAW_FILE).write_text(conversion.masked_source, encoding="utf-8")
        (folder / SCENARIO_FILE).write_text(conversion.scenario, encoding="utf-8")
        files = {SCENARIO_FILE: conversion.scenario}
        note = t("revision.note_recorded", id=recording_id)
        if target.new:
            self.services.add_scene(target.scene_id, files, note=note, domain_id=target.domain_id)
            number = 1
        else:
            latest = self.services.get_scene(target.scene_id).latest_number
            number = self.services.save_revision(
                target.scene_id, base=latest, files=files, note=note
            ).number
        with self.sessions() as session:
            row = session.get(Recording, recording_id)
            if row is None:
                return
            row.status = "done"
            row.revision_number = number
            row.warnings = [warning.to_json() for warning in conversion.warnings]
            row.finished_at = now()
            session.commit()

    def _fail(self, recording_id: str, message: str) -> None:
        with self.sessions() as session:
            row = session.get(Recording, recording_id)
            if row is None:
                return
            row.status = "failed"
            row.error = message
            row.finished_at = now()
            session.commit()

    # ------------------------------------------------------------ 啟動與關閉

    def recover(self) -> int:
        """伺服器啟動時：上次錄製到一半的標為失敗，刪除可能含密碼的暫存原始稿。"""
        for leftover in self.storage.recordings.glob(f"*/{_UNMASKED}"):
            leftover.unlink(missing_ok=True)
        with self.sessions() as session:
            rows = list(session.scalars(select(Recording).where(Recording.status == "recording")))
            for row in rows:
                row.status = "failed"
                row.error = t("recording.interrupted")
                row.finished_at = now()
            session.commit()
            return len(rows)

    def close(self) -> None:
        with self._lock:
            processes = list(self._processes.values())
        for process in processes:
            stop(process, grace=1)


def _tail(log: Path, lines: int = 3) -> str:
    """codegen 日誌的最後幾行（例如瀏覽器沒下載的錯誤），去掉 ANSI 顏色碼。"""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    kept: Sequence[str] = [line.strip() for line in clean.splitlines() if line.strip()][-lines:]
    return " ".join(kept)
