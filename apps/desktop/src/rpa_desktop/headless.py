"""RPA Worker 不開視窗（``rpa-worker.exe --no-window``，M10.1）：自動化與 CI 用。

和視窗版走同一個 :class:`rpa_desktop.controller.WorkerController`（配對、認證管理員、下載瀏覽器、
接任務），只是沒有視窗與通知區圖示，訊息寫到日誌（``--log``，預設在資料夾的 ``logs/``）。
不寫「登入時自動啟動」：那是視窗版的選擇。視窗程式沒有主控台，用 ``--log`` 看進度。
結束：在資料夾寫一個 ``stop.request``（視窗程式收不到 Ctrl+C；見
:meth:`rpa_desktop.single_instance.InstanceLock.request_stop`），執行中的任務會被取消並回報；
或直接結束程序（任務約一分鐘後判定失聯）。

結束碼：0 正常停止、1 被管理 Portal 拒絕或程式出錯、2 沒有配對（也沒有給 ``--invite``）、
3 必要的瀏覽器下載失敗、4 同一個資料夾已經有一份在執行。
"""

import argparse
import logging
import os
import signal
import sys
import threading
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Final

from rpa_core.i18n import ENV_VAR, parse_locale, set_locale
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import load
from rpa_desktop.controller import Services, WorkerController
from rpa_desktop.credentials import Credentials, TokenStore
from rpa_desktop.i18n import platform_key, resolve_locale, t
from rpa_desktop.logs import setup_logging
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.worker_app import data_dir, ensure_browsers_path

__all__ = ["NO_WINDOW_FLAG", "main"]

logger = logging.getLogger("rpa_desktop.headless")

NO_WINDOW_FLAG: Final = "--no-window"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpa-worker --no-window", description=t("worker.description")
    )
    parser.add_argument("--invite", metavar="INVITE", help=t("worker.invite_help"))
    parser.add_argument("--server", metavar="URL", help=t("worker.server_help"))
    parser.add_argument("--name", help=t("worker.name_help"))
    parser.add_argument("--reset-pairing", action="store_true", help=t("worker.reset_help"))
    parser.add_argument("--firefox", action="store_true", help=t("worker.firefox_help"))
    parser.add_argument(
        "--no-testsite",
        dest="testsite",
        action="store_false",
        help=t("worker.no_testsite_help", port=8765),
    )
    parser.add_argument("--keep-runs", action="store_true", help=t("worker.keep_runs_help"))
    parser.add_argument("--log", type=Path, metavar="FILE", help=t("window.log_help"))
    return parser


def main(
    argv: Sequence[str] = (),
    *,
    environ: MutableMapping[str, str] | None = None,
    store: TokenStore | None = None,
    services: Services | None = None,
) -> int:
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    set_locale(resolve_locale(env))
    args = _parser().parse_args(list(argv))
    ensure_browsers_path(env)
    home = data_dir(env)
    path = setup_logging(home / "logs", file=args.log)
    build = load()
    logger.info("RPA Worker %s（--no-window）資料夾 %s，日誌 %s", build.version, home, path)
    lock = InstanceLock(home)
    if not lock.acquire():
        logger.error("%s", t(platform_key("worker.already_running"), home=home))
        return 4
    try:
        override = env.get(ENV_VAR)
        controller = WorkerController(
            home=home,
            build=build,
            environ=env,
            credentials=Credentials(home, store),
            autostart=AutoStart(None, Path(sys.executable)),
            services=services,
            name=args.name,
            testsite=bool(args.testsite),
            keep_runs=bool(args.keep_runs),
            firefox=bool(args.firefox),
            language=parse_locale(override) if override else None,
        )
        if args.reset_pairing:
            controller.credentials.clear()
            logger.info("%s", t("worker.reset_done"))

        def request_stop(signum: int, frame: object) -> None:
            controller.stop()

        previous = signal.signal(signal.SIGINT, request_stop)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, request_stop)
        finished = threading.Event()
        lock.watch(None, finished, on_stop=controller.stop)
        try:
            controller.start(args.invite, args.server)
            while not controller.wait(0.5):
                pass
        finally:
            finished.set()
            signal.signal(signal.SIGINT, previous)
        logger.info("RPA Worker 結束（%s）：%s", controller.phase, controller.exit_code)
        return controller.exit_code
    finally:
        lock.release()
