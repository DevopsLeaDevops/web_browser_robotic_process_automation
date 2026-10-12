"""登入狀態：每個角色一份 storageState，執行前先檢查是否已登入（M4）。

角色的設定（:class:`LoginSettings`）由管理 Portal 提供：

- 確認網址與「已登入時看得到的元素」（DSL 定位器）：打開確認網址，等這個元素出現就算已登入。
- 選用的自動登入步驟（DSL 步驟，帳密用 ``{{ secrets.名稱 }}``）：沒登入時先自動登入一次。
- 登入狀態檔：只有本人能讀寫（M8 加密）；不放進執行目錄，不出現在報告與日誌。

兩種子程序（由 run.py 與管理 Portal 啟動）::

    python -m rpa_runner.login check --out 目錄 --deadline 秒數 [--engine 瀏覽器]
    python -m rpa_runner.login capture --state 新狀態檔 [--engine 瀏覽器]

設定以 JSON 放在環境變數 ``RPA_LOGIN``，Secrets 也從環境變數讀取。

- ``check``：無頭模式檢查；沒登入而且有自動登入步驟時先自動登入。結果寫在 ``login.json``，
  沒登入時另存截圖 ``login.png``。退出碼 0 已登入、4 需要登入、3 總期限已到、1 其他錯誤。
  檢查通過後把最新的狀態寫回狀態檔（網站換發 cookie 時跟著更新）。
- ``capture``（人工登入）：在這台電腦開瀏覽器視窗到登入網址，由使用者自己登入（可以處理 SSO、
  驗證碼、二次驗證）。標準輸入收到 ``finish`` 或使用者關掉視窗時，把登入狀態存到 ``--state``；
  收到 ``cancel`` 時不存。進度以一行一個 JSON 印在標準輸出：ready、saved、cancelled、error。
"""

import argparse
import contextlib
import json
import os
import queue
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from rpa_core.dsl import Locator, Scenario
from rpa_core.i18n import DEFAULT_LOCALE, ENV_VAR, parse_locale, set_locale
from rpa_runner.browser import Deadline, DeadlineExceeded, plan_records, resolve, run_steps
from rpa_runner.contexts import Engine, open_context
from rpa_runner.files import LOGIN, LOGIN_SCREENSHOT, write_json
from rpa_runner.i18n import t
from rpa_runner.secrets import mask

__all__ = [
    "CHECK_TIMEOUT_MS",
    "ENV_LOGIN",
    "EXIT_CANCELLED",
    "EXIT_NEEDS_LOGIN",
    "LoginSettings",
    "is_logged_in",
    "main",
    "save_state",
]

ENV_LOGIN: Final = "RPA_LOGIN"
"""角色設定（JSON）的環境變數。"""
EXIT_NEEDS_LOGIN: Final = 4
EXIT_CANCELLED: Final = 2
_EXIT_FAILED: Final = 1
_EXIT_DEADLINE: Final = 3
CHECK_TIMEOUT_MS: Final = 10_000
"""等「已登入時看得到的元素」出現的時間。"""
_PUMP_MS: Final = 300


