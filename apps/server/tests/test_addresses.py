"""錄製的起始網址是不是管理 Portal 自己（rpa_server.addresses）。不需要資料庫與瀏覽器。"""

import pytest

from rpa_server.addresses import PortalAddress, points_to_portal

# 2026-10-19 的人工驗收：Linux 伺服器 215.192.222.14，管理頁面 8080，對外埠 8081
SERVER = "215.192.222.14"


def via_recorder(host: str = f"{SERVER}:8081") -> PortalAddress:
    """透過錄製端：閘道轉送的 Host 是錄製端連的伺服器網址，請求在對外埠收到。"""
    return PortalAddress.of(host, (8080, 8081, 8081), on_server=False)


def on_server(host: str = "127.0.0.1:8080") -> PortalAddress:
    """直接打開伺服器的 Portal（或經由 SSH 通道）：錄製的瀏覽器開在伺服器這台。"""
    return PortalAddress.of(host, (8080, 8081, 8080), on_server=True)


@pytest.mark.parametrize(
    "url",
    [
        f"http://{SERVER}:8081/",  # 使用者實際填的
        f"http://{SERVER}:8081/scenes?x=1",
        f"https://{SERVER}:8081",
        f"http://{SERVER}:8080/",  # 管理頁面（有人把它開放到 0.0.0.0 時連得到）
        f"  http://{SERVER.upper()}:8081/  ",
    ],
)
def test_the_server_address_seen_through_the_recorder_is_refused(url: str) -> None:
    assert points_to_portal(url, via_recorder())


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/",  # 錄製端自己的測試網站
        f"http://{SERVER}:8765/",  # 同一台主機的其他埠
        f"http://{SERVER}/",
        "https://erp.example.com:8081/",  # 別的主機，碰巧也用 8081
        "http://127.0.0.1:8080/",  # 錄製端那台的本機：不是伺服器
        "ftp://215.192.222.14:8081/",
        "http://215.192.222.14:99999/",  # 埠號不合法：交給一般的網址檢查
        "not a url",
    ],
)
def test_other_sites_are_allowed_through_the_recorder(url: str) -> None:
    assert not points_to_portal(url, via_recorder())


def test_a_recorder_paired_through_an_ssh_tunnel() -> None:
    # 錄製端用 SSH 通道連伺服器（http://127.0.0.1:8081）：本機的這些埠就是 Portal
    portal = via_recorder("127.0.0.1:8081")
    assert points_to_portal("http://localhost:8081/", portal)
    assert points_to_portal("http://127.0.0.1:8080/", portal)
    assert not points_to_portal("http://127.0.0.1:8765/", portal)


def test_on_the_server_its_own_loopback_ports_are_the_portal() -> None:
    portal = on_server()
    assert points_to_portal("http://127.0.0.1:8080/scenes", portal)
    assert points_to_portal("http://localhost:8081/", portal)
    assert points_to_portal("http://[::1]:8080/", portal)
    assert not points_to_portal("http://127.0.0.1:8765/", portal)
    # SSH 通道把伺服器的 8080 帶到自己電腦的 18080：瀏覽器送來的 Host 是 127.0.0.1:18080
    tunnel = on_server("127.0.0.1:18080")
    assert points_to_portal("http://127.0.0.1:18080/", tunnel)
    assert points_to_portal("http://127.0.0.1:8080/", tunnel)
    assert not points_to_portal("https://erp.example.com/", tunnel)


def test_missing_host_and_ports() -> None:
    portal = PortalAddress.of(None, (None, None), on_server=False)
    assert portal.host == ""
    assert portal.ports == frozenset()
    assert not points_to_portal("http://127.0.0.1:8080/", portal)
    # Host 沒有寫埠：用 http 的預設埠
    plain = PortalAddress.of("rpa.example.com", (), on_server=False)
    assert points_to_portal("http://rpa.example.com/", plain)
    assert not points_to_portal("http://rpa.example.com:8765/", plain)
