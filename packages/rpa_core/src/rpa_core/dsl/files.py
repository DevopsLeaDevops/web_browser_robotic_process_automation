"""檔案入參（M7c）：值的寫法、場景附件、檔名、類型與大小。

管理 Portal、Runner、Worker 都用這裡的函式解讀與檢查，規則只寫在一個地方。

入參 ``type: file`` 的值有三種寫法（``multiple: true`` 時是清單，每一項是其中一種）：

- **上傳到伺服器的檔案**：``{"file": "<32 個十六進位字元>", "name": "訂單匯入.xlsx", "size": …,
  "sha256": …}``。管理 Portal 與 API 上傳後拿到的參照；只有伺服器知道內容在哪裡。
- **場景附件**：``"files/orders.xlsx"``，或要讓網頁看到別的檔名時
  ``{"attachment": "files/orders.xlsx", "name": "訂單範本.xlsx"}``。檔案跟著場景版本
  （版本資料夾的 ``files/`` 底下），納入場景雜湊。
- **執行那台電腦上的檔案**：``{"path": "D:\\共用\\orders-{{today}}.xlsx"}``，可以有動態值。
  命令列 ``rpa run`` 不限位置；管理 Portal 與 API 交給 Worker 時，只能在 Worker App 設定的
  允許資料夾裡（見 :func:`inside_folders`），不然能執行場景的人就能把那台電腦上的任何檔案
  上傳到外部網站。
- **組合運行的共用工作資料夾裡的檔案**（ADR 0020）：``{"workspace": "downloads/報表.xlsx",
  "name": …, "size": …, "sha256": …}``。這是上游節點 ``type: file`` 出參的值，組合場景把它直接
  接到下游的檔案入參；路徑相對於共用工作資料夾（同一次組合運行都在同一台 Worker 上）。

執行時 Runner 把每個值換成真的檔案，交給瀏覽器；表達式與 input.json 裡只有
``{"name", "size", "sha256"}``，沒有本機路徑。
"""

import hashlib
import mimetypes
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from rpa_core.dsl.fields import catalog

__all__ = [
    "ATTACHMENT_DIR",
    "FILE_ID",
    "MAX_ATTACHMENTS_BYTES",
    "MAX_ATTACHMENT_BYTES",
    "MAX_DROP_BYTES",
    "MAX_FILES_PER_INPUT",
    "MAX_FILE_BYTES",
    "MAX_RUN_BYTES",
    "FileMeta",
    "FileValue",
    "FileValueError",
    "accept_rule_ok",
    "accepts",
    "attachment_names",
    "clean_name",
    "file_meta",
    "file_values",
    "format_size",
    "guess_media_type",
    "inside_folders",
    "is_attachment_path",
    "is_workspace_ref",
    "parse_size",
    "uploaded_ids",
    "workspace_refs",
]

FILE_ID: Final = re.compile(r"[0-9a-f]{32}")
"""上傳到伺服器的檔案的代號。"""
ATTACHMENT_DIR: Final = "files"
"""場景附件放在版本資料夾的這個子資料夾。"""
_ATTACHMENT: Final = re.compile(r"files/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}")
"""附件的路徑：``files/`` 底下一層，檔名只用英數字、底線、點與連字號（git、各系統都不會轉換）。
要讓網頁看到中文檔名時用 ``name``。"""

