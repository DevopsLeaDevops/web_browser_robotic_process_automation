"""macOS 的 RPA Worker（rpa_desktop.macos）：選單列圖示、Dock、再次打開、登出、⌘Q 的判斷。

AppKit、Foundation、objc 換成記錄呼叫的替身，Linux 的 CI 也能測選單的內容、狀態與動作；
真的選單列圖示在 CI 的 macOS 上以打包版的 ``--smoke-test`` 打開。
"""

import subprocess
import sys
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from rpa_desktop import gui, macos
from rpa_desktop.autostart import AutoStart
from rpa_desktop.build_info import BuildInfo
from rpa_desktop.controller import Services, WorkerController
from rpa_desktop.credentials import Credentials, MemoryStore
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
        build=BuildInfo(app="worker", version="0.4.0", fingerprint="fp", protocol=1),
        environ={},
        credentials=Credentials(tmp_path, MemoryStore()),
        autostart=AutoStart(None, Path("x")),
        services=services,
    )


def wait_for(condition: Callable[[], bool]) -> None:
    ticker = threading.Event()
    for _ in range(500):
        if condition():
            return
        ticker.wait(0.01)
    assert condition()


# ---------------------------------------------------------------- AppKit 的替身


class _Alloc:
    """``Cls.alloc().init…()`` 的寫法。"""

    @classmethod
    def alloc(cls) -> Any:
        return cls()

    def init(self) -> Any:
        return self


class FakeObject(_Alloc):
    pass


class FakeImage(_Alloc):
    def initWithData_(self, data: bytes) -> "FakeImage":  # noqa: N802 - AppKit 的名稱
        self.data = data
        return self

    def setSize_(self, size: tuple[float, float]) -> None:  # noqa: N802
        self.size = size


class FakeMenuItem(_Alloc):
    separator = False

    def initWithTitle_action_keyEquivalent_(  # noqa: N802
        self, title: str, action: str, key: str
    ) -> "FakeMenuItem":
        self.title, self.action, self.key = title, action, key
        self.state = 0
        self.target: object = None
        return self

    @classmethod
    def separatorItem(cls) -> "FakeMenuItem":  # noqa: N802
        item = cls()
        item.separator = True
        return item

    def setTarget_(self, target: object) -> None:  # noqa: N802
        self.target = target

    def setState_(self, state: int) -> None:  # noqa: N802
        self.state = state


class FakeMenu(_Alloc):
    def init(self) -> "FakeMenu":
        self.items: list[FakeMenuItem] = []
        return self

    def setAutoenablesItems_(self, value: bool) -> None:  # noqa: N802
        self.autoenables = value

    def addItem_(self, item: FakeMenuItem) -> None:  # noqa: N802
        self.items.append(item)


class FakeButton:
    image: FakeImage | None = None
    tooltip = ""

    def setImage_(self, image: FakeImage) -> None:  # noqa: N802
        self.image = image

    def setToolTip_(self, text: str) -> None:  # noqa: N802
        self.tooltip = text


class FakeStatusItem:
    def __init__(self) -> None:
        self._button = FakeButton()
        self.menu: FakeMenu | None = None

    def button(self) -> FakeButton:
        return self._button

    def setMenu_(self, menu: FakeMenu) -> None:  # noqa: N802
        self.menu = menu


class FakeStatusBar:
    def __init__(self) -> None:
        self.items: list[FakeStatusItem] = []
        self.removed: list[FakeStatusItem] = []

    def statusItemWithLength_(self, length: float) -> FakeStatusItem:  # noqa: N802
        item = FakeStatusItem()
        self.items.append(item)
        return item

    def removeStatusItem_(self, item: FakeStatusItem) -> None:  # noqa: N802
        self.removed.append(item)


