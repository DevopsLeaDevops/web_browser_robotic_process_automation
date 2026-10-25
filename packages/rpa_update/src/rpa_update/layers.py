"""桌面 App 的程式碼層（ADR 0018）：更新檔裝在使用者的資料夾，啟動時排在內建的程式前面。

RPA Worker、RPA 錄製端的資料夾（和 App 自己用的相同，``RPA_WORKER_HOME``、
``RPA_RECORDER_HOME`` 可以改）底下::

    app/
        active.json          現在用哪一層（:class:`Active`）
        boot.log             啟動器的紀錄：只有改用內建的程式、退回上一層、重新啟動再試時才寫
        <版本-提交>/
            manifest.json    更新檔的清單與簽章，原樣保留：每次啟動都重新驗證
            manifest.sig
            app/…            程式碼層（工作區的套件與 .pyc）

啟動（:func:`activate`）：

1. 子程序：父程序用環境變數 ``RPA_APP_LAYER`` 指定同一層（或 ``builtin``），不重新選擇，
   也不重新核對每個檔案（父程序剛核對過）；
2. 使用者重新安裝過完整的安裝包（runtime.json 的 ``release`` 和 ``installed_with`` 不同）
   → 改回內建的程式；
3. 新裝的一層還沒確認（``pending``）→ 記下啟動次數，超過 :data:`MAX_ATTEMPTS` 次還沒確認就退回
   上一層（沒有上一層就用內建的程式）。確認（:func:`confirm`）由 :mod:`rpa_update.boot` 做：
   App 正常結束，或是執行超過 :data:`CONFIRM_AFTER` 秒；
4. 驗證簽章、環境代號、每個檔案 → 放在 import 路徑的最前面。任何一步失敗都不讓 App 起不來：
   改用上一層或內建的程式，寫進 boot.log。

這個模組跟著執行環境走（不在程式碼層），只能用標準函式庫與 rpa_update 自己。
"""

import contextlib
import importlib
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from rpa_update.errors import UpdateError
from rpa_update.manifest import (
    MANIFEST,
    SIGNATURE,
    Manifest,
    UpdateFile,
    check_path,
    verify_signature,
    verify_tree,
)
from rpa_update.runtime import Runtime, load_runtime

__all__ = [
    "ACTIVE_FILE",
    "BUILTIN",
    "CODE_DIR",
    "CONFIRM_AFTER",
    "HOME_ENVS",
    "KEEP",
    "LAYERS_DIR",
    "LAYER_ENV",
    "LOG_FILE",
    "MAX_ATTEMPTS",
    "Active",
    "Installed",
    "Layer",
    "activate",
    "app_home",
    "confirm",
    "current_layer",
    "install_layer",
    "layers_dir",
    "load_layer",
    "log",
    "prune",
    "read_active",
    "write_active",
]

LAYER_ENV: Final = "RPA_APP_LAYER"
"""父程序用的程式碼層（資料夾名稱，或 :data:`BUILTIN`）：子程序照用，不重新選擇。"""
BUILTIN: Final = "builtin"
LAYERS_DIR: Final = "app"
ACTIVE_FILE: Final = "active.json"
LOG_FILE: Final = "boot.log"
CODE_DIR: Final = "app"
"""一層裡放程式碼的資料夾；也是更新檔裡程式碼層的前綴（``app/``）。"""
KEEP: Final = 3
MAX_ATTEMPTS: Final = 2
"""新裝的一層最多啟動幾次還沒確認，下一次就退回。"""
CONFIRM_AFTER: Final = 20.0
HOME_ENVS: Final = {"worker": "RPA_WORKER_HOME", "recorder": "RPA_RECORDER_HOME"}
"""兩個桌面 App 改資料夾位置的環境變數（rpa_desktop.worker_app、rpa_desktop.recorder_gui）。"""
_LOG_LIMIT: Final = 256 * 1024
_STAGING: Final = ".staging-"


