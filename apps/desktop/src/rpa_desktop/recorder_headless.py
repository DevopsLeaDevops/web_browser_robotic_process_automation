"""RPA 錄製端不開 App 的視窗（``rpa-recorder --no-window``，M10.2）：自動化、CI 與排查問題用。

和視窗版走同一個 :class:`rpa_desktop.recorder_controller.RecorderController` 與本機閘道
（配對、鑰匙圈、下載瀏覽器、執行管理 Portal 交來的錄製、逐步調試、人工登入），只是沒有 App 自己的
WKWebView 視窗：管理 Portal 用系統的預設瀏覽器打開（``--open``），或把經由閘道打開的網址寫到
``--url-file``（只有本人能讀；自動化用）。訊息寫到日誌（``--log``，預設 ``logs/recorder.log``）。

**有頭模式照樣可以用**：少的只是 App 的視窗。錄製、有頭模式的逐步調試、人工登入的瀏覽器視窗
照樣開在這台；錄製端上線時照樣回報這台能顯示視窗。所以要在登入中的桌面啟動（例如「終端機」），
不要從 SSH 或 launchd 的背景服務啟動：那裡開不出視窗，有頭的工作會失敗。從終端機執行時訊息也印在
終端機。已經在執行時再雙擊 App，這一份用預設瀏覽器打開管理 Portal（沒有視窗可以叫出來）。

結束：在資料夾寫一個 ``stop.request``（見
:meth:`rpa_desktop.single_instance.InstanceLock.request_stop`），或送 SIGINT、SIGTERM、SIGHUP
（關掉終端機）。主執行緒先結束這台的子程序、回報、刪暫存（同視窗版），之後不等管理 Portal 的
長輪詢回來（最多再等 :data:`STOP_SECONDS` 秒）。

結束碼：0 正常停止、1 被管理 Portal 拒絕或程式出錯、2 沒有配對（也沒有給 ``--invite``）或配對失敗、
3 必要的瀏覽器下載失敗、4 同一個資料夾已經有一份在執行（視窗版或另一份 ``--no-window``）。
"""

import argparse
import contextlib
import logging
import os
import signal
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Generator, MutableMapping, Sequence
from pathlib import Path
from typing import Final

from rpa_core.i18n import ENV_VAR, parse_locale, set_locale
from rpa_desktop.build_info import load
from rpa_desktop.credentials import Credentials, KeyringStore, TokenStore
from rpa_desktop.i18n import resolve_locale, t
from rpa_desktop.logs import RedactingFormatter, setup_logging
from rpa_desktop.recorder_controller import SERVICE, RecorderController, RecorderServices
from rpa_desktop.recorder_pages import notice_page, offline_page
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.worker_app import ensure_browsers_path
from rpa_worker.gateway import Gateway

__all__ = ["NO_WINDOW_FLAG", "STOP_SECONDS", "main", "write_private"]

logger = logging.getLogger("rpa_desktop.recorder_headless")

NO_WINDOW_FLAG: Final = "--no-window"
STOP_SECONDS: Final = 15.0
"""要求結束之後最多等背景工作這麼久（管理 Portal 的長輪詢最多 25 秒，不等它）。"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpa-recorder --no-window", description=t("recorder.description")
    )
    parser.add_argument("--invite", metavar="INVITE", help=t("recorder.invite_help"))
    parser.add_argument("--server", metavar="URL", help=t("recorder.server_help"))
    parser.add_argument("--name", help=t("worker.name_help"))
    parser.add_argument("--reset-pairing", action="store_true", help=t("worker.reset_help"))
    parser.add_argument("--firefox", action="store_true", help=t("worker.firefox_help"))
    parser.add_argument(
        "--no-testsite",
        dest="testsite",
        action="store_false",
        help=t("worker.no_testsite_help", port=8765),
    )
    parser.add_argument("--open", action="store_true", help=t("recorder.open_help"))
    parser.add_argument("--url-file", type=Path, metavar="FILE", help=t("recorder.url_file_help"))
    parser.add_argument("--log", type=Path, metavar="FILE", help=t("window.log_help"))
    return parser


def write_private(path: Path, text: str) -> None:
    """寫一個只有本人能讀寫的檔案（網址帶著閘道的密語）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


