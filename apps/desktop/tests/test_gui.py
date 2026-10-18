"""視窗版的接線（rpa_desktop.gui、rpa_desktop.tray）：不開真的視窗，換成記錄呼叫的替身。

真的視窗與通知區圖示在 CI 的 Windows 上以打包版的 ``--smoke-test`` 打開。
"""

import sys
import threading
import types
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import pytest

from rpa_desktop import gui
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import Services, WorkerController
from rpa_desktop.credentials import Credentials, MemoryStore
from rpa_desktop.gui import Api, DesktopApp
from rpa_desktop.single_instance import InstanceLock
from rpa_desktop.tray import Tray


def _unused(*args: object, **kwargs: object) -> object:
    raise AssertionError("不應該被呼叫")


def controller(tmp_path: Path) -> WorkerController:
    services = Services(
        pair=_unused,  # type: ignore[arg-type]
        missing=_unused,  # type: ignore[arg-type]
        download=_unused,  # type: ignore[arg-type]
        run=_unused,  # type: ignore[arg-type]
        testsite=_unused,  # type: ignore[arg-type]
        detect=_unused,  # type: ignore[arg-type]
    )
    return WorkerController(
        home=tmp_path,
        build=BuildInfo(app="worker", version="0.2.0", fingerprint="fp", protocol=1),
        environ={},
        credentials=Credentials(tmp_path, MemoryStore()),
        autostart=AutoStart(None, Path("x")),
        services=services,
    )


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.scripts: list[str] = []
        self.html: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def hide(self) -> None:
        self.calls.append("hide")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")

    def evaluate_js(self, script: str) -> object:
        self.scripts.append(script)
        return None

    def load_html(self, content: str) -> None:
        self.html.append(content)

    def set_title(self, title: str) -> None:
        self.calls.append(f"title:{title}")


class FakeTray(Tray):
    def __init__(self, worker: WorkerController) -> None:
        super().__init__(worker, on_open=lambda: None, on_quit=lambda: None)
        self.notes: list[tuple[str, str]] = []
        self.updates = 0

    def notify(self, title: str, message: str) -> None:
        self.notes.append((title, message))

    def update(self) -> None:
        self.updates += 1


def app(tmp_path: Path, *, background: bool = False) -> tuple[DesktopApp, FakeWindow, FakeTray]:
    worker = controller(tmp_path)
    desktop = DesktopApp(worker, InstanceLock(tmp_path), background=background)
    window = FakeWindow()
    tray = FakeTray(worker)
    desktop.window = window  # type: ignore[assignment]
    desktop.tray = tray
    return desktop, window, tray


def wait_for(condition: Callable[[], bool]) -> None:
    ticker = threading.Event()
    for _ in range(500):
        if condition():
            return
        ticker.wait(0.01)
    assert condition()


def test_closing_hides_to_the_tray_with_a_hint_once(tmp_path: Path) -> None:
    desktop, window, tray = app(tmp_path)
    assert desktop._on_closing() is False  # pyright: ignore[reportPrivateUsage]
    wait_for(lambda: "hide" in window.calls)
    wait_for(lambda: len(tray.notes) == 1)
    assert "仍在執行" in tray.notes[0][0]
    assert desktop._on_closing() is False  # pyright: ignore[reportPrivateUsage]
    wait_for(lambda: window.calls.count("hide") == 2)
    assert len(tray.notes) == 1  # 只提示一次


def test_quit_really_closes(tmp_path: Path) -> None:
    desktop, window, _ = app(tmp_path)
    desktop.request_quit()
    assert window.calls == ["destroy"]
    assert desktop._on_closing() is True  # pyright: ignore[reportPrivateUsage]


def test_quit_while_running_asks_in_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop, window, _ = app(tmp_path)
    monkeypatch.setattr(WorkerController, "busy", property(lambda self: True))
    desktop.request_quit()  # 例如從通知區選「結束」
    assert window.calls == ["show", "restore"]
    assert window.scripts == ["window.rpa && window.rpa.askQuit()"]
    desktop.request_quit(confirmed=True)  # 頁面裡按了確定
    assert window.calls[-1] == "destroy"


