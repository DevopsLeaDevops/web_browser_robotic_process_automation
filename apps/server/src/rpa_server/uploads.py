"""上傳的檔案（M7c）：檔案入參的值 ``{"file": id, …}`` 參照的檔案。

- **存放**：內容放在資料目錄的 ``input-files/<sha256 前兩碼>/<sha256>``，同內容只存一份；資料表
  ``uploaded_files`` 一次上傳一列（檔名、大小、類型、上傳與最後使用的時間）。
- **上傳**：一個請求一個檔案，內容就是請求的本體（不用 multipart），一段一段寫進暫存檔、邊寫邊算
  sha256，超過單檔上限就拒絕（D4）。
- **執行前檢查**（:meth:`UploadService.check`）：參照的檔案在不在、大小與類型、一次執行合計；
  網頁看到的檔名、大小與 sha256 以伺服器的為準。場景附件檢查在不在版本裡；那台電腦上的路徑
  （``path``）由執行的那台檢查。
- **保留**（D7）：上傳後 24 小時沒被用到就刪；用過的保留到最後一次使用後的保留天數；總量超過
  上限時從最久沒用的開始刪；組合場景固定入參用到的（``pinned``）不刪。只刪內容，資料表那一列
  留著（運行紀錄看得到當時的檔名）。
"""

import contextlib
import hashlib
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal, cast

import anyio
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from rpa_core.dsl import Scenario
from rpa_core.dsl.files import (
    MAX_FILE_BYTES,
    MAX_RUN_BYTES,
    FileValueError,
    accepts,
    clean_name,
    file_values,
    format_size,
    guess_media_type,
    uploaded_ids,
)
from rpa_server.domain import now
from rpa_server.errors import ServiceError, invalid
from rpa_server.i18n import t
from rpa_server.models import UploadedFile

__all__ = [
    "DEFAULT_KEEP_DAYS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "UNUSED_HOURS",
    "UploadLimits",
    "UploadService",
    "definition_uploads",
    "read_body",
    "upload_json",
]

logger = logging.getLogger(__name__)

DEFAULT_KEEP_DAYS: Final = 90
"""用過的檔案保留到最後一次使用後幾天。"""
DEFAULT_MAX_TOTAL_BYTES: Final = 10 * 1024**3
"""全部上傳檔合計的上限。"""
UNUSED_HOURS: Final = 24
"""上傳後這麼久沒被用到就刪掉（選了檔又沒執行）。"""
_SWEEP_SECONDS: Final = 3600.0
_CHUNK: Final = 1024 * 1024

DeleteReason = Literal["unused", "expired", "quota"]


@dataclass(frozen=True, slots=True)
class UploadLimits:
    """上傳與保留的上限（伺服器設定可以改，見 config.py）。"""

    max_file: int = MAX_FILE_BYTES
    max_run: int = MAX_RUN_BYTES
    keep_days: int = DEFAULT_KEEP_DAYS
    max_total: int = DEFAULT_MAX_TOTAL_BYTES


def definition_uploads(definition: Mapping[str, object]) -> list[str]:
    """組合場景定義裡，節點固定值用到的上傳檔代號（第二期 (2)）。"""
    values: list[object] = []
    nodes = definition.get("nodes")
    for node in cast("list[object]", nodes) if isinstance(nodes, list) else []:
        if not isinstance(node, Mapping):
            continue
        inputs = cast("Mapping[str, object]", node).get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        for binding in cast("Mapping[str, object]", inputs).values():
            if isinstance(binding, Mapping) and "value" in binding:
                values.append(cast("Mapping[str, object]", binding)["value"])
    return uploaded_ids(values)


def upload_json(row: UploadedFile) -> dict[str, object]:
    """給 API 與頁面的說明；``file``、``name``、``size``、``sha256`` 就是檔案入參的值。"""
    return {
        "file": row.id,
        "name": row.name,
        "size": row.size,
        "sha256": row.sha256,
        "mediaType": row.media_type,
        "createdAt": row.created_at.isoformat(timespec="seconds"),
        "deleted": row.deleted_at is not None,
    }