@dataclass(frozen=True, slots=True)
class LoginSettings:
    """一個角色的登入設定。"""

    role: str
    """角色代號（場景的 ``login.role``）。"""
    state: Path
    """登入狀態檔（Playwright storageState）；不存在代表還沒登入過。"""
    check_url: str | None = None
    """確認是否已登入時打開的網址；None 代表不檢查，只載入登入狀態（例如命令列只給了狀態檔）。"""
    check: Mapping[str, object] | None = None
    """已登入時看得到的元素（DSL 定位器，camelCase 欄位）。"""
    login_url: str | None = None
    """人工登入時打開的網址。"""
    steps: tuple[Mapping[str, object], ...] = ()
    """自動登入步驟（DSL 步驟）；沒有代表只能人工登入。"""
    secrets: tuple[str, ...] = ()
    """自動登入步驟用到的 Secrets 名稱。"""
    name: str | None = None
    """角色名稱，給人看。"""

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "state": str(self.state),
            "checkUrl": self.check_url,
            "check": dict(self.check) if self.check is not None else None,
            "loginUrl": self.login_url,
            "steps": [dict(step) for step in self.steps],
            "secrets": list(self.secrets),
            "name": self.name,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "LoginSettings":
        steps = cast("list[Mapping[str, object]]", data.get("steps") or [])
        check = data.get("check")
        return cls(
            role=str(data["role"]),
            state=Path(str(data["state"])),
            check_url=cast("str | None", data.get("checkUrl")),
            check=cast("Mapping[str, object]", check) if isinstance(check, dict) else None,
            login_url=cast("str | None", data.get("loginUrl")),
            steps=tuple(steps),
            secrets=tuple(cast("list[str]", data.get("secrets") or [])),
            name=cast("str | None", data.get("name")),
        )

    @property
    def label(self) -> str:
        return self.name or self.role

    def auto_scenario(self) -> Scenario | None:
        """自動登入步驟包成一個場景（用同一套步驟執行與 ``{{ }}`` 代入）；沒有步驟時回傳 None。"""
        if not self.steps:
            return None
        return Scenario.model_validate(
            {
                "schemaVersion": 1,
                "id": "login",
                "name": self.label,
                "secrets": list(self.secrets),
                "steps": [dict(step) for step in self.steps],
            }
        )


@dataclass(slots=True)
class _Check:
    logged_in: bool
    url: str | None = None
    refreshed: bool = False
    """這次自動登入過。"""
    error: str | None = None
    steps: list[dict[str, object]] = field(default_factory=list[dict[str, object]])


