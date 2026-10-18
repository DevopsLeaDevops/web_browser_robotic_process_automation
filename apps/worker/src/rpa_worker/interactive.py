"""錄製端的互動子程序（M10.2，ADR 0014）：管理 Portal 與錄製端之間的格式，只寫在一個地方。

錄製、逐步調試、人工登入的子程序在**錄製端那台**執行（瀏覽器開在操作的人面前），讀寫檔案、
解析輸出的程式仍在管理 Portal。兩邊經由 Client API（``/client-api/v1``，對外埠）溝通::

    錄製端                                         管理 Portal
    POST /hello（上線、這次啟動的代號）      →
    POST /control（長輪詢，最多 25 秒）      ←  指令：start／input／close／kill（依序號）
    PUT  /processes/<代號>/files（zip）      →  新增或改過的檔案（先傳）
    POST /processes/<代號>/output            →  標準輸出的幾行；結束時附結束碼

- **指令依序號**：``/control`` 帶上已經處理到的序號（``after``），管理 Portal 只在下一次
  輪詢確認後才丟掉指令；回應沒收到也不會漏。長輪詢本身就是心跳。
- **啟動**（``start``）：模組名稱、參數、環境變數、需要的檔案（base64）、要不要標準輸入輸出、
  日誌的檔名。參數與環境變數裡的工作資料夾寫成 :data:`WORK`，錄製端換成自己的暫存資料夾；
  管理 Portal 資料夾以外的檔案（例如角色的登入狀態）放在 ``.inputs/`` 底下。
- **檔案先到**：錄製端每送一行輸出之前，先上傳這段期間新增或改過的檔案（``.inputs/`` 不傳），
  所以管理 Portal 處理那一行時檔案一定已經到了；結束時再同步一次，最後才回報結束碼。
- **失聯**：超過 :data:`LOST_SECONDS` 沒有輪詢，管理 Portal 把這台的子程序視為結束。
  錄製端重新啟動（``/hello`` 的啟動代號不同）時也一樣；錄製端連回來時結束殘留的子程序。
"""

import base64
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Final

__all__ = [
    "CONTROL_WAIT_SECONDS",
    "INPUTS",
    "LOST_SECONDS",
    "MAX_SYNC_BYTES",
    "MAX_SYNC_FILES",
    "WORK",
    "SyncError",
    "b64decode",
    "b64encode",
    "changed_files",
    "is_safe_relative",
    "pack_files",
    "scan",
    "unpack_files",
]

CONTROL_WAIT_SECONDS: Final = 25.0
"""指令的長輪詢最多等這麼久。"""
LOST_SECONDS: Final = 30.0
"""這麼久沒有輪詢，管理 Portal 把錄製端的子程序視為結束。"""
WORK: Final = "{work}"
"""參數與環境變數裡代表工作資料夾的記號。"""
INPUTS: Final = ".inputs"
"""工作資料夾以外的輸入檔放在這裡（不同步回管理 Portal）。"""
MAX_SYNC_BYTES: Final = 256 * 1024 * 1024
"""一次同步（解壓後）最多這麼大。"""
MAX_SYNC_FILES: Final = 2000

Snapshot = dict[str, tuple[int, int]]
"""相對路徑 → （大小, 修改時間 ns）。"""


class SyncError(ValueError):
    """同步的檔案不合規定（路徑不安全、檔案太多或太大、不是 zip）。"""


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(text: object) -> bytes:
    if not isinstance(text, str):
        raise ValueError("expected base64 text")
    return base64.b64decode(text.encode("ascii"), validate=True)


def is_safe_relative(name: str) -> bool:
    """工作資料夾裡的相對路徑：用 / 分隔，不能是絕對路徑，不能有 ``.``、``..`` 或空的一段。

    和執行目錄的規則不同，這裡允許 ``.`` 開頭的檔名（錄製中的原始稿是 ``.recording.py``）。
    """
    if not name or len(name) > 400 or "\\" in name or "\0" in name or name.startswith("/"):
        return False
    parts = name.split("/")
    return all(part and part not in (".", "..") and len(part) <= 200 for part in parts)


def scan(folder: Path, skip: Iterable[str] = (INPUTS,)) -> Snapshot:
    """工作資料夾裡每個一般檔案的大小與修改時間（不跟隨符號連結）。"""
    skipped = tuple(skip)
    found: Snapshot = {}
    if not folder.is_dir():
        return found
    for path in folder.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        name = path.relative_to(folder).as_posix()
        if name.split("/", 1)[0] in skipped:
            continue
        stat = path.stat()
        found[name] = (stat.st_size, stat.st_mtime_ns)
    return found


def changed_files(before: Mapping[str, tuple[int, int]], after: Snapshot) -> list[str]:
    """新增或改過的檔案（刪除的不處理：管理 Portal 那邊保留）。"""
    return sorted(name for name, stamp in after.items() if before.get(name) != stamp)


def pack_files(folder: Path, names: Iterable[str], target: Path) -> int:
    """把幾個檔案打包成 zip，回傳檔案數。打包時已經被刪掉的檔案略過。"""
    count = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = folder / name
            if not is_safe_relative(name) or not path.is_file():
                continue
            try:
                archive.write(path, name)
            except OSError:
                continue
            count += 1
    return count


def unpack_files(source: Path, folder: Path) -> list[str]:
    """把同步的 zip 解到工作資料夾（覆蓋同名的檔案），回傳檔案清單。

    任何一個檔名不安全、檔案數或解壓後大小超過上限，就整個拒絕、不寫任何檔案。
    """
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise SyncError("not a zip file") from error
    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) > MAX_SYNC_FILES:
            raise SyncError(f"too many files: {len(members)}")
        if sum(item.file_size for item in members) > MAX_SYNC_BYTES:
            raise SyncError("files too large")
        names = [item.filename for item in members]
        for name in names:
            if not is_safe_relative(name) or PurePosixPath(name).parts[0] == INPUTS:
                raise SyncError(f"unsafe path: {name!r}")
        if len(set(names)) != len(names):
            raise SyncError("duplicate file names")
        root = folder.resolve()
        for item in members:
            target = folder / item.filename
            if not target.resolve().is_relative_to(root):  # 資料夾裡的符號連結指到外面
                raise SyncError(f"unsafe path: {item.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".sync")
            with archive.open(item) as reader, temporary.open("wb") as writer:
                while chunk := reader.read(1024 * 1024):
                    writer.write(chunk)
            temporary.replace(target)
        return names