@contextlib.contextmanager
def _signals(handler: Callable[[], object]) -> Generator[None]:
    """Ctrl+C（SIGINT）、SIGTERM 與關掉終端機（SIGHUP）要求結束。

    ``handler`` 只能設旗標：收拾（結束子程序、刪暫存）在主迴圈做。只有主執行緒能設定訊號
    （測試在別的執行緒呼叫時略過）。
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    names = [signal.SIGINT]
    if sys.platform != "win32":
        names += [signal.SIGTERM, signal.SIGHUP]
    previous = {name: signal.getsignal(name) for name in names}
    for name in names:
        signal.signal(name, lambda signum, frame: handler())
    try:
        yield
    finally:
        for name, value in previous.items():
            signal.signal(name, value)


def _terminal_output() -> logging.Handler | None:
    """從終端機執行時，訊息也印在終端機（日誌照寫；權杖、邀請代碼、閘道的密語一樣遮掉）。"""
    stream = sys.stderr
    try:
        interactive = stream is not None and stream.isatty()
    except (AttributeError, ValueError):
        interactive = False
    if not interactive:
        return None
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    return handler


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    """macOS 經由 LaunchServices 啟動時可能帶著 ``-psn_…``：略過它，其他不認得的參數照樣報錯。"""
    parser = _parser()
    args, unknown = parser.parse_known_args(list(argv))
    others = [arg for arg in unknown if not arg.startswith("-psn_")]
    if others:
        parser.error(" ".join(others))
    return args


def main(
    argv: Sequence[str] = (),
    *,
    environ: MutableMapping[str, str] | None = None,
    store: TokenStore | None = None,
    services: RecorderServices | None = None,
    open_browser: Callable[[str], object] = webbrowser.open,
) -> int:
    from rpa_desktop.recorder_gui import LOG_FILE, recorder_dir

    env: MutableMapping[str, str] = os.environ if environ is None else environ
    set_locale(resolve_locale(env))
    args = _parse(argv)
    ensure_browsers_path(env)
    home = recorder_dir(env)
    path = setup_logging(home / "logs", file=args.log or home / "logs" / LOG_FILE)
    terminal = _terminal_output()
    build = load()
    logger.info("RPA 錄製端 %s（--no-window）資料夾 %s，日誌 %s", build.version, home, path)
    lock = InstanceLock(home)
    if not lock.acquire():
        logger.error("%s", t("recorder.no_window_busy", home=home))
        if terminal is not None:
            logging.getLogger().removeHandler(terminal)
        return 4
    url_file: Path | None = args.url_file
    gateway: Gateway | None = None
    try:
        override = env.get(ENV_VAR)
        controller = RecorderController(
            home=home,
            build=build,
            environ=env,
            credentials=Credentials(home, KeyringStore(SERVICE) if store is None else store),
            services=services,
            name=args.name,
            testsite=bool(args.testsite),
            language=parse_locale(override) if override else None,
        )
        set_locale(controller.locale)
        if args.reset_pairing:
            controller.credentials.clear()
            logger.info("%s", t("worker.reset_done"))
        if args.firefox and not controller.settings.firefox:
            controller.set_firefox(True)
        servers: list[Gateway] = []  # 離線頁要顯示閘道目前轉送到哪裡
        gateway = Gateway(
            None,
            controller.token,
            on_unauthorized=controller.unauthorized,
            offline_page=offline_page(lambda: controller.locale, lambda: servers[0].server),
            notice_page=notice_page(lambda: controller.locale, window=False),
        )
        servers.append(gateway)
        controller.attach(gateway)
        gateway.start()
        portal = gateway.login_url("/")
        if url_file is not None:
            write_private(url_file, portal + "\n")
        opened = False

        def on_change() -> None:
            nonlocal opened
            if args.open and not opened and controller.phase == "online":
                opened = True
                open_browser(portal)

        controller.subscribe(on_change)
        stopping = threading.Event()

        def on_show() -> None:
            # 又雙擊了 App（視窗版拿不到鎖，請這一份叫出畫面）：這一份沒有視窗，改開瀏覽器
            logger.info("又開了一次 RPA 錄製端：用預設瀏覽器打開管理 Portal")
            open_browser(portal)

        finished = threading.Event()
        lock.watch(on_show, finished, on_stop=stopping.set)
        with _signals(stopping.set):
            try:
                controller.start(args.invite, args.server)
                deadline: float | None = None
                while not controller.wait(0.5):
                    if stopping.is_set() and deadline is None:
                        # 在主執行緒做完收拾（結束子程序、回報、刪暫存）才開始計時：不讓背景的
                        # 收拾做到一半就結束程序（同視窗版的 _finish）
                        logger.info("要求結束")
                        controller.stop_now()
                        deadline = time.monotonic() + STOP_SECONDS
                    if deadline is not None and time.monotonic() > deadline:
                        logger.info("錄製端的連線還沒結束，直接結束")
                        break
            finally:
                finished.set()
        code = controller.exit_code
        logger.info("RPA 錄製端結束（%s）：%s", controller.phase, code)
        return code
    finally:
        if gateway is not None:
            gateway.close()
        if url_file is not None:
            with contextlib.suppress(OSError):
                url_file.unlink()
        lock.release()
        if terminal is not None:
            logging.getLogger().removeHandler(terminal)