def test_shutdown_closes_without_hiding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desktop, window, _ = app(tmp_path)
    monkeypatch.setattr(gui, "system_shutting_down", lambda: True)
    assert desktop._on_closing() is True  # pyright: ignore[reportPrivateUsage]
    assert "hide" not in window.calls
    assert desktop._session_ending  # pyright: ignore[reportPrivateUsage]


def test_background_start_shows_the_window_when_not_paired(tmp_path: Path) -> None:
    desktop, window, tray = app(tmp_path, background=True)
    desktop.controller._phase = "unpaired"  # pyright: ignore[reportPrivateUsage]
    desktop._on_change()  # pyright: ignore[reportPrivateUsage]
    desktop._on_change()  # pyright: ignore[reportPrivateUsage]
    assert window.calls.count("show") == 1
    assert tray.updates == 2


def test_api_routes_settings_and_language(tmp_path: Path) -> None:
    desktop, window, _ = app(tmp_path)
    api = Api(desktop)
    assert api.state()["phase"] == "starting"
    api.set_setting("download_host", "http://mirror")
    assert desktop.controller.settings.download_host == "http://mirror"
    api.set_setting("firefox", True)
    assert desktop.controller.settings.firefox
    api.set_setting("language", "en")
    assert desktop.controller.settings.language == "en"
    assert window.html
    assert '<html lang="en">' in window.html[-1]
    assert "title:RPA Worker" in window.calls
    api.set_setting("language", "fr")  # 不認得的語言不理會
    assert desktop.controller.settings.language == "en"
    api.pause(True)
    assert desktop.controller.paused
    assert api.ready("Mozilla/5.0 Edg/141") is True
    assert not [name for name in vars(api) if not name.startswith("_")]  # 不公開內部物件給頁面


class _Item:
    def __init__(
        self,
        text: str,
        action: Callable[..., object] | None,
        checked: Callable[["_Item"], bool] | None = None,
        default: bool = False,
    ) -> None:
        self.text, self.action, self.checked = text, action, checked

    def run(self) -> None:
        assert self.action is not None
        self.action()


class _Menu:
    SEPARATOR = _Item("-", None)

    def __init__(self, *items: _Item) -> None:
        self.items = items


class _Icon:
    created: ClassVar[list["_Icon"]] = []

    def __init__(self, name: str, icon: object, title: str, menu: _Menu) -> None:
        self.icon, self.title, self.menu = icon, title, menu
        self.updated = False
        _Icon.created.append(self)

    def labels(self) -> list[str]:
        return [item.text for item in self.menu.items]

    def update_menu(self) -> None:
        self.updated = True


def test_tray_menu_follows_language_and_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = types.ModuleType("pystray")
    fake.Icon, fake.Menu, fake.MenuItem = _Icon, _Menu, _Item  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pystray", fake)

    worker = controller(tmp_path)
    opened: list[bool] = []
    quit_: list[bool] = []
    tray = Tray(worker, on_open=lambda: opened.append(True), on_quit=lambda: quit_.append(True))
    tray._create()  # pyright: ignore[reportPrivateUsage]
    icon = _Icon.created[-1]
    assert icon.labels() == ["開啟視窗", "暫停接任務", "-", "結束"]
    assert icon.title == "RPA Worker · 啟動中"

    items = icon.menu.items
    items[0].run()
    items[1].run()
    items[3].run()
    assert opened == [True]
    assert quit_ == [True]
    assert worker.paused
    checked = items[1].checked
    assert checked is not None
    assert checked(items[1]) is True

    worker.set_language("en")
    tray.update()
    assert icon.labels() == ["Open window", "Pause jobs", "-", "Quit"]
    assert icon.title.startswith("RPA Worker · ")
    assert icon.updated


def test_webview2_and_shutdown_checks_off_windows() -> None:
    if sys.platform == "win32":
        pytest.skip("Windows 上看真的登錄檔")
    assert gui.webview2_version() == "n/a"
    assert gui.system_shutting_down() is False
