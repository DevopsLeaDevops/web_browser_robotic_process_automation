"""`rpa worker`：在這台電腦當遠端 worker，向管理 Portal 領取任務執行（M9a，ADR 0012）。

- 權杖來自環境變數 ``RPA_WORKER_TOKEN`` 或 ``--token-file``（不放在命令列，避免留在命令歷史）。
- M10.1：也可以用裝置頁的邀請配對（``--invite``）：邀請一次性、24 小時內有效，換到的權杖存在
  工作資料夾的 ``pairing.json``（只有本人能讀寫），之後直接 ``rpa worker`` 就能啟動。
- 預設一起在 127.0.0.1:8765 啟動本機測試網站：範例場景對它執行，網址和管理 Portal 那台一樣。
- 一次執行一個任務；有頭模式的瀏覽器視窗出現在這台電腦。Ctrl+C 停止（執行中的任務會被取消並回報）。
- 連不上管理 Portal 時自動重試；權杖被拒或協定版本不同時結束。
"""

import os
import signal
import socket
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import click

from rpa_cli.i18n import t
from rpa_cli.serve import browser_warning, start_testsite
from testsite.server import DEFAULT_PORT as TESTSITE_PORT

__all__ = [
    "DEFAULT_WORK_DIR",
    "TOKEN_ENV",
    "build_worker_command",
    "describe_event",
    "resolve_credentials",
]

TOKEN_ENV: Final = "RPA_WORKER_TOKEN"
DEFAULT_WORK_DIR: Final = Path("worker-data")


def describe_event(event: str, details: Mapping[str, object]) -> str | None:
    """遠端任務來源的事件 → 給人看的一行；不需要顯示的回傳 None。"""
    if event == "online":
        lines = [t("cli.worker.event_online", worker=details.get("worker"))]
        if details.get("sameVersion") is False:
            lines.append(
                t(
                    "cli.worker.event_version",
                    mine=details.get("fingerprint"),
                    theirs=details.get("serverFingerprint"),
                )
            )
        return "\n".join(lines)
    if event == "offline":
        return t(
            "cli.worker.event_offline", server=details.get("server"), reason=details.get("reason")
        )
    if event == "claimed":
        window = t("cli.worker.headless") if details.get("headless") else t("cli.worker.headed")
        return t("cli.worker.event_claimed", run=details.get("run"), window=window)
    if event == "reported":
        return t("cli.worker.event_reported", run=details.get("run"), status=details.get("status"))
    if event == "abandoned":
        return t("cli.worker.event_abandoned", run=details.get("run"))
    if event == "report_failed":
        return t("cli.worker.event_report_failed", reason=details.get("reason"))
    if event == "rejected":
        return t("cli.worker.event_rejected", message=details.get("message"))
    return None


def _read_token(token_file: Path | None) -> str | None:
    """權杖檔或環境變數裡的權杖；都沒有時回傳 None。"""
    if token_file is not None:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise click.ClickException(
                t("cli.worker.token_file_failed", path=token_file, error=error.strerror or error)
            ) from None
        if not token:
            raise click.ClickException(t("cli.worker.no_token", env=TOKEN_ENV))
        return token
    return os.environ.get(TOKEN_ENV, "").strip() or None


def _pair(invite_text: str, server: str | None, work: Path) -> tuple[str, str]:
    """用邀請換權杖並存進工作資料夾；回傳 (伺服器網址, 權杖)。"""
    from rpa_worker.pairing import PAIRING_FILE, InviteError, pair, parse_invite, save_pairing
    from rpa_worker.remote import ConnectionLostError, WorkerApiError

    try:
        invite = parse_invite(invite_text, server)
    except InviteError as error:
        raise click.ClickException(t("cli.worker.invite_" + error.reason)) from None
    try:
        result = pair(invite, "worker")
    except WorkerApiError as error:
        raise click.ClickException(t("cli.worker.pair_rejected", message=error.message)) from None
    except ConnectionLostError as error:
        raise click.ClickException(
            t("cli.worker.pair_offline", server=invite.server, reason=error)
        ) from None
    path = work / PAIRING_FILE
    save_pairing(path, result)
    click.echo(t("cli.worker.paired", name=result.name, device=result.device, path=path), err=True)
    return result.server, result.token


