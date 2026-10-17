"""裝置邀請與配對（M10.1，ADR 0014）：邀請的格式，以及用邀請換權杖的 Client API。

管理 Portal 的「裝置」頁產生邀請；RPA Worker App 或 ``rpa worker --invite`` 用它換到權杖。
管理 Portal 與用戶端都用這裡的函式編碼與解碼，格式只寫在一個地方。

- 邀請是一行文字：``rpa://pair?server=http://192.168.1.10:8081&app=worker&code=…``。
  代碼一次性、24 小時內有效、限定 App 種類；管理 Portal 只存代碼的雜湊。
- 也接受只有代碼，伺服器網址另外填（:func:`parse_invite` 的 ``server``）。
- 配對：``POST /client-api/v1/pair``，只在對外埠提供。成功時回傳裝置代號、名稱與權杖；
  Worker 的權杖直接用在 Worker API。邀請的 App 種類不對時被拒絕（409 ``invite_wrong_app``）。
- 命令列（``rpa worker --invite``）把配對結果存在工作資料夾的 ``pairing.json``（只有本人能讀寫），
  之後不必再給權杖；桌面 App 改存在作業系統的認證管理員（M10.1 的 Worker App）。
"""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from rpa_worker.remote import WorkerClient

__all__ = [
    "APPS",
    "CLIENT_API_PREFIX",
    "INVITE_HOURS",
    "PAIRING_FILE",
    "App",
    "Invite",
    "InviteError",
    "PairResult",
    "load_pairing",
    "normalize_server",
    "pair",
    "parse_invite",
    "save_pairing",
]

CLIENT_API_PREFIX: Final = "/client-api/v1"
INVITE_SCHEME: Final = "rpa"
INVITE_HOURS: Final = 24
"""邀請產生後這麼多小時內有效。"""

PAIRING_FILE: Final = "pairing.json"
"""命令列 worker 在工作資料夾裡存配對結果的檔名。"""

App = Literal["worker", "recorder"]
APPS: Final[tuple[App, ...]] = ("worker", "recorder")

_CODE: Final = re.compile(r"^[A-Za-z0-9_-]{16,200}$")


class InviteError(ValueError):
    """邀請的格式不對。``reason`` 給呼叫端翻成使用者看得懂的訊息：

    ``empty``（沒有內容）、``format``（不是邀請也不是代碼）、``server``（缺少或不是有效的伺服器網址）、
    ``app``（不認得的 App 種類）。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize_server(server: str) -> str:
    """伺服器網址：沒寫 http:// 就補上，去掉結尾的斜線；只接受 http 與 https。"""
    value = server.strip().rstrip("/")
    if not value:
        raise InviteError("server")
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InviteError("server")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise InviteError("server")
    return f"{parts.scheme}://{parts.netloc}"


@dataclass(frozen=True, slots=True)
class Invite:
    """一份邀請：伺服器網址、代碼，以及限定的 App 種類（只貼代碼時不知道種類）。"""

    server: str
    code: str
    app: App | None = None

    def line(self) -> str:
        """一行文字的邀請，給使用者複製貼上。"""
        query: dict[str, str] = {"server": self.server}
        if self.app is not None:
            query["app"] = self.app
        query["code"] = self.code
        return f"{INVITE_SCHEME}://pair?{urlencode(query)}"


def parse_invite(text: str, server: str | None = None) -> Invite:
    """解析邀請：``rpa://pair?…`` 的一行，或只有代碼（這時要給 ``server``）。

    兩者都給時，邀請裡的伺服器網址優先：那是管理 Portal 產生邀請時看到的對外埠位址。
    """
    value = text.strip().strip("\"'")
    if not value:
        raise InviteError("empty")
    if value.lower().startswith(f"{INVITE_SCHEME}://"):
        parts = urlsplit(value)
        if parts.netloc.lower() != "pair" and parts.path.strip("/").lower() != "pair":
            raise InviteError("format")
        query = parse_qs(parts.query)

        def one(key: str) -> str | None:
            values = query.get(key)
            return values[0].strip() if values else None

        code = one("code") or ""
        if not _CODE.fullmatch(code):
            raise InviteError("format")
        app = one("app")
        if app is not None and app not in APPS:
            raise InviteError("app")
        address = one("server") or server
        if address is None:
            raise InviteError("server")
        return Invite(normalize_server(address), code, app)
    if not _CODE.fullmatch(value):
        raise InviteError("format")
    if server is None or not server.strip():
        raise InviteError("server")
    return Invite(normalize_server(server), value)


@dataclass(frozen=True, slots=True)
class PairResult:
    """配對成功：裝置代號、名稱、App 種類與權杖，以及管理 Portal 的版本資訊。"""

    server: str
    device: str
    name: str
    app: App
    token: str
    protocol: int | None
    fingerprint: str | None
    version: str | None


def pair(
    invite: Invite,
    app: App,
    info: Mapping[str, object] | None = None,
    *,
    timeout: float = 30.0,
) -> PairResult:
    """用邀請換權杖。

    管理 Portal 拒絕時拋出 :class:`rpa_worker.remote.WorkerApiError`（訊息已是使用者的語言），
    連不上時拋出 :class:`rpa_worker.remote.ConnectionLostError`。
    """
    client = WorkerClient(invite.server, None, prefix=CLIENT_API_PREFIX, timeout=timeout)
    payload: dict[str, object] = {"code": invite.code, "app": app}
    if info is not None:
        payload["info"] = dict(info)
    reply = client.call("POST", "/pair", payload)
    token = reply.get("token")
    device = reply.get("device")
    if not isinstance(token, str) or not token or not isinstance(device, str):
        raise ValueError("pairing reply without token or device")
    server = reply.get("server")
    details = cast("dict[str, object]", server) if isinstance(server, dict) else {}
    protocol = details.get("protocol")
    fingerprint = details.get("fingerprint")
    version = details.get("version")
    return PairResult(
        server=invite.server,
        device=device,
        name=str(reply.get("name") or device),
        app=app,
        token=token,
        protocol=protocol if isinstance(protocol, int) else None,
        fingerprint=str(fingerprint) if fingerprint else None,
        version=str(version) if version else None,
    )


def save_pairing(path: Path, result: PairResult) -> None:
    """把配對結果存成只有本人能讀寫的檔案（命令列 worker 用）。"""
    data = {
        "server": result.server,
        "device": result.device,
        "name": result.name,
        "token": result.token,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_pairing(path: Path) -> tuple[str, str] | None:
    """讀回配對結果：(伺服器網址, 權杖)；沒有檔案或內容不對時回傳 None。"""
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    values = cast("dict[str, object]", data)
    server, token = values.get("server"), values.get("token")
    if not isinstance(server, str) or not isinstance(token, str) or not server or not token:
        return None
    return server, token