def app_home(kind: str, environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """桌面 App 的資料夾：和 rpa_desktop 的 ``data_dir``、``recorder_dir`` 相同（有測試核對）。

    啟動器不能匯入 rpa_desktop（那是程式碼層，要在選好之後才載入），所以在這裡另外寫一份。
    """
    override = environ.get(HOME_ENVS[kind])
    if override:
        return Path(override).expanduser()
    if kind == "worker":
        home = Path(environ.get("USERPROFILE") or environ.get("HOME") or Path.home())
    else:
        home = Path(environ.get("HOME") or environ.get("USERPROFILE") or Path.home())
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "rpa" / kind
    if platform == "darwin":
        return home / "Library" / "Application Support" / "rpa" / kind
    base = environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(base) / "rpa" / kind


def layers_dir(runtime: Runtime, environ: Mapping[str, str] | None = None) -> Path:
    """這個 App 放程式碼層的資料夾。"""
    kind = runtime.target.split("-", 1)[0]
    if kind not in HOME_ENVS:
        raise UpdateError("not_desktop", target=runtime.target)
    return app_home(kind, os.environ if environ is None else environ) / LAYERS_DIR


# ---------------------------------------------------------------- 現在用哪一層


@dataclass(frozen=True, slots=True)
class Active:
    """``active.json``：``release`` 是 None 時用內建的程式。"""

    release: str | None = None
    previous: str | None = None
    """裝這一層之前用的（None 是內建的程式）：退回時用。"""
    pending: bool = False
    """新裝的，還沒確認能正常啟動。"""
    attempts: int = 0
    installed_with: str = ""
    """裝這一層時內建的程式版本（runtime.json 的 ``release``）：不同代表重新安裝過完整的安裝包。"""
    failed: str | None = None
    """最近一次退回的那一層：同一個版本不要再自動裝一次。"""

    def to_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: object) -> "Active":
        if not isinstance(data, dict):
            return cls()
        values = cast("dict[str, object]", data)

        def text(key: str) -> str | None:
            value = values.get(key)
            return value if isinstance(value, str) and value else None

        attempts = values.get("attempts", 0)
        return cls(
            release=text("release"),
            previous=text("previous"),
            pending=values.get("pending") is True,
            attempts=attempts if isinstance(attempts, int) and attempts >= 0 else 0,
            installed_with=text("installed_with") or "",
            failed=text("failed"),
        )


