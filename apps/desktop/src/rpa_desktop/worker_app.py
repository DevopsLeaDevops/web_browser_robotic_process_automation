"""RPA Worker 的主控台版（M10.1，ADR 0014）：``rpa-child.exe --worker``，排查問題用。

打包後雙擊 ``rpa-worker.exe`` 開的是視窗版（:mod:`rpa_desktop.gui`）；這裡是第一步交付的主控台版，
兩者共用同一份配對（:mod:`rpa_desktop.credentials`）與單一執行鎖（同一時間只能開一份）：

1. 讀存下的配對；沒有就請使用者貼上邀請（或用 ``--invite``），經由 Client API 換到權杖並存起來。
2. 必要的 Chromium 還沒下載時，用 App 內附的 Playwright 下載（主控台上看得到進度）；
   Firefox 選用：第一次配對時詢問，或加上 ``--firefox``。
3. 在 127.0.0.1:8765 啟動測試網站（已經有就沿用），範例場景對它執行。
4. 連上管理 Portal 領取任務（:func:`rpa_worker.service.run_remote_worker`，和 ``rpa worker``
   相同），直到按 Ctrl+C 或關掉視窗。權杖被拒（重新邀請、停用、刪除）時清除配對，
   下次開啟重新貼邀請。

資料夾：Windows 是 ``%LOCALAPPDATA%\\rpa\\worker``（開發時的 macOS、Linux 見 :func:`data_dir`），
可以用環境變數 ``RPA_WORKER_HOME`` 改。權杖存在作業系統的認證管理員，不能用時退回資料夾裡只有本人
能讀寫的 ``pairing.json``。瀏覽器放在 Playwright 預設的位置（:func:`browsers_dir`）。
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Final, TextIO

from rpa_core.i18n import set_locale
from rpa_desktop.build_info import load
from rpa_desktop.credentials import Credentials, TokenStore
from rpa_desktop.i18n import resolve_locale, t
from rpa_desktop.single_instance import InstanceLock
from rpa_runner.commands import is_frozen, playwright_command
from rpa_worker.pairing import InviteError, pair, parse_invite
from rpa_worker.remote import ConnectionLostError, WorkerApiError
from testsite.server import DEFAULT_PORT as TESTSITE_PORT

__all__ = [
    "BROWSERS_ENV",
    "ENV_HOME",
    "REQUIRED_ENGINE",
    "browsers_dir",
    "data_dir",
    "describe_event",
    "ensure_browsers_path",
    "main",
    "obtain_credentials",
    "prepare_browsers",
]

ENV_HOME: Final = "RPA_WORKER_HOME"
BROWSERS_ENV: Final = "PLAYWRIGHT_BROWSERS_PATH"
REQUIRED_ENGINE: Final = "chromium"
OPTIONAL_ENGINE: Final = "firefox"
_NAMES: Final = {"chromium": "Chromium", "firefox": "Firefox"}

Say = Callable[[str], None]
"""在主控台印一行。"""
Ask = Callable[[str], str]
"""問使用者一個問題，回傳輸入的那一行（沒有人可以回答時呼叫的人傳 None）。"""
Install = Callable[[str], int]
"""下載一個瀏覽器，回傳結束碼。"""


def _home(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("USERPROFILE") or environ.get("HOME") or Path.home())


def data_dir(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """RPA Worker 的資料夾：配對結果、任務的暫存與執行目錄。"""
    override = environ.get(ENV_HOME)
    if override:
        return Path(override).expanduser()
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or str(_home(environ) / "AppData" / "Local")
        return Path(base) / "rpa" / "worker"
    if platform == "darwin":
        return _home(environ) / "Library" / "Application Support" / "rpa" / "worker"
    base = environ.get("XDG_DATA_HOME") or str(_home(environ) / ".local" / "share")
    return Path(base) / "rpa" / "worker"


def browsers_dir(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Playwright 預設放瀏覽器的位置（和開發環境 ``playwright install`` 的位置相同）。"""
    if platform == "win32":
        base = environ.get("LOCALAPPDATA") or str(_home(environ) / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if platform == "darwin":
        return _home(environ) / "Library" / "Caches" / "ms-playwright"
    base = environ.get("XDG_CACHE_HOME") or str(_home(environ) / ".cache")
    return Path(base) / "ms-playwright"


def ensure_browsers_path(environ: MutableMapping[str, str], *, frozen: bool | None = None) -> None:
    """打包後明確指定瀏覽器的位置，子程序也跟著用。

    沒設定或設成 ``0``（放在套件裡，打包工具可能這樣設）時改成 :func:`browsers_dir`；
    使用者自己設定了其他位置就照用。
    """
    if not (is_frozen() if frozen is None else frozen):
        return
    if environ.get(BROWSERS_ENV, "") in ("", "0"):
        environ[BROWSERS_ENV] = str(browsers_dir(environ))


def describe_event(event: str, details: Mapping[str, object]) -> str | None:
    """遠端任務來源的事件 → 給人看的一行；不需要顯示的回傳 None。"""
    if event == "online":
        line = t("worker.event_online", worker=details.get("worker"))
        if details.get("sameVersion") is False:
            line += "\n" + t(
                "worker.event_version",
                mine=details.get("fingerprint"),
                theirs=details.get("serverFingerprint"),
            )
        return line
    if event == "claimed":
        window = t("worker.headless") if details.get("headless") else t("worker.headed")
        return t("worker.event_claimed", run=details.get("run"), window=window)
    if event in ("offline", "reported", "abandoned", "report_failed", "rejected"):
        return t(f"worker.event_{event}", **dict(details))
    return None


def _invite_problem(error: InviteError) -> str:
    return t("worker.invite_" + error.reason)


def obtain_credentials(
    credentials: Credentials,
    *,
    invite: str | None,
    server: str | None,
    ask: Ask | None,
    say: Say,
) -> tuple[str, str] | None:
    """決定連哪個管理 Portal、用哪個權杖：``--invite`` → 存下的配對 → 問使用者。

    配對成功就存起來。沒有人可以回答又沒有配對、或使用者放棄時回傳 None。
    """
    if invite is None:
        saved = credentials.load()
        if saved is not None:
            say(t("worker.saved", server=saved.server))
            return saved.server, saved.token
        if ask is None:
            say(t("worker.no_pairing"))
            return None
    while True:
        text = invite
        invite = None  # 命令列給的只試一次；失敗後改問使用者
        if text is None:
            if ask is None:
                return None
            text = ask(t("worker.ask_invite")).strip()
            if not text:
                return None
        try:
            parsed = parse_invite(text, server)
        except InviteError as error:
            if error.reason != "server" or ask is None or text.lower().startswith("rpa://"):
                say(_invite_problem(error))
                continue
            server = ask(t("worker.ask_server")).strip()
            if not server:
                return None
            invite = text  # 有了網址再試一次同一個代碼
            continue
        try:
            result = pair(parsed, "worker")
        except WorkerApiError as error:
            say(t("worker.pair_rejected", message=error.message))
            continue
        except ConnectionLostError as error:
            say(t("worker.pair_offline", server=parsed.server, reason=error))
            continue
        credentials.save(result)
        say(t("worker.paired", name=result.name, device=result.device))
        return result.server, result.token


def _install(engine: str) -> int:
    """用 App 內附的 Playwright 下載瀏覽器；子程序直接寫到這個主控台，看得到進度。"""
    return subprocess.run(playwright_command(["install", engine]), check=False).returncode


def prepare_browsers(
    engines: Sequence[str],
    *,
    missing: Callable[[Sequence[str]], list[str]],
    say: Say,
    install: Install = _install,
) -> bool:
    """下載還沒有的瀏覽器；必要的 Chromium 下載失敗時回傳 False（選用的失敗只提醒）。"""
    for engine in missing(engines):
        name = _NAMES.get(engine, engine)
        say(t("worker.downloading", browser=name))
        code = install(engine)
        if code != 0:
            say(t("worker.download_failed", browser=name, code=code))
            if engine == REQUIRED_ENGINE:
                return False
            continue
        say(t("worker.downloaded", browser=name))
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rpa-worker", description=t("worker.description"))
    parser.add_argument("--invite", metavar="INVITE", help=t("worker.invite_help"))
    parser.add_argument("--server", metavar="URL", help=t("worker.server_help"))
    parser.add_argument("--name", help=t("worker.name_help"))
    parser.add_argument("--reset-pairing", action="store_true", help=t("worker.reset_help"))
    parser.add_argument("--firefox", action="store_true", help=t("worker.firefox_help"))
    parser.add_argument(
        "--no-testsite",
        dest="testsite",
        action="store_false",
        help=t("worker.no_testsite_help", port=TESTSITE_PORT),
    )
    parser.add_argument("--keep-runs", action="store_true", help=t("worker.keep_runs_help"))
    return parser


def _is_console(stream: TextIO | None) -> bool:
    """標準輸入是不是真的主控台。Windows 上 NUL（沒有輸入）的 isatty() 也是 True，要再確認。"""
    if stream is None or not stream.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes
    import msvcrt

    mode = ctypes.c_uint32()
    handle = msvcrt.get_osfhandle(stream.fileno())
    return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


def _answer(question: str) -> str:
    """問一個問題；輸入結束（EOF）或按 Ctrl+C 視為沒有回答。"""
    try:
        return input(question)
    except (EOFError, KeyboardInterrupt):
        sys.stdout.write("\n")
        return ""


def _console_ask() -> Ask | None:
    """有人在主控台前（雙擊開啟、終端機）才問問題；CI、背景執行時回傳 None。"""
    return _answer if _is_console(sys.stdin) else None


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main(
    argv: Sequence[str] = (),
    *,
    environ: MutableMapping[str, str] | None = None,
    ask: Ask | None = None,
    say: Say = _say,
    console: bool = True,
    store: TokenStore | None = None,
) -> int:
    """主控台版的入口；回傳結束碼（0 正常停止、1 被管理 Portal 拒絕、2 沒有配對、3 瀏覽器、
    4 已經有一份在執行）。

    ``console`` 為 True 時，有人在主控台前才問問題（測試改傳 ``ask``）；``store`` 是測試用的
    認證管理員替身。
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    set_locale(resolve_locale(env))
    args = _parser().parse_args(list(argv))
    if console:
        ask = _console_ask()
    code = _run(args, env, ask, say, store)
    if code != 0 and ask is not None:
        ask(t("worker.press_enter"))  # 雙擊開啟的視窗不要一閃就關掉，讓人看得到原因
    return code


def _run(
    args: argparse.Namespace,
    env: MutableMapping[str, str],
    ask: Ask | None,
    say: Say,
    store: TokenStore | None,
) -> int:
    ensure_browsers_path(env)
    build = load()
    home = data_dir(env)
    say(t("worker.banner", version=build.version, home=home))
    lock = InstanceLock(home)
    if not lock.acquire():
        say(t("worker.already_running", home=home))
        return 4
    try:
        return _work(args, env, ask, say, Credentials(home, store), home)
    finally:
        lock.release()


def _work(
    args: argparse.Namespace,
    env: MutableMapping[str, str],
    ask: Ask | None,
    say: Say,
    credentials: Credentials,
    home: Path,
) -> int:
    # 只有真的執行 worker 時才載入 Playwright 與 runner（子程序也經過 entry，要啟動得快）
    from rpa_runner.installed import missing_browsers
    from rpa_worker.environment import WorkerInfo
    from rpa_worker.remote import WorkerClient
    from rpa_worker.service import run_remote_worker
    from testsite.server import start_in_background

    build = load()
    if args.reset_pairing:
        credentials.clear()
        say(t("worker.reset_done"))
    first_time = credentials.load() is None or args.invite is not None
    found = obtain_credentials(
        credentials, invite=args.invite, server=args.server, ask=ask, say=say
    )
    if found is None:
        return 2
    server, token = found

    engines = [REQUIRED_ENGINE]
    wants_firefox = bool(args.firefox)
    if not wants_firefox and first_time and ask is not None:
        wants_firefox = ask(t("worker.ask_firefox")).strip().lower() in ("y", "yes", "是")
    if wants_firefox:
        engines.append(OPTIONAL_ENGINE)
    if not prepare_browsers(engines, missing=missing_browsers, say=say):
        return 3

    site = None
    if args.testsite:
        site, state, detail = start_in_background(TESTSITE_PORT)
        url = f"http://127.0.0.1:{TESTSITE_PORT}/"
        say(t(f"worker.testsite_{state}", url=url, port=TESTSITE_PORT, error=detail))

    info = WorkerInfo.detect(
        args.name or socket.gethostname(), fingerprint=build.fingerprint, version=build.version
    )
    if not info.display:
        say(t("worker.no_display"))
    say(t("worker.started", name=info.name, server=server))

    stop = threading.Event()
    rejected: list[int] = []

    def notify(event: str, details: Mapping[str, object]) -> None:
        if event == "rejected":
            status = details.get("status")
            rejected.append(status if isinstance(status, int) else 0)
        line = describe_event(event, details)
        if line is not None:
            say(line)

    def request_stop(signum: int, frame: object) -> None:
        stop.set()

    previous = signal.signal(signal.SIGINT, request_stop)
    if sys.platform == "win32":  # Windows 主控台的 Ctrl+Break
        signal.signal(signal.SIGBREAK, request_stop)
    try:
        fatal = run_remote_worker(
            WorkerClient(server, token),
            info,
            home / "work",
            stop=stop,
            notify=notify,
            keep_runs=bool(args.keep_runs),
            on_stopping=lambda: say(t("worker.stopping")),
        )
    finally:
        signal.signal(signal.SIGINT, previous)
        if site is not None:
            site.shutdown()
            site.server_close()
    if fatal is None:
        return 0
    if rejected and rejected[-1] in (401, 403):
        credentials.clear()
        say(t("worker.pairing_cleared"))
    return 1