def save_state(context: BrowserContext, path: Path) -> None:
    """把目前的登入狀態寫到 path：先寫暫存檔再改名；只有本人能讀寫。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    data = context.storage_state()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(temporary, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)


def is_logged_in(page: Page, settings: LoginSettings, timeout_ms: int) -> bool:
    """打開確認網址，在 timeout_ms 內看到「已登入時看得到的元素」就算已登入。"""
    if settings.check_url is None or settings.check is None:
        return True
    page.goto(settings.check_url, wait_until="domcontentloaded", timeout=timeout_ms)
    locator = resolve(page, Locator.model_validate(dict(settings.check)))
    try:
        locator.first.wait_for(state="visible", timeout=min(timeout_ms, CHECK_TIMEOUT_MS))
    except PlaywrightTimeoutError:
        return False
    return True


def _auto_login(
    page: Page,
    settings: LoginSettings,
    secrets: Mapping[str, str],
    out: Path,
    deadline: Deadline,
    result: _Check,
) -> None:
    scenario = settings.auto_scenario()
    if scenario is None:
        return
    records = plan_records(scenario)
    try:
        run_steps(
            page,
            scenario,
            records=records,
            context={"inputs": {}, "secrets": dict(secrets), "env": dict(os.environ)},
            base_url=None,
            artifacts=out,
            deadline=deadline,
        )
    finally:
        result.steps = [
            {**record.to_json(), "error": mask(record.error or "", secrets) or None}
            for record in records
        ]


def check(args: argparse.Namespace, settings: LoginSettings, secrets: Mapping[str, str]) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    deadline = Deadline.after(float(args.deadline))
    result = _Check(logged_in=False)
    page: Page | None = None
    code = _EXIT_FAILED
    with sync_playwright() as playwright, contextlib.ExitStack() as stack:
        try:
            context = open_context(
                playwright,
                cast("Engine", args.engine),
                headed=False,
                timeout_ms=deadline.budget(60_000),
                budget_seconds=deadline.remaining_ms() / 1000,
                stack=stack,
                storage_state=settings.state,
            )
            page = context.pages[0] if context.pages else context.new_page()
            result.logged_in = is_logged_in(page, settings, deadline.budget(30_000))
            if not result.logged_in and settings.steps:
                _auto_login(page, settings, secrets, out, deadline, result)
                result.logged_in = is_logged_in(page, settings, deadline.budget(30_000))
                result.refreshed = result.logged_in
            result.url = page.url
            if result.logged_in:
                if settings.check_url is not None:
                    save_state(context, settings.state)
                code = 0
            else:
                code = EXIT_NEEDS_LOGIN
                page.screenshot(path=out / LOGIN_SCREENSHOT, timeout=deadline.budget(5_000))
        except BaseException as error:
            timed_out = isinstance(error, DeadlineExceeded) or deadline.remaining_ms() <= 0
            result.error = mask(f"{type(error).__name__}: {error}".splitlines()[0], secrets)
            result.url = page.url if page is not None else None
            code = _EXIT_DEADLINE if timed_out else _EXIT_FAILED
            sys.stderr.write(mask(f"{type(error).__name__}: {error}", secrets) + "\n")
        finally:
            status = {0: "passed", EXIT_NEEDS_LOGIN: "needs_login", _EXIT_DEADLINE: "timed_out"}
            write_json(
                out / LOGIN,
                {
                    "role": settings.role,
                    "status": status.get(code, "failed"),
                    "refreshed": result.refreshed,
                    "url": result.url,
                    "error": result.error,
                    "steps": result.steps,
                },
            )
    return code


# ---------------------------------------------------------------- 人工登入


def _emit(event: str, **details: object) -> None:
    sys.stdout.write(json.dumps({"event": event, **details}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read_commands(commands: "queue.Queue[str]") -> None:
    """從標準輸入讀命令；標準輸入關閉（啟動它的程式不在了）就當作取消。"""
    for line in sys.stdin:
        commands.put(line.strip())
    commands.put("cancel")


def capture(args: argparse.Namespace, settings: LoginSettings) -> int:
    commands: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_read_commands, args=(commands,), daemon=True).start()
    with sync_playwright() as playwright, contextlib.ExitStack() as stack:
        try:
            context = open_context(
                playwright,
                cast("Engine", args.engine),
                headed=not args.headless,
                timeout_ms=60_000,
                budget_seconds=60,
                stack=stack,
                # 一般的 context：使用者關掉視窗後瀏覽器還在，才拿得到登入狀態
                persistent=False,
            )
            page = context.pages[0] if context.pages else context.new_page()
            if settings.login_url:
                page.goto(settings.login_url, wait_until="domcontentloaded", timeout=60_000)
        except BaseException as error:
            _emit("error", message=f"{type(error).__name__}: {error}".splitlines()[0])
            return _EXIT_FAILED
        _emit("ready")
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = ""
            if command == "cancel":
                _emit("cancelled")
                return EXIT_CANCELLED
            pages = context.pages
            if command == "finish" or not pages:
                break
            try:
                # 讓 Playwright 處理瀏覽器的事件（例如使用者關掉分頁），同時等下一個命令
                pages[0].wait_for_timeout(_PUMP_MS)
            except PlaywrightError:
                time.sleep(0.05)  # 分頁剛好被關掉；下一輪再看還有沒有分頁
        try:
            save_state(context, Path(args.state))
        except PlaywrightError:
            _emit("error", message=t("login.browser_closed"))
            return _EXIT_FAILED
        _emit("saved")
        return 0


# ---------------------------------------------------------------- 入口


def _secrets(settings: LoginSettings) -> dict[str, str]:
    return {name: os.environ[name] for name in settings.secrets if name in os.environ}


def main(argv: Sequence[str] | None = None) -> int:
    set_locale(parse_locale(os.environ.get(ENV_VAR, "")) or DEFAULT_LOCALE)
    parser = argparse.ArgumentParser(prog="python -m rpa_runner.login")
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check")
    checking.add_argument("--out", required=True)
    checking.add_argument("--deadline", required=True, help="總期限剩下的秒數")
    checking.add_argument("--engine", choices=["chromium", "firefox", "webkit"], default="chromium")
    capturing = commands.add_parser("capture")
    capturing.add_argument("--state", required=True, help="人工登入後的狀態存到這裡")
    # 只給自動測試用：沒有圖形介面的環境也能測試命令與結束的流程
    capturing.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    capturing.add_argument(
        "--engine", choices=["chromium", "firefox", "webkit"], default="chromium"
    )
    args = parser.parse_args(argv)
    settings = LoginSettings.from_json(cast("dict[str, object]", json.loads(os.environ[ENV_LOGIN])))
    if args.command == "check":
        return check(args, settings, _secrets(settings))
    return capture(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
