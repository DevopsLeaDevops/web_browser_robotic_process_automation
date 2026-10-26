"""更新檔（ADR 0018）：清單、簽章、讀取與解開、核對解開後的檔案。

``RPA-Update-<版本>.zip`` 的內容::

    manifest.json        清單（:class:`Manifest`），簽章簽的就是這個檔案的原始位元組
    manifest.sig         簽章（JSON：演算法、金鑰代號、base64 的簽章）
    app/…                程式碼層：工作區的套件（不含 rpa_update）與它們的 dist-info、.pyc
    server/…             伺服器另外需要的檔案：bin/rpa、install.sh、範例場景

讀取時先驗證簽章，再核對壓縮檔裡的檔案和清單完全一樣（不多、不少、大小相同），解開時逐一
核對 SHA-256。路徑只接受相對、正斜線、不含 ``..`` 的寫法，也不接受符號連結。
"""

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Final, Self, cast

from rpa_update import ed25519
from rpa_update.errors import UpdateError

__all__ = [
    "FORMAT",
    "MANIFEST",
    "SIGNATURE",
    "FileEntry",
    "Manifest",
    "UpdateFile",
    "check_path",
    "hash_file",
    "scan_tree",
    "sign_manifest",
    "verify_signature",
    "verify_tree",
    "write_update",
]

FORMAT: Final = 1
MANIFEST: Final = "manifest.json"
SIGNATURE: Final = "manifest.sig"
_ALGORITHM: Final = "ed25519"
_MANIFEST_LIMIT: Final = 16 * 1024 * 1024
_SIGNATURE_LIMIT: Final = 4096
_CHUNK: Final = 1024 * 1024
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT: Final = re.compile(r"^[A-Za-z0-9._+\-@ ]+$")
_RESERVED: Final = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10))})


def check_path(path: str) -> str:
    """確認清單裡的路徑安全：相對、正斜線分隔、每段只有常見字元，不含 ``.``、``..``。"""
    parts = path.split("/")
    if not path or path.startswith("/") or any(not part for part in parts):
        raise UpdateError("unsafe_path", path=path)
    for part in parts:
        stem = part.split(".", 1)[0].lower()
        if (
            part in (".", "..")
            or not _SEGMENT.fullmatch(part)
            or part.endswith((" ", "."))
            or stem in _RESERVED
            or (stem.startswith("lpt") and stem[3:].isdigit())
        ):
            raise UpdateError("unsafe_path", path=path)
    return path


@dataclass(frozen=True, slots=True)
class FileEntry:
    sha256: str
    size: int

    def to_json(self) -> dict[str, object]:
        return {"sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class Manifest:
    """更新檔的清單。``files`` 的鍵是壓縮檔裡的路徑（不含清單與簽章）。"""

    version: str
    commit: str
    built_at: str
    fingerprint: str
    protocol: int
    features: tuple[str, ...]
    runtimes: Mapping[str, str]
    """每個目標（``server-linux-x64`` 之類）需要的環境代號；沒列出的目標只能裝完整的安裝包。"""
    files: Mapping[str, FileEntry]
    format: int = FORMAT
    extra: Mapping[str, object] = field(default_factory=dict[str, object])
    """新版本加的欄位：舊的程式讀到時保留，不認得也不拒絕。"""

    @property
    def release(self) -> str:
        """伺服器的版本資料夾名稱：``0.6.0-1a2b3c4``（沒有提交時只有版本）。"""
        return f"{self.version}-{self.commit}" if self.commit else self.version

    def runtime_for(self, target: str) -> str | None:
        return self.runtimes.get(target)

    def under(self, prefix: str) -> dict[str, FileEntry]:
        """``prefix``（例如 ``app/``）底下的檔案，鍵去掉 ``prefix``。"""
        return {
            path[len(prefix) :]: entry
            for path, entry in self.files.items()
            if path.startswith(prefix)
        }

    def to_json(self) -> dict[str, object]:
        return {
            **self.extra,
            "format": self.format,
            "version": self.version,
            "commit": self.commit,
            "built_at": self.built_at,
            "fingerprint": self.fingerprint,
            "protocol": self.protocol,
            "features": list(self.features),
            "runtimes": dict(sorted(self.runtimes.items())),
            "files": {path: entry.to_json() for path, entry in sorted(self.files.items())},
        }

    def to_bytes(self) -> bytes:
        return (json.dumps(self.to_json(), ensure_ascii=True, indent=1) + "\n").encode("ascii")

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise UpdateError("manifest_invalid") from None
        if not isinstance(raw, dict):
            raise UpdateError("manifest_invalid")
        values = cast("dict[str, object]", raw)
        if values.get("format") != FORMAT:
            raise UpdateError("manifest_format", format=values.get("format"))
        known = {
            "format",
            "version",
            "commit",
            "built_at",
            "fingerprint",
            "protocol",
            "features",
            "runtimes",
            "files",
        }
        return cls(
            version=_string(values, "version"),
            commit=_string(values, "commit"),
            built_at=_string(values, "built_at"),
            fingerprint=_string(values, "fingerprint"),
            protocol=_integer(values, "protocol"),
            features=tuple(_strings(values.get("features"))),
            runtimes=_runtimes(values.get("runtimes")),
            files=_files(values.get("files")),
            extra={key: value for key, value in values.items() if key not in known},
        )


def _string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str):
        raise UpdateError("manifest_invalid", field=key)
    return value


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise UpdateError("manifest_invalid", field=key)
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in cast("list[object]", value)
    ):
        raise UpdateError("manifest_invalid", field="features")
    return cast("list[str]", value)