def resolve_credentials(
    server: str | None, token_file: Path | None, invite: str | None, work: Path
) -> tuple[str, str]:
    """決定連哪個管理 Portal、用哪個權杖：邀請 → 權杖檔或環境變數 → 之前配對存下的。"""
    from rpa_worker.pairing import PAIRING_FILE, load_pairing, normalize_server

    if invite is not None:
        return _pair(invite, server, work)
    token = _read_token(token_file)
    saved = load_pairing(work / PAIRING_FILE)
    if saved is not None:
        token = token or saved[1]
        server = server or saved[0]
    if token is None:
        raise click.ClickException(t("cli.worker.no_token", env=TOKEN_ENV))
    if not server:
        raise click.ClickException(t("cli.worker.no_server"))
    try:
        return normalize_server(server), token
    except ValueError:
        raise click.ClickException(t("cli.worker.invite_server")) from None


def build_worker_command() -> click.Command:
    """依目前語言建立 `rpa worker`。"""

    @click.command(
        name="worker",
        help=t("cli.worker.help", env=TOKEN_ENV),
        short_help=t("cli.worker.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.option("--server", default=None, metavar="URL", help=t("cli.worker.server_help"))
    @click.option(
        "--invite",
        default=None,
        metavar=t("cli.worker.invite_metavar"),
        help=t("cli.worker.invite_help"),
    )
    @click.option(
        "--token-file",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help=t("cli.worker.token_file_help", env=TOKEN_ENV),
    )
    @click.option("--name", default=None, help=t("cli.worker.name_help"))
    @click.option(
        "--work-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=DEFAULT_WORK_DIR,
        show_default=True,
        help=t("cli.worker.work_dir_help"),
    )
    @click.option("--keep-runs", is_flag=True, help=t("cli.worker.keep_runs_help"))
    @click.option(
        "--testsite/--no-testsite",
        default=True,
        help=t("cli.worker.testsite_help", port=TESTSITE_PORT),
    )
    def worker(
        server: str | None,
        invite: str | None,
        token_file: Path | None,
        name: str | None,
        work_dir: Path,
        keep_runs: bool,
        testsite: bool,
    ) -> None:
        work = work_dir.expanduser().absolute()
        server, token = resolve_credentials(server, token_file, invite, work)
        work.mkdir(parents=True, exist_ok=True)
        # 只有真的啟動 worker 時才載入 Playwright 與 runner
        from rpa_runner.installed import missing_browsers
        from rpa_worker.environment import WorkerInfo
        from rpa_worker.remote import WorkerClient
        from rpa_worker.service import run_remote_worker

        info = WorkerInfo.detect(name or socket.gethostname())
        stopped = threading.Event()

        def notify(event: str, details: Mapping[str, object]) -> None:
            line = describe_event(event, details)
            if line is not None:
                click.echo(line, err=True)

        site = None
        if testsite:
            site, message = start_testsite()
            click.echo(message, err=True)
        warning = browser_warning(missing_browsers())
        if warning is not None:
            click.echo(warning, err=True)
        if not info.display:
            click.echo(t("cli.worker.no_display"), err=True)
        click.echo(t("cli.worker.started", name=info.name, server=server, work=work), err=True)
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: stopped.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda signum, frame: stopped.set())
        try:
            fatal = run_remote_worker(
                WorkerClient(server, token),
                info,
                work,
                stop=stopped,
                notify=notify,
                keep_runs=keep_runs,
                on_stopping=lambda: click.echo(t("cli.worker.stopping"), err=True),
            )
        finally:
            signal.signal(signal.SIGINT, previous)
            if site is not None:
                site.shutdown()
                site.server_close()
        if fatal is not None:
            raise click.ClickException(t("cli.worker.rejected", message=fatal))

    return worker