async def read_body(request: Request, limit: int) -> bytes:
    """讀完請求的本體（例如場景附件）；超過 ``limit`` 位元組就拒絕。"""
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > limit:
        raise _too_large(limit)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise _too_large(limit)
    return bytes(data)


def _too_large(limit: int) -> ServiceError:
    return ServiceError(413, "file_too_large", t("error.file_too_large", limit=format_size(limit)))


class UploadService:
    """上傳檔的存放、檢查、使用紀錄與清理。"""

    def __init__(
        self, sessions: sessionmaker[Session], root: Path, limits: UploadLimits | None = None
    ) -> None:
        self.sessions = sessions
        self.folder = root.absolute() / "input-files"
        self.limits = limits or UploadLimits()
        self.pinned: Callable[[], Collection[str]] = lambda: ()
        """不能刪的檔案（組合場景固定入參用到的）；由 Services 接上。"""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def blob(self, digest: str) -> Path:
        return self.folder / digest[:2] / digest

    # ------------------------------------------------------------ 上傳

    async def receive(
        self, request: Request, name: str, *, client_id: str | None = None
    ) -> dict[str, object]:
        """把請求的本體存成一個上傳檔，回傳說明（同 :func:`upload_json`）。"""
        shown = clean_name(name or "file")
        limit = self.limits.max_file
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            raise _too_large(limit)
        directory = anyio.Path(self.folder)
        await directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".incoming-{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        size = 0
        try:
            async with await anyio.open_file(temporary, "wb") as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise _too_large(limit)
                    digest.update(chunk)
                    await handle.write(chunk)
            sha = digest.hexdigest()
            target = anyio.Path(self.blob(sha))
            await target.parent.mkdir(parents=True, exist_ok=True)
            if await target.exists():
                await temporary.unlink(missing_ok=True)
            else:
                await temporary.rename(target)
        except BaseException:
            await temporary.unlink(missing_ok=True)
            raise
        media = request.headers.get("content-type") or ""
        if not media or media.startswith(("application/octet-stream", "text/plain")):
            media = guess_media_type(shown)
        row = UploadedFile(
            id=uuid.uuid4().hex,
            sha256=sha,
            name=shown,
            size=size,
            media_type=media.split(";")[0].strip()[:100],
            created_at=now(),
            client_id=client_id,
        )
        with self.sessions() as session:
            session.add(row)
            session.commit()
            return upload_json(row)

    # ------------------------------------------------------------ 查詢

    def get(self, file_id: str) -> UploadedFile | None:
        """上傳檔（含已刪除內容的）；不存在時回傳 None。"""
        with self.sessions() as session:
            return session.get(UploadedFile, file_id)

    def path(self, file_id: str) -> Path | None:
        """上傳檔的內容在伺服器的哪裡；不存在或已刪除時回傳 None。"""
        row = self.get(file_id)
        if row is None or row.deleted_at is not None:
            return None
        path = self.blob(row.sha256)
        return path if path.is_file() else None

    def rows(self, ids: Iterable[str]) -> dict[str, UploadedFile]:
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return {}
        with self.sessions() as session:
            found = session.scalars(select(UploadedFile).where(UploadedFile.id.in_(wanted)))
            return {row.id: row for row in found}

    # ------------------------------------------------------------ 執行前檢查

    def check(
        self,
        scenario: Scenario,
        inputs: Mapping[str, object],
        attachments: Mapping[str, int],
    ) -> tuple[dict[str, object], list[dict[str, str]]]:
        """檢查檔案入參，回傳 (整理過的入參, 問題)。

        ``inputs`` 是這次給的入參（沒給的用場景預設值，預設值只會是附件或路徑）；
        ``attachments`` 是這個版本的附件（``files/檔名`` → 大小）。上傳檔的大小與 sha256 以伺服器的
        為準，網頁看到的檔名沒寫時用上傳時的檔名。
        """
        values = dict(inputs)
        problems: list[dict[str, str]] = []
        found = self.rows(uploaded_ids(values.values()))
        total = 0
        for name, spec in scenario.inputs.items():
            if spec.type != "file":
                continue
            given = name in values
            raw = values[name] if given else spec.default
            if raw is None:
                continue
            multiple = bool(spec.multiple)
            try:
                items = file_values(raw, multiple=multiple)
            except FileValueError as error:
                problems.append({"name": name, "message": error.message})
                continue
            limit = min(spec.max_bytes or self.limits.max_file, self.limits.max_file)
            normalized: list[object] = []
            for item in items:
                size: int | None = None
                shown = item.display_name
                if item.source == "upload":
                    row = found.get(item.ref)
                    if row is None or row.deleted_at is not None:
                        problems.append(
                            {
                                "name": name,
                                "message": t("error.file_missing", name=name, file=item.name or ""),
                            }
                        )
                        continue
                    shown = clean_name(item.name) if item.name else row.name
                    size = row.size
                    normalized.append(
                        {"file": row.id, "name": shown, "size": row.size, "sha256": row.sha256}
                    )
                elif item.source == "attachment":
                    size = attachments.get(item.ref)
                    if size is None:
                        problems.append(
                            {
                                "name": name,
                                "message": t("error.file_attachment", name=name, file=item.ref),
                            }
                        )
                        continue
                    normalized.append(item.to_json())
                else:
                    # 那台電腦上的路徑：在不在、多大、在不在允許的資料夾由執行的那台檢查
                    normalized.append(item.to_json())
                    continue
                if size > limit:
                    problems.append(
                        {
                            "name": name,
                            "message": t(
                                "error.file_input_too_large",
                                name=name,
                                file=shown,
                                size=format_size(size),
                                limit=format_size(limit),
                            ),
                        }
                    )
                elif not accepts(spec.accept, shown):
                    problems.append(
                        {
                            "name": name,
                            "message": t(
                                "error.file_input_type",
                                name=name,
                                file=shown,
                                accept=", ".join(spec.accept or ()),
                            ),
                        }
                    )
                total += size
            if given:
                values[name] = normalized if multiple else (normalized[0] if normalized else raw)
        if total > self.limits.max_run:
            problems.append(
                {
                    "name": "",
                    "message": t(
                        "error.files_too_large",
                        size=format_size(total),
                        limit=format_size(self.limits.max_run),
                    ),
                }
            )
        return values, problems

    def require(
        self, scenario: Scenario, inputs: Mapping[str, object], attachments: Mapping[str, int]
    ) -> dict[str, object]:
        """同 :meth:`check`，有問題時拋出 inputs_invalid（和其他入參問題相同的格式）。"""
        values, problems = self.check(scenario, inputs, attachments)
        if problems:
            raise invalid(
                "inputs_invalid", t("error.inputs_invalid", count=len(problems)), problems=problems
            )
        return values

    def prepare(
        self,
        scenario: Scenario,
        inputs: Mapping[str, object],
        revision_dir: Path,
        target: Path,
    ) -> list[tuple[str, Path]]:
        """調試與接著錄製（M7c）：上傳檔與附件以網頁要看到的檔名放進 ``target``，回傳
        ``(入參, 檔案)``，給子程序的 ``--file``。``path`` 值由那台自己找；同一個入參不能混用。

        ``inputs`` 是整理過的入參（:meth:`check` 之後）；沒給的用場景預設值。
        """
        prepared: list[tuple[str, Path]] = []
        for name, spec in scenario.inputs.items():
            if spec.type != "file":
                continue
            raw = inputs.get(name, spec.default)
            if raw is None:
                continue
            items = file_values(raw, multiple=bool(spec.multiple))
            sources = {item.source for item in items}
            if "path" in sources:
                if len(sources) > 1:
                    raise invalid("inputs_invalid", t("error.file_mixed", name=name))
                continue
            for index, item in enumerate(items):
                source = self.path(item.ref) if item.source == "upload" else revision_dir / item.ref
                if source is None or not source.is_file():
                    raise invalid(
                        "inputs_invalid",
                        t("error.file_missing", name=name, file=item.name or item.ref),
                    )
                path = target / name / str(index) / item.display_name
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, path)
                except OSError:
                    shutil.copyfile(source, path)
                prepared.append((name, path))
        return prepared

    def touch(self, values: Iterable[object], moment: datetime | None = None) -> None:
        """記下這些入參用到的上傳檔的使用時間（保留天數從這裡算）。"""
        ids = uploaded_ids(values)
        if not ids:
            return
        with self.sessions() as session:
            session.execute(
                update(UploadedFile).where(UploadedFile.id.in_(ids)).values(used_at=moment or now())
            )
            session.commit()

    # ------------------------------------------------------------ 清理

    def usage(self) -> dict[str, int]:
        """目前保存的上傳檔：幾個、內容合計多大（同內容只算一次）。"""
        with self.sessions() as session:
            rows = (
                session.execute(
                    select(UploadedFile.sha256, UploadedFile.size).where(
                        UploadedFile.deleted_at.is_(None)
                    )
                )
                .tuples()
                .all()
            )
        return {"count": len(rows), "bytes": sum(dict(rows).values())}

    def sweep(self, moment: datetime | None = None) -> list[str]:
        """依保留規則刪掉檔案內容，回傳被刪的上傳檔代號。"""
        moment = moment or now()
        pinned = set(self.pinned())
        deleted: list[str] = []
        with self._lock, self.sessions() as session:
            rows = list(
                session.scalars(
                    select(UploadedFile)
                    .where(UploadedFile.deleted_at.is_(None))
                    .order_by(UploadedFile.created_at, UploadedFile.id)
                )
            )
            kept: list[UploadedFile] = []
            for row in rows:
                reason: DeleteReason | None = None
                if row.id in pinned:
                    pass
                elif row.used_at is None:
                    if row.created_at + timedelta(hours=UNUSED_HOURS) <= moment:
                        reason = "unused"
                elif row.used_at + timedelta(days=self.limits.keep_days) <= moment:
                    reason = "expired"
                if reason is None:
                    kept.append(row)
                else:
                    self._mark(row, reason, moment)
                    deleted.append(row.id)
            total = sum({row.sha256: row.size for row in kept}.values())
            oldest = sorted(
                (row for row in kept if row.id not in pinned and row.used_at is not None),
                key=lambda row: cast("datetime", row.used_at),
            )
            for row in oldest:
                if total <= self.limits.max_total:
                    break
                if row.used_at is not None and row.used_at + timedelta(hours=UNUSED_HOURS) > moment:
                    break  # 剛用過的不刪（可能正在執行）
                total -= row.size
                self._mark(row, "quota", moment)
                deleted.append(row.id)
            session.commit()
            live = set(
                session.scalars(
                    select(UploadedFile.sha256).where(UploadedFile.deleted_at.is_(None))
                )
            )
        for digest in {row.sha256 for row in rows if row.id in set(deleted)} - live:
            with contextlib.suppress(OSError):
                self.blob(digest).unlink()
        if deleted:
            logger.info("刪除了 %d 個上傳檔的內容（保留規則）", len(deleted))
        return deleted

    @staticmethod
    def _mark(row: UploadedFile, reason: DeleteReason, moment: datetime) -> None:
        row.deleted_at = moment
        row.deleted_reason = reason

    def start(self) -> None:
        """啟動時清理一次，之後每小時一次。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="upload-sweeper", daemon=True)
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
                logger.exception("清理上傳檔失敗")
            self._stop.wait(_SWEEP_SECONDS)