class FakeApp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self._delegate: object = None

    def setActivationPolicy_(self, policy: object) -> None:  # noqa: N802
        self.calls.append(("policy", policy))

    def activateIgnoringOtherApps_(self, flag: bool) -> None:  # noqa: N802
        self.calls.append(("activate", flag))

    def delegate(self) -> object:
        return self._delegate

    def setDelegate_(self, delegate: object) -> None:  # noqa: N802
        self.calls.append(("delegate", delegate))
        self._delegate = delegate


class FakeCenter:
    def __init__(self) -> None:
        self.observers: list[tuple[object, Callable[[object], None]]] = []

    def addObserverForName_object_queue_usingBlock_(  # noqa: N802
        self, name: object, sender: object, queue: object, block: Callable[[object], None]
    ) -> object:
        self.observers.append((name, block))
        return object()


class Fakes:
    def __init__(self) -> None:
        self.app = FakeApp()
        self.bar = FakeStatusBar()
        self.center = FakeCenter()
        self.added: list[tuple[type, list[Any]]] = []
        app, bar, center = self.app, self.bar, self.center

        appkit = types.ModuleType("AppKit")
        appkit.NSApplication = types.SimpleNamespace(sharedApplication=lambda: app)  # type: ignore[attr-defined]
        appkit.NSStatusBar = types.SimpleNamespace(systemStatusBar=lambda: bar)  # type: ignore[attr-defined]
        appkit.NSVariableStatusItemLength = -1  # type: ignore[attr-defined]
        appkit.NSMenu = FakeMenu  # type: ignore[attr-defined]
        appkit.NSMenuItem = FakeMenuItem  # type: ignore[attr-defined]
        appkit.NSImage = FakeImage  # type: ignore[attr-defined]
        appkit.NSApplicationActivationPolicyRegular = "regular"  # type: ignore[attr-defined]
        appkit.NSApplicationActivationPolicyAccessory = "accessory"  # type: ignore[attr-defined]
        appkit.NSWorkspaceWillPowerOffNotification = "power-off"  # type: ignore[attr-defined]
        workspace = types.SimpleNamespace(notificationCenter=lambda: center)
        appkit.NSWorkspace = types.SimpleNamespace(sharedWorkspace=lambda: workspace)  # type: ignore[attr-defined]
        self.appkit = appkit

        foundation = types.ModuleType("Foundation")
        foundation.NSObject = FakeObject  # type: ignore[attr-defined]
        foundation.NSData = types.SimpleNamespace(dataWithBytes_length_=lambda raw, size: raw)  # type: ignore[attr-defined]
        foundation.NSOperationQueue = types.SimpleNamespace(mainQueue=lambda: "main")  # type: ignore[attr-defined]
        self.foundation = foundation

        class NoSuchClassError(Exception):
            pass

        registered: dict[str, Any] = {}

        def look_up(name: str) -> Any:
            if name not in registered:
                raise NoSuchClassError(name)
            return registered[name]

        def selector(function: Callable[..., object], selector: bytes, signature: bytes) -> Any:
            return types.SimpleNamespace(function=function, name=selector, signature=signature)

        def add_methods(cls: type, methods: list[Any]) -> None:
            self.added.append((cls, methods))

        objc = types.ModuleType("objc")
        objc.nosuchclass_error = NoSuchClassError  # type: ignore[attr-defined]
        objc.lookUpClass = look_up  # type: ignore[attr-defined]
        objc.selector = selector  # type: ignore[attr-defined]
        objc.classAddMethods = add_methods  # type: ignore[attr-defined]
        self.objc = objc


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Iterator[Fakes]:
    replaced = Fakes()
    monkeypatch.setattr(macos, "_appkit", lambda: replaced.appkit)
    monkeypatch.setattr(macos, "_foundation", lambda: replaced.foundation)
    monkeypatch.setitem(sys.modules, "objc", replaced.objc)
    yield replaced
    macos._active.clear()  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------- 選單列圖示


def titles(menu: FakeMenu | None) -> list[str]:
    assert menu is not None
    return ["-" if item.separator else item.title for item in menu.items]