def read_active(root: Path) -> Active:
    """讀 active.json；沒有或壞掉時當作用內建的程式。"""
    try:
        return Active.from_json(json.loads((root / ACTIVE_FILE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Active()


def write_active(root: Path, active: Active) -> None:
    """寫 active.json（先寫暫存檔再換掉，不會留下寫到一半的檔案）。"""
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f"{ACTIVE_FILE}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(active.to_json(), indent=1) + "\n", encoding="utf-8")
    temporary.replace(root / ACTIVE_FILE)


def log(root: Path, message: str) -> None:
    """寫一行到 boot.log；寫不進去也不影響啟動。檔案太大時從頭開始。"""
    with contextlib.suppress(OSError):
        root.mkdir(parents=True, exist_ok=True)
        path = root / LOG_FILE
        mode = "w" if path.is_file() and path.stat().st_size > _LOG_LIMIT else "a"
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with path.open(mode, encoding="utf-8") as stream:
            stream.write(f"{stamp} [{os.getpid()}] {message}\n")


def _describe(error: Exception) -> str:
    if isinstance(error, UpdateError):
        details = " ".join(f"{key}={value}" for key, value in error.params.items())
        return f"{error.code} {details}".strip()
    return f"{type(error).__name__}: {error}"


# ---------------------------------------------------------------- 一層


@dataclass(frozen=True, slots=True)
class Layer:
    """一層已經驗證過的程式碼。"""

    path: Path
    manifest: Manifest

    @property
    def release(self) -> str:
        return self.path.name

    @property
    def code(self) -> Path:
        return self.path / CODE_DIR


_current: Layer | None = None


def _check_runtime(manifest: Manifest, runtime: Runtime) -> None:
    needed = manifest.runtime_for(runtime.target)
    if needed is None:
        raise UpdateError("no_build_for_target", target=runtime.target, version=manifest.version)
    if needed != runtime.id:
        raise UpdateError(
            "runtime_changed", version=manifest.version, needed=needed, current=runtime.id
        )


def load_layer(root: Path, release: str, runtime: Runtime, *, full: bool = True) -> Layer:
    """驗證 ``root/release`` 這一層：簽章、環境代號；``full`` 時再核對每個檔案。"""
    if "/" in release or "\\" in release:
        raise UpdateError("unsafe_path", path=release)
    check_path(release)
    path = root / release
    try:
        data = (path / MANIFEST).read_bytes()
        signature = (path / SIGNATURE).read_bytes()
    except OSError:
        raise UpdateError("layer_missing", release=release) from None
    verify_signature(data, signature, runtime.keys)
    manifest = Manifest.from_bytes(data)
    if manifest.release != release:
        raise UpdateError("layer_mismatch", release=release, manifest=manifest.release)
    _check_runtime(manifest, runtime)
    if full:
        verify_tree(path / CODE_DIR, manifest.under(f"{CODE_DIR}/"))
    return Layer(path, manifest)


# ---------------------------------------------------------------- 安裝


@dataclass(frozen=True, slots=True)
class Installed:
    manifest: Manifest
    previous: str | None
    """裝之前用的那一層（None 是內建的程式）。"""
    already: bool = False
    """已經在用這個版本，沒有改變任何東西。"""


def install_layer(
    root: Path,
    update: Path,
    runtime: Runtime,
    *,
    keep: int = KEEP,
    protect: Iterable[str] = (),
) -> Installed:
    """把更新檔的程式碼層裝成新的一層，下次啟動時使用（還沒確認，見 :func:`activate`）。

    ``protect`` 是不能刪的層（例如這個程序正在用的那一層）。
    """
    with UpdateFile(update, runtime.keys) as source:
        manifest = source.manifest
        _check_runtime(manifest, runtime)
        release = check_path(manifest.release)
        active = read_active(root)
        if active.installed_with != runtime.release:
            active = Active(installed_with=runtime.release)
        if manifest.release == runtime.release:
            # 更新檔就是內建的程式：改回內建的，不用另外裝一層
            already = active.release is None
            write_active(root, Active(installed_with=runtime.release))
            return Installed(manifest, active.release, already=already)
        if active.release == release:
            with contextlib.suppress(UpdateError):
                load_layer(root, release, runtime)
                return Installed(manifest, active.previous, already=True)
        source.check()
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f"{_STAGING}{uuid.uuid4().hex}"
        try:
            entries = source.extract(f"{CODE_DIR}/", staging / CODE_DIR)
            (staging / MANIFEST).write_bytes(source.manifest_bytes)
            (staging / SIGNATURE).write_bytes(source.signature_bytes)
            verify_tree(staging / CODE_DIR, entries)
            target = root / release
            if target.exists():
                # 之前裝過（可能不完整）：換成剛解開的這份
                shutil.rmtree(target)
            staging.replace(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    previous = active.release
    write_active(
        root,
        Active(
            release=release,
            previous=previous,
            pending=True,
            installed_with=runtime.release,
            failed=active.failed if active.failed != release else None,
        ),
    )
    prune(root, keep, protect={release, *([previous] if previous else []), *protect})
    return Installed(manifest, previous)


def prune(root: Path, keep: int = KEEP, protect: Iterable[str] = ()) -> list[str]:
    """只留最新的 ``keep`` 層（``protect`` 一定留），清掉沒裝完的暫存資料夾；回傳刪掉的。"""
    protected = {name for name in protect if name}
    if not root.is_dir():
        return []
    layers: list[Path] = []
    for path in root.iterdir():
        if path.name.startswith(_STAGING) and path.is_dir():
            # 超過一小時還在的暫存資料夾是中斷的安裝
            if time.time() - path.stat().st_mtime > 3600:
                shutil.rmtree(path, ignore_errors=True)
        elif path.is_dir() and (path / MANIFEST).is_file():
            layers.append(path)
    layers.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for path in layers[keep:]:
        if path.name not in protected:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    return removed


# ---------------------------------------------------------------- 啟動


def current_layer() -> Layer | None:
    """這個程序用的程式碼層；用內建的程式（或開發環境）時是 None。"""
    return _current


def _use(
    layer: Layer | None, environ: MutableMapping[str, str], path: MutableSequence[str]
) -> Layer | None:
    global _current
    _current = layer
    if layer is None:
        environ[LAYER_ENV] = BUILTIN
        return None
    path.insert(0, str(layer.code))
    environ[LAYER_ENV] = layer.release
    # .pyc 都在更新檔裡；寫進去會多出檔案，下次啟動核對時就不符
    sys.dont_write_bytecode = True
    importlib.invalidate_caches()
    return layer


def _fallback(
    root: Path, active: Active, runtime: Runtime, failed: str, reason: str
) -> tuple[Active, Layer | None]:
    """``failed`` 這一層不能用：改用上一層（也不能用就用內建的程式），記下來。"""
    previous = active.previous if active.previous != failed else None
    layer: Layer | None = None
    if previous is not None:
        try:
            layer = load_layer(root, previous, runtime)
        except (UpdateError, OSError) as error:
            log(root, f"上一層 {previous} 也不能用：{_describe(error)}")
    chosen = layer.release if layer is not None else None
    log(root, f"不用 {failed}（{reason}），改用 {chosen or BUILTIN}")
    updated = Active(release=chosen, installed_with=runtime.release, failed=failed)
    return updated, layer


def activate(
    runtime: Runtime | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
    path: MutableSequence[str] | None = None,
) -> tuple[Layer | None, bool]:
    """選出這次啟動用的程式碼層並放在 import 路徑最前面；回傳 (那一層, 是否還沒確認)。

    開發環境（沒有 runtime.json）、伺服器的分發包、用內建的程式時，那一層是 None。
    """
    env = os.environ if environ is None else environ
    paths = sys.path if path is None else path
    try:
        info = load_runtime() if runtime is None else runtime
    except UpdateError:
        info = None
    if info is None or info.target.split("-", 1)[0] not in HOME_ENVS:
        return None, False
    root = layers_dir(info, env)
    pinned = env.get(LAYER_ENV)
    if pinned == BUILTIN:
        return _use(None, env, paths), False
    if pinned:
        try:
            return _use(load_layer(root, pinned, info, full=False), env, paths), False
        except (UpdateError, OSError) as error:
            log(root, f"父程序指定的 {pinned} 不能用：{_describe(error)}")
    active = read_active(root)
    if active.release is None:
        return _use(None, env, paths), False
    if active.installed_with != info.release:
        log(root, f"重新安裝過完整的安裝包（{info.release}），改用內建的程式")
        _save(root, Active(installed_with=info.release))
        return _use(None, env, paths), False
    if active.pending:
        active = replace(active, attempts=active.attempts + 1)
        if active.attempts > MAX_ATTEMPTS:
            active, layer = _fallback(root, active, info, active.release or "", "啟動後沒有確認")
            _save(root, active)
            return _use(layer, env, paths), False
        _save(root, active)
    release = active.release or ""
    try:
        layer = load_layer(root, release, info)
    except (UpdateError, OSError) as error:
        active, layer = _fallback(root, active, info, release, _describe(error))
        _save(root, active)
        return _use(layer, env, paths), False
    return _use(layer, env, paths), active.pending


def _save(root: Path, active: Active) -> None:
    try:
        write_active(root, active)
    except OSError as error:
        log(root, f"寫不進 {ACTIVE_FILE}：{error}")


def confirm(root: Path, release: str) -> bool:
    """``release`` 能正常啟動：不再計算啟動次數。回傳有沒有改變。"""
    active = read_active(root)
    if not active.pending or active.release != release:
        return False
    _save(root, replace(active, pending=False, attempts=0))
    return True