MAX_FILE_BYTES: Final = 50 * 1024 * 1024
"""單一檔案的預設上限（D4）；伺服器設定可以改。"""
MAX_RUN_BYTES: Final = 200 * 1024 * 1024
"""一次執行全部檔案合計的預設上限（D4）。"""
MAX_ATTACHMENT_BYTES: Final = 20 * 1024 * 1024
"""單一場景附件的上限：附件跟著版本存進領域資料夾、經由 git 同步，太大的檔案會讓倉庫變慢。"""
MAX_ATTACHMENTS_BYTES: Final = 50 * 1024 * 1024
"""一個版本全部附件合計的上限。"""
MAX_DROP_BYTES: Final = 20 * 1024 * 1024
"""拖拽區（``dropzone``）一次交給網頁的檔案合計上限：內容要先送進頁面裡。"""
MAX_FILES_PER_INPUT: Final = 100
"""``multiple`` 的入參最多幾個檔案。"""
_MAX_NAME_BYTES: Final = 200
_SIZE: Final = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)\s*", re.IGNORECASE)
_UNITS: Final = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
_MAX_SIZE_SETTING: Final = 1024**3
"""場景的 maxSize 最多 1 GB（再大多半是寫錯單位）；實際上限由伺服器設定決定。"""
_ACCEPT_EXTENSION: Final = re.compile(r"\.[A-Za-z0-9][A-Za-z0-9._-]{0,19}")
_ACCEPT_MEDIA: Final = re.compile(r"[a-z]+/(?:\*|[A-Za-z0-9][A-Za-z0-9.+_-]{0,99})")
_WINDOWS_RESERVED: Final = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{n}" for n in range(1, 10)),
        *(f"LPT{n}" for n in range(1, 10)),
    }
)
_UNSAFE_CHARS: Final = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")

Source = Literal["upload", "attachment", "path", "workspace"]
_MAX_WORKSPACE_REF: Final = 400


class FileValueError(ValueError):
    """檔案入參的值寫錯了；``message`` 是目前語言的說明。"""

    def __init__(self, code: str, **params: object) -> None:
        self.code = code
        self.params = params
        self.message = catalog(f"files.{code}", **params)
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class FileValue:
    """一個檔案值（還沒換成真的檔案）。"""

    source: Source
    ref: str
    """上傳檔的代號、附件的路徑、那台電腦上的路徑（可能有動態值），或共用工作資料夾裡的
    相對路徑。"""
    name: str | None = None
    """網頁看到的檔名；沒寫時用附件或路徑的檔名。"""
    size: int | None = None
    sha256: str | None = None

    def to_json(self) -> object:
        """寫回 JSON（保留原本的寫法）。"""
        match self.source:
            case "upload":
                data: dict[str, object] = {"file": self.ref}
                if self.name is not None:
                    data["name"] = self.name
                if self.size is not None:
                    data["size"] = self.size
                if self.sha256 is not None:
                    data["sha256"] = self.sha256
                return data
            case "attachment":
                if self.name is None:
                    return self.ref
                return {"attachment": self.ref, "name": self.name}
            case "workspace":
                data = {"workspace": self.ref}
                if self.name is not None:
                    data["name"] = self.name
                if self.size is not None:
                    data["size"] = self.size
                if self.sha256 is not None:
                    data["sha256"] = self.sha256
                return data
            case _:
                data = {"path": self.ref}
                if self.name is not None:
                    data["name"] = self.name
                return data

    @property
    def display_name(self) -> str:
        """網頁看到的檔名（已清理）。"""
        if self.name:
            return clean_name(self.name)
        tail = re.split(r"[\\/]", self.ref)[-1]
        return clean_name(tail or "file")


@dataclass(frozen=True, slots=True)
class FileMeta:
    """執行時一個檔案的說明：表達式、input.json 與報告裡只有這些，沒有本機路徑。"""

    name: str
    size: int
    sha256: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "size": self.size, "sha256": self.sha256}


def is_attachment_path(text: str) -> bool:
    """是不是場景附件的路徑（``files/檔名``）。"""
    return _ATTACHMENT.fullmatch(text) is not None


def is_workspace_ref(text: str) -> bool:
    """是不是共用工作資料夾裡的相對路徑：用 / 分隔，不能是絕對路徑，也不能有 ``..``。"""
    if not text or len(text) > _MAX_WORKSPACE_REF or "\\" in text or text.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", text) or _CONTROL.search(text):
        return False
    return all(part not in ("", ".", "..") for part in text.split("/"))