def test_menu_bar_shows_status_menu_and_follows_language(tmp_path: Path, fakes: Fakes) -> None:
    worker = controller(tmp_path)
    opened: list[bool] = []
    quit_: list[bool] = []
    menu_bar = macos.MenuBar(
        worker, on_open=lambda: opened.append(True), on_quit=lambda: quit_.append(True)
    )
    assert menu_bar.start().is_set()  # 在主執行緒：直接建立
    item = fakes.bar.items[0]
    assert titles(item.menu) == ["開啟視窗", "暫停接任務", "-", "結束"]
    assert item.button().tooltip == "RPA Worker · 啟動中"
    image = item.button().image
    assert image is not None
    assert image.size == (18.0, 18.0)
    assert image.data.startswith(b"\x89PNG")

    # 選單的 target 是同一個物件，三個動作各一個 selector
    assert item.menu is not None
    pause = item.menu.items[1]
    assert [entry.action for entry in item.menu.items if not entry.separator] == [
        "openWindow:",
        "togglePause:",
        "quit:",
    ]
    target = pause.target
    assert target is not None
    target.openWindow_(None)  # type: ignore[attr-defined]
    target.quit_(None)  # type: ignore[attr-defined]
    target.togglePause_(None)  # type: ignore[attr-defined]
    wait_for(lambda: opened == [True] and quit_ == [True] and worker.paused)

    # 暫停後打勾；換語言後選單換成英文
    menu_bar.update()
    assert item.menu is not None
    assert item.menu.items[1].state == 1
    worker.set_language("en")
    menu_bar.update()
    assert titles(item.menu) == ["Open window", "Pause jobs", "-", "Quit"]

    menu_bar.stop()
    assert fakes.bar.removed == [item]
    target.quit_(None)  # type: ignore[attr-defined]  # 移除之後按到也不做事
    assert quit_ == [True]


def test_menu_target_class_is_registered_once(tmp_path: Path, fakes: Fakes) -> None:
    first = macos._target()  # pyright: ignore[reportPrivateUsage]
    registered: Any = first.__class__
    fakes.objc.lookUpClass = lambda name: registered  # type: ignore[attr-defined]
    second = macos._target()  # pyright: ignore[reportPrivateUsage]
    assert type(second) is registered


def test_menu_bar_without_appkit_does_not_break(tmp_path: Path) -> None:
    """建立失敗（例如沒有 AppKit）只記日誌：接任務照常。"""
    menu_bar = macos.MenuBar(controller(tmp_path), on_open=lambda: None, on_quit=lambda: None)
    assert not menu_bar.start().is_set()
    menu_bar.update()
    menu_bar.stop()
    with pytest.raises(NotImplementedError):
        menu_bar.run_blocking()


