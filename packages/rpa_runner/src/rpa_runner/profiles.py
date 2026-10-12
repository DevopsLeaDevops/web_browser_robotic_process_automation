"""Firefox 的預熱設定檔：避免每次啟動都要初始化全新設定檔而卡住。

Playwright 每次啟動 Firefox 都用全新的暫存設定檔；Firefox 初始化設定檔時整個瀏覽器停止回應，
大約在啟動後 3 秒。Windows 上實測：閒置時 0.4～2.8 秒，機器忙時 3～5 秒以上，偶爾超過步驟的
逾時（10 秒），結果是隨機某個步驟失敗。改用預先初始化過的設定檔的複本啟動，降到 0～0.3 秒。

做法：

- 每台電腦、每個 Firefox 版本保留一份**範本**：第一次用到時建立，只開過 about:blank，
  沒有任何瀏覽紀錄。先在暫存資料夾建立，完成後改名成正式名稱，多個執行同時建立也不會互相干擾。
- 每次執行**複製一份**來啟動，結束後刪除；每次執行仍然是乾淨的，不會帶到別次執行的 cookie 或紀錄。
  被強制終止而沒刪掉的複本，超過一天後由之後的執行清掉。
- 任何一步做不到（例如沒有寫入權限、剩下的期限不夠建立範本）就照舊用全新設定檔，只是慢一點。

範本放在快取資料夾 ``RPA_CACHE_DIR``；沒設定時依系統：Windows ``%LOCALAPPDATA%\\rpa\\cache``、
macOS ``~/Library/Caches/rpa``、其他 ``$XDG_CACHE_HOME/rpa``（預設 ``~/.cache/rpa``）。
"""

import hashlib
import os
import shutil
import sys
import time
import uuid
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from playwright.sync_api import Playwright

from rpa_runner.i18n import t

__all__ = [
    "MIN_BUDGET_SECONDS",
    "READY",
    "cache_dir",
    "copy_profile",
    "ensure_template",
    "firefox_profile",
    "prune",
    "template_key",
    "warm_profile",
]

READY: Final = ".rpa-ready"
"""範本建立完成的標記；沒有這個檔案的範本視為不完整。"""
WARMUP_SECONDS: Final = 6.0
"""建立範本時讓 Firefox 開著的秒數：要涵蓋啟動後約 3 秒的初始化。"""
MIN_BUDGET_SECONDS: Final = 25.0
"""還沒有範本時，剩下的期限至少要這麼多秒才建立（建立約需 7～10 秒）；不夠就先用全新設定檔。"""
STALE_SECONDS: Final = 24 * 3600
_LOCKS: Final = ("parent.lock", "lock", ".parentlock")
_FOLDER: Final = "firefox-profile"
_RUNS: Final = "runs"


def cache_dir(
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """快取資料夾：``RPA_CACHE_DIR``，沒設定時依系統的慣例位置。"""
    env = os.environ if environ is None else environ
    if env.get("RPA_CACHE_DIR"):
        return Path(env["RPA_CACHE_DIR"])
    system = sys.platform if platform is None else platform
    base = Path.home() if home is None else home
    if system == "win32":
        local = env.get("LOCALAPPDATA")
        return (Path(local) if local else base / "AppData" / "Local") / "rpa" / "cache"
    if system == "darwin":
        return base / "Library" / "Caches" / "rpa"
    xdg = env.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else base / ".cache") / "rpa"


def template_key(executable: Path) -> str:
    """範本的名稱：依 Firefox 執行檔的位置、大小與修改時間。

    Playwright 換了 Firefox 版本就是新的範本；舊的範本留著不刪（同一台電腦可能有多個版本在用）。
    """
    try:
        stat = executable.stat()
        identity = f"{executable}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        identity = str(executable)
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def prune(folder: Path, *, older_than: float = STALE_SECONDS, now: float | None = None) -> None:
    """刪除資料夾中超過時限的項目（被強制終止的執行留下的複本、建立到一半的範本）。"""
    limit = (time.time() if now is None else now) - older_than
    try:
        entries = list(folder.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            stale = entry.stat().st_mtime < limit
        except OSError:
            continue
        if stale:
            _remove(entry)


def ensure_template(root: Path, key: str, warm: Callable[[Path], None]) -> Path:
    """確保範本存在，回傳範本資料夾；沒有時用 warm 在暫存資料夾初始化，完成後改名。"""
    template = root / key
    if (template / READY).is_file():
        return template
    root.mkdir(parents=True, exist_ok=True)
    prune(root)
    if template.exists():  # 不完整的範本（例如被刪到一半）
        _remove(template)
    staging = root / f".{key}-{uuid.uuid4().hex[:12]}"
    staging.mkdir()
    try:
        warm(staging)
        (staging / READY).write_text(key, encoding="utf-8")
        try:
            staging.rename(template)
        except OSError:
            # 另一個執行同時建立並先完成了，就用它的
            if not (template / READY).is_file():
                raise
    finally:
        if staging.exists():
            _remove(staging)
    return template


def copy_profile(template: Path, runs: Path) -> Path:
    """把範本複製成這次執行專用的設定檔（不含鎖定檔與完成標記），回傳複本資料夾。"""
    runs.mkdir(parents=True, exist_ok=True)
    prune(runs)
    target = runs / uuid.uuid4().hex
    shutil.copytree(template, target, ignore=shutil.ignore_patterns(READY, *_LOCKS))
    return target


def warm_profile(playwright: Playwright, seconds: float = WARMUP_SECONDS) -> Callable[[Path], None]:
    """初始化設定檔的方式：用它開一次 Firefox（about:blank），開著 seconds 秒再關掉。"""

    def warm(folder: Path) -> None:
        context = playwright.firefox.launch_persistent_context(folder, headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                page.evaluate("1")  # 初始化時這裡會等到瀏覽器恢復回應
                time.sleep(0.1)
        finally:
            context.close()

    return warm


@contextmanager
def firefox_profile(
    playwright: Playwright,
    *,
    budget_seconds: float,
    root: Path | None = None,
    warm: Callable[[Path], None] | None = None,
) -> Generator[Path | None, None, None]:
    """產出這次執行專用的 Firefox 設定檔（預熱範本的複本），離開時刪除。

    做不到時產出 None，呼叫端照舊用 Playwright 的全新設定檔。budget_seconds 是剩下的期限，
    還沒有範本而且期限不夠建立時，這次先不建立。
    """
    base = (cache_dir() if root is None else root) / _FOLDER
    copy: Path | None = None
    try:
        key = template_key(Path(playwright.firefox.executable_path))
        if (base / key / READY).is_file() or budget_seconds >= MIN_BUDGET_SECONDS:
            template = ensure_template(base, key, warm or warm_profile(playwright))
            copy = copy_profile(template, base / _RUNS)
    except Exception as error:  # 範本只是加速；做不到就照舊啟動，原因寫進 automation.log
        sys.stderr.write(t("child.profile_fallback", error=error) + "\n")
        copy = None
    try:
        yield copy
    finally:
        if copy is not None:
            _remove(copy)


def _remove(path: Path) -> None:
    """刪除資料夾或檔案；Windows 上瀏覽器剛結束時檔案可能還被占用，稍等再試，最後放棄。"""
    for attempt in range(5):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.2 * (attempt + 1))
    shutil.rmtree(path, ignore_errors=True)
