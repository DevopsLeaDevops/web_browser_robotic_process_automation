"""Worker API 的資料格式：管理 Portal 交給遠端 worker 的任務、執行目錄的打包（M9a，ADR 0012）。

兩邊都用這裡的函式編碼與解碼，格式只寫在一個地方。

- 任務（:class:`JobPayload`）：場景檔與腳本以 base64 傳送，worker 照位元組寫出——
  發布門檻比對的雜湊是對位元組算的，Windows 的換行轉換不能碰它。
- 執行目錄打包成 zip 上傳；解開時只接受安全的相對路徑、限制檔案數與大小。
"""

import base64
import re
import shutil
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Final, cast

from rpa_core.i18n import Locale, parse_locale
from rpa_runner.login import LoginSettings

__all__ = [
    "API_PREFIX",
    "CLAIM_WAIT_SECONDS",
    "HEARTBEAT_SECONDS",
    "LEASE_SECONDS",
    "MAX_ARTIFACT_BYTES",
    "MAX_ARTIFACT_FILES",
    "ArtifactError",
    "JobPayload",
    "is_safe_path",
    "pack_directory",
    "unpack_directory",
]

API_PREFIX: Final = "/worker-api/v1"
HEARTBEAT_SECONDS: Final = 5.0
"""執行中每隔這麼久向管理 Portal 報到一次（順便知道要不要取消）。"""
LEASE_SECONDS: Final = 60.0
"""這麼久沒有報到，管理 Portal 把執行標為「worker 失聯」。"""
CLAIM_WAIT_SECONDS: Final = 25.0
"""領取任務的長輪詢最多等這麼久。"""
MAX_ARTIFACT_BYTES: Final = 512 * 1024 * 1024
"""一次執行的產物（解壓後）最多這麼大。"""
MAX_ARTIFACT_FILES: Final = 2000

_SAFE_PART: Final = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")


def is_safe_path(name: str) -> bool:
    """相對路徑，每一段只有英數字、底線、點、連字號，不能是 . 或 .. 開頭。"""
    if not name or len(name) > 400 or "\\" in name or name.startswith("/"):
        return False
    return all(_SAFE_PART.match(part) for part in PurePosixPath(name).parts)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: object) -> bytes:
    if not isinstance(text, str):
        raise ValueError("expected base64 text")
    return base64.b64decode(text.encode("ascii"), validate=True)