def _runtimes(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise UpdateError("manifest_invalid", field="runtimes")
    items = cast("dict[object, object]", value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in items.items()):
        raise UpdateError("manifest_invalid", field="runtimes")
    return cast("dict[str, str]", items)


def _files(value: object) -> dict[str, FileEntry]:
    if not isinstance(value, dict):
        raise UpdateError("manifest_invalid", field="files")
    entries: dict[str, FileEntry] = {}
    folded: set[str] = set()
    for path, item in cast("dict[object, object]", value).items():
        if not isinstance(path, str) or not isinstance(item, dict):
            raise UpdateError("manifest_invalid", field="files")
        check_path(path)
        if path in (MANIFEST, SIGNATURE) or path.casefold() in folded:
            raise UpdateError("unsafe_path", path=path)
        folded.add(path.casefold())
        info = cast("dict[str, object]", item)
        sha256, size = info.get("sha256"), info.get("size")
        if (
            not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise UpdateError("manifest_invalid", field=path)
        entries[path] = FileEntry(sha256, size)
    return entries


# ---------------------------------------------------------------- 簽章


def sign_manifest(manifest: bytes, seed: bytes) -> bytes:
    """``manifest.sig`` 的內容（只在 CI 產生更新檔時用）。"""
    public = ed25519.public_key(seed)
    signature = base64.b64encode(ed25519.sign(seed, manifest)).decode("ascii")
    body = {"algorithm": _ALGORITHM, "key": ed25519.key_id(public), "signature": signature}
    return (json.dumps(body, indent=1) + "\n").encode("ascii")


def verify_signature(manifest: bytes, signature: bytes, keys: Iterable[bytes]) -> str:
    """確認 ``manifest`` 是信任的金鑰簽的；回傳金鑰代號。"""
    try:
        raw = json.loads(signature.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise UpdateError("signature_invalid") from None
    if not isinstance(raw, dict):
        raise UpdateError("signature_invalid")
    body = cast("dict[str, object]", raw)
    key, value = body.get("key"), body.get("signature")
    if (
        body.get("algorithm") != _ALGORITHM
        or not isinstance(key, str)
        or not isinstance(value, str)
    ):
        raise UpdateError("signature_invalid")
    trusted = {ed25519.key_id(public): public for public in keys}
    if not trusted:
        raise UpdateError("no_trusted_keys")
    public = trusted.get(key)
    if public is None:
        raise UpdateError("signature_untrusted", key=key)
    try:
        raw_signature = base64.b64decode(value, validate=True)
    except binascii.Error:
        raise UpdateError("signature_invalid") from None
    if not ed25519.verify(public, manifest, raw_signature):
        raise UpdateError("signature_mismatch", key=key)
    return key


# ---------------------------------------------------------------- 檔案的雜湊


def _digest(stream: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def hash_file(path: Path) -> FileEntry:
    with path.open("rb") as stream:
        sha256, size = _digest(stream)
    return FileEntry(sha256, size)


def _walk(root: Path) -> Iterator[tuple[str, Path]]:
    """``root`` 底下的每個檔案（相對路徑用 /）；遇到符號連結或特殊檔案就拒絕。"""
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in [*names, *filenames]:
            path = base / name
            mode = path.lstat().st_mode
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise UpdateError("unexpected_file", path=relative)
            if stat.S_ISREG(mode):
                yield relative, path


def scan_tree(root: Path, prefix: str = "") -> dict[str, FileEntry]:
    """產生清單用：``root`` 底下每個檔案的雜湊，鍵加上 ``prefix``。"""
    return {
        check_path(prefix + relative): hash_file(path) for relative, path in sorted(_walk(root))
    }


def verify_tree(root: Path, entries: Mapping[str, FileEntry]) -> None:
    """``root`` 底下的檔案和 ``entries`` 完全一樣：不多、不少、雜湊相同。

    多出來的檔案也拒絕：Python 優先載入 .so、.pyd 等擴充模組，被放進去的檔案會蓋過我們的程式。
    """
    seen: set[str] = set()
    for relative, path in _walk(root):
        expected = entries.get(relative)
        if expected is None:
            raise UpdateError("unexpected_file", path=relative)
        if hash_file(path) != expected:
            raise UpdateError("file_mismatch", path=relative)
        seen.add(relative)
    missing = sorted(set(entries) - seen)
    if missing:
        raise UpdateError("file_missing", path=missing[0])


# ---------------------------------------------------------------- 更新檔（zip）


class UpdateFile:
    """一個已經驗證過簽章與內容的更新檔。用 ``with`` 開啟，離開時關閉壓縮檔。"""

    def __init__(self, path: Path, keys: Iterable[bytes]) -> None:
        self.path = path
        try:
            self._zip = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as error:
            raise UpdateError("not_an_update", error=error) from None
        try:
            self.manifest_bytes = self._small(MANIFEST, _MANIFEST_LIMIT)
            self.signature_bytes = self._small(SIGNATURE, _SIGNATURE_LIMIT)
            self.key = verify_signature(self.manifest_bytes, self.signature_bytes, keys)
            self.manifest = Manifest.from_bytes(self.manifest_bytes)
            self._check_members()
        except BaseException:
            self._zip.close()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    def _small(self, name: str, limit: int) -> bytes:
        try:
            info = self._zip.getinfo(name)
        except KeyError:
            raise UpdateError("not_an_update", error=f"{name} missing") from None
        if info.file_size > limit:
            raise UpdateError("not_an_update", error=f"{name} too large")
        with self._zip.open(info) as stream:
            return stream.read(limit + 1)[:limit]

    def _check_members(self) -> None:
        expected = self.manifest.files
        seen: set[str] = set()
        for info in self._zip.infolist():
            name = info.filename
            if info.is_dir():
                check_path(name.rstrip("/"))
                continue
            if name in (MANIFEST, SIGNATURE):
                continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UpdateError("unsafe_path", path=name)
            entry = expected.get(name)
            if entry is None or name in seen:
                raise UpdateError("unexpected_file", path=name)
            if info.file_size != entry.size:
                raise UpdateError("file_mismatch", path=name)
            seen.add(name)
        missing = sorted(set(expected) - seen)
        if missing:
            raise UpdateError("file_missing", path=missing[0])

    def check(self) -> None:
        """讀過每個檔案、核對 SHA-256（解開之前先確認整個檔案完整）。"""
        for name, entry in self.manifest.files.items():
            with self._zip.open(name) as stream:
                if _digest(stream) != (entry.sha256, entry.size):
                    raise UpdateError("file_mismatch", path=name)

    def extract(self, prefix: str, destination: Path) -> dict[str, FileEntry]:
        """把 ``prefix`` 底下的檔案解到 ``destination``（去掉 ``prefix``），邊寫邊核對雜湊。

        回傳解開的檔案（鍵去掉 ``prefix``），給之後的 :func:`verify_tree` 用。
        """
        entries = self.manifest.under(prefix)
        for relative, entry in sorted(entries.items()):
            target = destination.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with self._zip.open(prefix + relative) as source, target.open("xb") as out:
                while chunk := source.read(_CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            if (digest.hexdigest(), size) != (entry.sha256, entry.size):
                raise UpdateError("file_mismatch", path=prefix + relative)
            if (self._zip.getinfo(prefix + relative).external_attr >> 16) & stat.S_IXUSR:
                target.chmod(0o755)
        return entries


def write_update(path: Path, manifest: Manifest, sources: Mapping[str, Path], seed: bytes) -> bytes:
    """寫出更新檔：``sources`` 是 {壓縮檔裡的路徑: 本機檔案}，要和清單的檔案一致。回傳清單。"""
    if set(sources) != set(manifest.files):
        raise UpdateError("file_missing", path=sorted(set(sources) ^ set(manifest.files))[0])
    data = manifest.to_bytes()
    signature = sign_manifest(data, seed)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(MANIFEST, data)
        archive.writestr(SIGNATURE, signature)
        for name in sorted(sources):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = sources[name].stat().st_mode
            info.external_attr = ((0o755 if mode & stat.S_IXUSR else 0o644) | stat.S_IFREG) << 16
            archive.writestr(info, sources[name].read_bytes(), compresslevel=9)
    return data
