"""這個網址是不是管理 Portal 自己：錄製的起始網址不能是 Portal。

2026-10-19 的人工驗收中，錄製的起始網址填了伺服器的對外埠（``http://伺服器:8081/``）。
錄製開的是全新的瀏覽器，沒有錄製端的權杖，對外埠只回 401（``recorder_unauthorized``），
錄不到任何東西。起始網址要填被測試的網站，所以在開始錄製前就擋下並說明。

判斷依據是操作者連到 Portal 用的位址（請求的 ``Host``；透過錄製端時，錄製端的閘道轉送的
``Host`` 就是它連的伺服器網址）與 Portal 自己的埠（管理頁面、對外埠、收到這個請求的埠）：

- 主機和 ``Host`` 相同（都是本機位址也算相同），而且埠是 Portal 的埠 → 是 Portal。
- 錄製的瀏覽器開在伺服器這台（不是透過錄製端）時，本機位址加上 Portal 的埠也是 Portal。

只用標準函式庫，沒有連線、沒有 DNS 查詢：判斷不了的（例如另一個網域名稱指到同一台）就放行。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

__all__ = ["LOOPBACK_HOSTS", "PortalAddress", "points_to_portal"]

LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
"""本機位址；彼此視為同一台。"""


@dataclass(frozen=True, slots=True)
class PortalAddress:
    """操作者連到管理 Portal 的位址。"""

    host: str
    """請求的 ``Host`` 標頭，例如 ``215.192.222.14:8081``、``127.0.0.1:8080``；沒有時是空字串。"""
    ports: frozenset[int]
    """Portal 自己的埠：管理頁面、對外埠、收到這個請求的埠。"""
    on_server: bool
    """錄製的瀏覽器開在伺服器這台（直接打開伺服器的 Portal，不是透過錄製端）。"""

    @classmethod
    def of(
        cls, host: str | None, ports: Iterable[int | None], *, on_server: bool
    ) -> "PortalAddress":
        return cls(
            host=(host or "").strip(),
            ports=frozenset(port for port in ports if port),
            on_server=on_server,
        )


def _host_port(netloc: str, scheme: str) -> tuple[str, int | None]:
    """``主機:埠`` 拆成小寫的主機與埠；沒寫埠時用 scheme 的預設埠，埠號不合法時是 None。"""
    parts = urlsplit(f"{scheme}://{netloc}")
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        return host, None
    if port is None:
        port = 443 if scheme == "https" else 80
    return host, port


def points_to_portal(url: str, portal: PortalAddress) -> bool:
    """``url`` 指向管理 Portal 自己（管理頁面或對外埠）時回傳 True。"""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        return False
    host, port = _host_port(parts.netloc, scheme)
    if not host or port is None:
        return False
    own_host, own_port = _host_port(portal.host, "http") if portal.host else ("", None)
    ports = set(portal.ports)
    if own_port is not None:
        ports.add(own_port)
    if port not in ports:
        return False
    same_host = host == own_host or (host in LOOPBACK_HOSTS and own_host in LOOPBACK_HOSTS)
    return same_host or (portal.on_server and host in LOOPBACK_HOSTS)