@dataclass(frozen=True, slots=True)
class JobPayload:
    """管理 Portal 交給遠端 worker 的一個任務。"""

    run_id: str
    files: Mapping[str, bytes]
    """場景檔與腳本：相對路徑 → 內容（位元組）。"""
    scenario_file: str = "scenario.yaml"
    inputs: Mapping[str, object] = field(default_factory=dict[str, object])
    engine: str | None = None
    base_url: str | None = None
    headless: bool = True
    deadline_ms: int | None = None
    locale: Locale | None = None
    login: LoginSettings | None = None
    """角色的登入設定；state 路徑由 worker 換成自己的暫存檔。"""
    login_state: bytes | None = None
    """角色目前的登入狀態檔內容（storageState JSON）；還沒登入過時是 None。"""
    secrets: Mapping[str, str] = field(default_factory=dict[str, str])
    record_video: bool = False
    """錄影（M12）；舊版管理 Portal 不會送這個欄位，就不錄。"""

    def to_json(self) -> dict[str, object]:
        login = None
        if self.login is not None:
            login = self.login.to_json()
            login.pop("state", None)
        return {
            "runId": self.run_id,
            "files": {name: _b64(data) for name, data in self.files.items()},
            "scenarioFile": self.scenario_file,
            "inputs": dict(self.inputs),
            "engine": self.engine,
            "baseUrl": self.base_url,
            "headless": self.headless,
            "deadlineMs": self.deadline_ms,
            "locale": self.locale,
            "login": login,
            "loginState": _b64(self.login_state) if self.login_state is not None else None,
            "secrets": dict(self.secrets),
            "recordVideo": self.record_video,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object], *, state_path: Path) -> "JobPayload":
        """解讀管理 Portal 的回應；格式不對或路徑不安全時拋出 ValueError。"""
        run_id = data.get("runId")
        if not isinstance(run_id, str) or not is_safe_path(run_id) or "/" in run_id:
            raise ValueError("invalid runId")
        raw_files = data.get("files")
        if not isinstance(raw_files, dict) or not raw_files:
            raise ValueError("invalid files")
        files: dict[str, bytes] = {}
        for name, content in cast("dict[object, object]", raw_files).items():
            if not isinstance(name, str) or not is_safe_path(name):
                raise ValueError(f"unsafe file name: {name!r}")
            files[name] = _unb64(content)
        scenario_file = str(data.get("scenarioFile") or "scenario.yaml")
        if scenario_file not in files:
            raise ValueError("scenario file missing")
        login_data = data.get("login")
        login = None
        if isinstance(login_data, dict):
            values = dict(cast("dict[str, object]", login_data))
            values["state"] = str(state_path)
            login = LoginSettings.from_json(values)
        state = data.get("loginState")
        inputs = data.get("inputs")
        secrets = data.get("secrets")
        deadline = data.get("deadlineMs")
        engine = data.get("engine")
        base_url = data.get("baseUrl")
        return cls(
            run_id=run_id,
            files=files,
            scenario_file=scenario_file,
            inputs=dict(cast("dict[str, object]", inputs)) if isinstance(inputs, dict) else {},
            engine=engine if isinstance(engine, str) else None,
            base_url=base_url if isinstance(base_url, str) else None,
            headless=data.get("headless") is not False,
            deadline_ms=deadline if isinstance(deadline, int) else None,
            locale=parse_locale(str(data.get("locale") or "")),
            login=login,
            login_state=_unb64(state) if state is not None else None,
            secrets={
                str(key): str(value) for key, value in cast("dict[object, object]", secrets).items()
            }
            if isinstance(secrets, dict)
            else {},
            record_video=data.get("recordVideo") is True,
        )


class ArtifactError(ValueError):
    """上傳的執行目錄不合規定（路徑不安全、檔案太多或太大、不是 zip）。"""


def pack_directory(folder: Path, target: Path) -> int:
    """把執行目錄打包成 zip，回傳檔案數。只放一般檔案，路徑用 / 分隔。"""
    count = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.write(path, path.relative_to(folder).as_posix())
                count += 1
    return count


def unpack_directory(source: Path, folder: Path) -> list[str]:
    """把上傳的 zip 解到執行目錄（必須還不存在或是空的），回傳檔案清單。

    任何一個檔名不安全、檔案數或解壓後大小超過上限，就整個拒絕、不留下任何檔案。
    """
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise ArtifactError("not a zip file") from error
    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) > MAX_ARTIFACT_FILES:
            raise ArtifactError(f"too many files: {len(members)}")
        if sum(item.file_size for item in members) > MAX_ARTIFACT_BYTES:
            raise ArtifactError("artifacts too large")
        names = [item.filename for item in members]
        for name in names:
            if not is_safe_path(name):
                raise ArtifactError(f"unsafe path: {name!r}")
        if len(set(names)) != len(names):
            raise ArtifactError("duplicate file names")
        folder.mkdir(parents=True, exist_ok=True)
        if any(folder.iterdir()):
            raise ArtifactError("run directory is not empty")
        written = 0
        try:
            for item in members:
                target = folder / item.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as reader, target.open("wb") as writer:
                    while chunk := reader.read(1024 * 1024):
                        written += len(chunk)
                        if written > MAX_ARTIFACT_BYTES:
                            raise ArtifactError("artifacts too large")
                        writer.write(chunk)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return sorted(names)