def test_menu_bar_updates_from_other_threads_go_to_the_main_thread(
    tmp_path: Path, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued: list[Callable[[], object]] = []
    helper = types.ModuleType("PyObjCTools.AppHelper")
    helper.callAfter = queued.append  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PyObjCTools.AppHelper", helper)
    worker = controller(tmp_path)
    menu_bar = macos.MenuBar(worker, on_open=lambda: None, on_quit=lambda: None)
    menu_bar.start()
    worker.set_paused(True)
    runner = threading.Thread(target=menu_bar.update)
    runner.start()
    runner.join()
    assert len(queued) == 1  # 排到主執行緒，沒有在背景執行緒碰 AppKit
    queued[0]()
    menu = fakes.bar.items[0].menu
    assert menu is not None
    assert menu.items[1].state == 1


def test_make_tray_picks_the_menu_bar_on_macos(tmp_path: Path) -> None:
    worker = controller(tmp_path)
    mac = gui.make_tray(worker, on_open=lambda: None, on_quit=lambda: None, platform="darwin")
    windows = gui.make_tray(worker, on_open=lambda: None, on_quit=lambda: None, platform="win32")
    assert isinstance(mac, macos.MenuBar)
    assert isinstance(windows, Tray)


# ---------------------------------------------------------------- App 層級的事件


def test_dock_follows_the_window(fakes: Fakes) -> None:
    macos.set_dock_visible(False, platform="darwin")
    macos.set_dock_visible(True, platform="darwin")
    assert fakes.app.calls == [
        ("policy", "accessory"),
        ("policy", "regular"),
        ("activate", True),
    ]


def test_reopen_adds_the_handler_to_the_app_delegate(fakes: Fakes) -> None:
    class Delegate:
        pass

    delegate = Delegate()
    fakes.app._delegate = delegate  # pyright: ignore[reportPrivateUsage]
    shown = threading.Event()
    macos.on_reopen(shown.set, platform="darwin")
    [(cls, methods)] = fakes.added
    assert cls is Delegate
    assert methods[0].name == b"applicationShouldHandleReopen:hasVisibleWindows:"
    assert methods[0].signature == b"Z@:@Z"
    assert ("delegate", delegate) in fakes.app.calls  # 重新設定，AppKit 才看得到新方法
    assert methods[0].function(delegate, None, False) is True
    assert shown.wait(5)


def test_reopen_without_delegate_only_logs(fakes: Fakes) -> None:
    macos.on_reopen(lambda: None, platform="darwin")
    assert fakes.added == []


def test_power_off_calls_back(fakes: Fakes) -> None:
    called: list[bool] = []
    macos.on_power_off(lambda: called.append(True), platform="darwin")
    [(name, block)] = fakes.center.observers
    assert name == "power-off"
    block(object())
    assert called == [True]


def test_other_systems_do_nothing(fakes: Fakes) -> None:
    macos.set_dock_visible(False, platform="linux")
    macos.on_reopen(lambda: None, platform="win32")
    macos.on_power_off(lambda: None, platform="linux")
    assert fakes.app.calls == []
    assert fakes.center.observers == []
    assert macos.terminating(platform="win32") is False


def applicationShouldTerminate_() -> bool:  # noqa: N802 - 和 pywebview 的 App 委派同名
    return macos.terminating(platform="darwin")


def test_terminating_sees_the_app_asking_to_quit() -> None:
    assert applicationShouldTerminate_() is True
    assert macos.terminating(platform="darwin") is False


def test_terminating_from_another_thread_looks_at_the_main_thread() -> None:
    """pywebview 可能在另一個執行緒呼叫 closing 的處理：看的是主執行緒正在做什麼。"""
    answers: list[bool] = []
    asked = threading.Event()

    def worker() -> None:
        answers.append(macos.terminating(platform="darwin"))
        asked.set()

    def applicationShouldTerminate_() -> None:  # noqa: N802
        threading.Thread(target=worker).start()
        assert asked.wait(5)

    applicationShouldTerminate_()
    worker()
    assert answers == [True, False]


def test_applescript_strings_keep_chinese() -> None:
    text = macos._applescript('錄製 "A"\\B')  # pyright: ignore[reportPrivateUsage]
    assert text == '"錄製 \\"A\\"\\\\B"'


def test_notify_and_alert_off_macos_only_log(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("不應該執行 osascript")

    monkeypatch.setattr(subprocess, "run", no_run)
    macos.notify("標題", "內容", platform="linux")
    macos.alert("標題", "內容", platform="linux")


def test_notify_runs_osascript_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[list[str]] = []
    done = threading.Event()

    def fake_run(command: list[str], **kwargs: object) -> None:
        scripts.append(command)
        done.set()

    monkeypatch.setattr(subprocess, "run", fake_run)
    macos.notify("RPA Worker 仍在執行", "選單列", platform="darwin")
    assert done.wait(5)
    assert scripts[0][:2] == ["osascript", "-e"]
    assert scripts[0][2] == 'display notification "選單列" with title "RPA Worker 仍在執行"'