def _size_and_digest(data: Mapping[str, object]) -> tuple[int | None, str | None]:
    size = data.get("size")
    digest = data.get("sha256")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
        raise FileValueError("shape")
    if digest is not None and (
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise FileValueError("shape")
    return size, digest


def _one(value: object) -> FileValue:
    if isinstance(value, str):
        if not is_attachment_path(value):
            raise FileValueError("attachment_path", value=value)
        return FileValue("attachment", value)
    if not isinstance(value, Mapping):
        raise FileValueError("shape")
    data = cast("Mapping[str, object]", value)
    keys = set(data)
    name = data.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise FileValueError("name")
    if "file" in keys:
        if not keys <= {"file", "name", "size", "sha256"}:
            raise FileValueError("shape")
        ref = data["file"]
        if not isinstance(ref, str) or not FILE_ID.fullmatch(ref):
            raise FileValueError("id", value=str(ref))
        size, digest = _size_and_digest(data)
        return FileValue("upload", ref, name, size, digest)
    if "workspace" in keys:
        if not keys <= {"workspace", "name", "size", "sha256"}:
            raise FileValueError("shape")
        ref = data["workspace"]
        if not isinstance(ref, str) or not is_workspace_ref(ref):
            raise FileValueError("workspace_ref", value=str(ref))
        size, digest = _size_and_digest(data)
        return FileValue("workspace", ref, name, size, digest)
    if "attachment" in keys:
        if not keys <= {"attachment", "name"}:
            raise FileValueError("shape")
        ref = data["attachment"]
        if not isinstance(ref, str) or not is_attachment_path(ref):
            raise FileValueError("attachment_path", value=str(ref))
        return FileValue("attachment", ref, name)
    if "path" in keys:
        if not keys <= {"path", "name"}:
            raise FileValueError("shape")
        ref = data["path"]
        if not isinstance(ref, str) or not ref.strip():
            raise FileValueError("path")
        return FileValue("path", ref, name)
    raise FileValueError("shape")


def file_values(value: object, *, multiple: bool) -> list[FileValue]:
    """解讀一個 file 入參的值；寫法不對時拋出 :class:`FileValueError`。

    ``multiple`` 的入參要寫清單（空清單代表沒有檔案）；單檔的入參不能寫清單。
    """
    if isinstance(value, list):
        if not multiple:
            raise FileValueError("not_multiple")
        items = cast("list[object]", value)
        if len(items) > MAX_FILES_PER_INPUT:
            raise FileValueError("too_many", count=len(items), limit=MAX_FILES_PER_INPUT)
        return [_one(item) for item in items]
    if multiple:
        raise FileValueError("multiple_list")
    return [_one(value)]


def uploaded_ids(values: Iterable[object]) -> list[str]:
    """一組入參值裡用到的上傳檔代號（依出現順序、不重複；看不懂的值略過）。"""
    found: dict[str, None] = {}
    pending = list(values)
    while pending:
        item = pending.pop(0)
        if isinstance(item, list):
            pending[0:0] = cast("list[object]", item)
        elif isinstance(item, Mapping):
            ref = cast("Mapping[str, object]", item).get("file")
            if isinstance(ref, str) and FILE_ID.fullmatch(ref):
                found[ref] = None
    return list(found)


def workspace_refs(values: Iterable[object]) -> list[str]:
    """一組入參值裡用到的共用工作資料夾檔案（上游節點的 file 出參；看不懂的值略過）。"""
    found: dict[str, None] = {}
    pending = list(values)
    while pending:
        item = pending.pop(0)
        if isinstance(item, list):
            pending[0:0] = cast("list[object]", item)
        elif isinstance(item, Mapping):
            ref = cast("Mapping[str, object]", item).get("workspace")
            if isinstance(ref, str) and is_workspace_ref(ref):
                found[ref] = None
    return list(found)


def attachment_names(values: Iterable[object]) -> list[str]:
    """一組入參值裡用到的場景附件（依出現順序、不重複；看不懂的值略過）。"""
    found: dict[str, None] = {}
    pending = list(values)
    while pending:
        item = pending.pop(0)
        if isinstance(item, list):
            pending[0:0] = cast("list[object]", item)
        elif isinstance(item, str) and is_attachment_path(item):
            found[item] = None
        elif isinstance(item, Mapping):
            ref = cast("Mapping[str, object]", item).get("attachment")
            if isinstance(ref, str) and is_attachment_path(ref):
                found[ref] = None
    return list(found)


def clean_name(name: str) -> str:
    """網頁看到的檔名：去掉路徑、控制字元與 Windows 不能用的字元，避開保留名稱，最長 200 位元組。

    Unicode 先轉成 NFC（macOS 與 Windows 的組字方式不同，同一個檔名才會一致）。
    """
    text = unicodedata.normalize("NFC", name)
    text = re.split(r"[\\/]", text)[-1]
    text = _UNSAFE_CHARS.sub("_", text).strip().rstrip(". ")
    if not text or text in (".", ".."):
        text = "file"
    stem, dot, suffix = text.partition(".")
    if stem.upper() in _WINDOWS_RESERVED:
        text = f"_{stem}{dot}{suffix}"
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_NAME_BYTES:
        suffix_part = PurePosixPath(text).suffix
        keep = _MAX_NAME_BYTES - len(suffix_part.encode("utf-8"))
        head = text[: len(text) - len(suffix_part)].encode("utf-8")[:keep]
        text = head.decode("utf-8", errors="ignore").rstrip(". ") + suffix_part
    return text


def parse_size(text: str) -> int:
    """``20MB`` 這類寫法 → 位元組數；單位 B、KB、MB、GB（1024 進位，不分大小寫）。"""
    match = _SIZE.fullmatch(text)
    if match is None:
        raise FileValueError("size_format", value=text)
    number = float(match.group(1)) * _UNITS[match.group(2).upper()]
    if number < 1 or number > _MAX_SIZE_SETTING:
        raise FileValueError("size_range", value=text)
    return int(number)


def format_size(size: int) -> str:
    """給人看的大小，例如 20 MB、1.5 KB。"""
    for unit in ("GB", "MB", "KB"):
        base = _UNITS[unit]
        if size >= base:
            value = size / base
            return f"{value:.1f} {unit}".replace(".0 ", " ")
    return f"{size} B"


def accept_rule_ok(rule: str) -> bool:
    """``accept`` 的一項寫法是否正確：``.副檔名``，或 MIME（``image/png``、``image/*``）。"""
    return bool(_ACCEPT_EXTENSION.fullmatch(rule) or _ACCEPT_MEDIA.fullmatch(rule))


def guess_media_type(name: str) -> str:
    """依副檔名猜檔案類型；猜不到時是 application/octet-stream。"""
    media, _ = mimetypes.guess_type(name, strict=False)
    return media or "application/octet-stream"


def accepts(rules: Sequence[str] | None, name: str) -> bool:
    """檔名是否符合 ``accept``（沒寫就都符合）：副檔名不分大小寫，MIME 依副檔名推測。"""
    if not rules:
        return True
    lowered = name.lower()
    media = guess_media_type(name)
    for rule in rules:
        if rule.startswith("."):
            if lowered.endswith(rule.lower()):
                return True
        elif rule.endswith("/*"):
            if media.startswith(rule[:-1]):
                return True
        elif media == rule:
            return True
    return False


def file_meta(path: Path, name: str) -> FileMeta:
    """讀一次檔案：大小與 sha256。"""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return FileMeta(name, size, digest.hexdigest())


def inside_folders(path: Path, folders: Sequence[Path]) -> bool:
    """``path``（解開符號連結之後）是否在任何一個允許的資料夾裡。"""
    try:
        real = path.resolve(strict=True)
    except OSError:
        return False
    for folder in folders:
        try:
            root = folder.resolve(strict=True)
        except OSError:
            continue
        if real.is_relative_to(root):
            return True
    return False
