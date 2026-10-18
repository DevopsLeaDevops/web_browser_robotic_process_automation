"""`rpa recorder`：在這台電腦當錄製端（M10.2，ADR 0014）。

透過錄製端操作管理 Portal 時，錄製、逐步調試、人工登入的瀏覽器開在**這台**，錄製稿、截圖與
登入狀態傳回管理 Portal（執行場景仍在伺服器或 Worker）。RPA 錄製端 App 用的是同一套程式
（:mod:`rpa_worker.recorder`、:mod:`rpa_worker.gateway`），這個命令給有開發環境的人先用：

- 第一次用管理 Portal「裝置」頁產生的錄製端邀請配對（``--invite``）；權杖存在工作資料夾的
  ``pairing.json``（只有本人能讀寫），之後直接 ``rpa recorder`` 就能啟動。
- 在 127.0.0.1 的隨機埠開本機閘道，用預設瀏覽器打開；權杖只在閘道裡，網頁拿不到。
- 預設一起在 127.0.0.1:8765 啟動本機測試網站：錄製範例場景時連得到。
- Ctrl+C 停止：進行中的錄製、調試、人工登入會結束。
"""

import signal
import socket
import threading
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import click

from rpa_cli.i18n import t
from rpa_cli.serve import browser_warning, start_testsite
from rpa_cli.worker import pair_with_invite
from testsite.server import DEFAULT_PORT as TESTSITE_PORT

__all__ = ["DEFAULT_WORK_DIR", "build_recorder_command", "describe_event"]

DEFAULT_WORK_DIR: Final = Path("recorder-data")


_KINDS: Final = {
    "rpa_runner.record": "cli.recorder.kind_record",
    "rpa_runner.debug": "cli.recorder.kind_debug",
    "rpa_runner.login": "cli.recorder.kind_login",
}


def _kind(module: object) -> str:
    """管理 Portal 要這台執行的模組 → 給人看的名稱（錄製、逐步調試、人工登入）。"""
    key = _KINDS.get(str(module))
    return t(key) if key else t("cli.recorder.kind_other", module=module)


def describe_event(event: str, details: Mapping[str, object]) -> str | None:
    """錄製端的事件 → 給人看的一行；不需要顯示的回傳 None。"""
    if event == "online":
        lines = [t("cli.recorder.event_online", device=details.get("device"))]
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
    if event == "started":
        return t("cli.recorder.event_started", kind=_kind(details.get("module")))
    if event == "finished":
        return t(
            "cli.recorder.event_finished",
            kind=_kind(details.get("module")),
            code=details.get("exit"),
        )
    if event == "rejected":
        return t("cli.recorder.event_rejected", message=details.get("message"))
    return None


def resolve_pairing(server: str | None, invite: str | None, work: Path) -> tuple[str, str]:
    """邀請 → 之前配對存下的（``--server`` 可以換掉存下的網址）；回傳 (伺服器網址, 權杖)。

    錄製端的權杖只能用邀請換：不像 ``rpa worker`` 收環境變數或權杖檔。
    """
    from rpa_worker.pairing import PAIRING_FILE, load_pairing, normalize_server

    if invite is not None:
        return pair_with_invite(invite, server, work, "recorder")
    saved = load_pairing(work / PAIRING_FILE)
    if saved is None:
        raise click.ClickException(t("cli.recorder.no_pairing", path=work / PAIRING_FILE))
    if not server:
        return saved
    try:
        return normalize_server(server), saved[1]
    except ValueError:
        raise click.ClickException(t("cli.worker.invite_server")) from None


def build_recorder_command() -> click.Command:
    """依目前語言建立 `rpa recorder`。"""

    @click.command(
        name="recorder",
        help=t("cli.recorder.help"),
        short_help=t("cli.recorder.short_help"),
        options_metavar=t("cli.options_metavar"),
    )
    @click.option(
        "--invite",
        default=None,
        metavar=t("cli.worker.invite_metavar"),
        help=t("cli.recorder.invite_help"),
    )
    @click.option("--server", default=None, metavar="URL", help=t("cli.recorder.server_help"))
    @click.option("--name", default=None, help=t("cli.worker.name_help"))
    @click.option(
        "--work-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=DEFAULT_WORK_DIR,
        show_default=True,
        help=t("cli.recorder.work_dir_help"),
    )
    @click.option("--port", type=int, default=0, help=t("cli.recorder.port_help"))
    @click.option(
        "--open/--no-open", "open_browser", default=True, help=t("cli.recorder.open_help")
    )
    @click.option(
        "--testsite/--no-testsite",
        default=True,
        help=t("cli.worker.testsite_help", port=TESTSITE_PORT),
    )
    def recorder(
        invite: str | None,
        server: str | None,
        name: str | None,
        work_dir: Path,
        port: int,
        open_browser: bool,
        testsite: bool,
    ) -> None:
        work = work_dir.expanduser().absolute()
        server, token = resolve_pairing(server, invite, work)
        work.mkdir(parents=True, exist_ok=True)
        from rpa_runner.installed import missing_browsers
        from rpa_worker.environment import WorkerInfo
        from rpa_worker.gateway import Gateway
        from rpa_worker.pairing import CLIENT_API_PREFIX
        from rpa_worker.recorder import RecorderHost
        from rpa_worker.remote import WorkerClient

        info = WorkerInfo.detect(name or socket.gethostname())
        stopped = threading.Event()

        def notify(event: str, details: Mapping[str, object]) -> None:
            line = describe_event(event, details)
            if line is not None:
                click.echo(line, err=True)
            if event == "rejected":
                stopped.set()

        site = None
        if testsite:
            site, message = start_testsite()
            click.echo(message, err=True)
        warning = browser_warning(missing_browsers())
        if warning is not None:
            click.echo(warning, err=True)
        if not info.display:
            click.echo(t("cli.recorder.no_display"), err=True)
        host = RecorderHost(
            WorkerClient(server, token, prefix=CLIENT_API_PREFIX),
            info.to_json(),
            work / "sessions",
            notify=notify,
        )
        gateway = Gateway(server, lambda: token, port=port)
        gateway.start()
        url = gateway.login_url()
        click.echo(t("cli.recorder.started", name=info.name, server=server, url=url), err=True)
        if open_browser:
            webbrowser.open(url)
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda signum, frame: stopped.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda signum, frame: stopped.set())
        rejected: list[str | None] = []
        thread = threading.Thread(target=lambda: rejected.append(host.run(stopped)), daemon=True)
        thread.start()
        try:
            while not stopped.wait(0.5):
                pass
            click.echo(t("cli.recorder.stopping"), err=True)
            thread.join(timeout=30)
        finally:
            signal.signal(signal.SIGINT, previous)
            gateway.close()
            if site is not None:
                site.shutdown()
                site.server_close()
        if rejected and rejected[0] is not None:
            raise click.ClickException(t("cli.recorder.rejected", message=rejected[0]))

    return recorder
