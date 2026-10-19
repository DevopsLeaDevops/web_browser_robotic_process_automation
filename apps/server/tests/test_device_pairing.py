"""M10.1 裝置邀請與配對：產生邀請、Client API 的 /pair、代碼一次性與期限、App 種類、
停用與刪除、對外埠分流、worker 回報的 App 版本，以及「裝置」頁。不需要瀏覽器。

管理 API 打到管理頁面的埠；Client API 與 Worker API 打到對外埠（base_url 帶 :8081）。
真的 HTTP 配對（rpa_worker.pairing.pair）在 test_remote_worker_flow.py。
"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_server.app import create_app
from rpa_server.config import Settings, sqlite_url
from rpa_server.models import DeviceInvite
from rpa_server.services import Services
from rpa_worker.environment import PROTOCOL
from rpa_worker.pairing import CLIENT_API_PREFIX, INVITE_HOURS, Invite, parse_invite

JsonObject = dict[str, object]
WORKER_PORT = 8081
PAIR = f"{CLIENT_API_PREFIX}/pair"
HELLO = "/worker-api/v1/hello"
INFO: JsonObject = {"name": "WIN", "protocol": PROTOCOL, "fingerprint": "x", "version": "0.1.0"}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT, worker_host="192.168.1.10")


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    """打到對外埠的用戶端（伺服器已經由 client 啟動）。"""
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def invite(client: Client, worker_id: str = "win-01") -> Invite:
    reply = body(client.post(f"/api/workers/{worker_id}/invite"))
    data = cast("JsonObject", reply["invite"])
    parsed = parse_invite(str(data["line"]))
    assert parsed.server == data["server"]
    assert parsed.code == data["code"]
    assert parsed.app == data["app"] == "worker"
    return parsed


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def register(client: Client, worker_id: str = "win-01") -> str:
    created = body(client.post("/api/workers", json={"id": worker_id, "name": "Windows"}), 201)
    return str(created["token"])


def pair(remote: Client, code: str, app: str = "worker") -> Response:
    return remote.post(PAIR, json={"code": code, "app": app})


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_invite_pairs_once_and_replaces_the_token(
    app: FastAPI, client: Client, remote: Client
) -> None:
    old_token = register(client)
    assert body(remote.post(HELLO, json=INFO, headers=auth(old_token)))["worker"] == "win-01"

    reply = body(client.post("/api/workers/win-01/invite"))
    data = cast("JsonObject", reply["invite"])
    assert data["server"] == "http://192.168.1.10:8081"  # 綁定特定位址時用那個位址
    expires = datetime.fromisoformat(str(data["expiresAt"]))
    remaining = expires - datetime.now(expires.tzinfo)
    assert timedelta(hours=INVITE_HOURS - 1) < remaining <= timedelta(hours=INVITE_HOURS)
    code = parse_invite(str(data["line"])).code
    # 邀請產生的當下，舊權杖就失效
    assert error(remote.post(HELLO, json=INFO, headers=auth(old_token)), 401)["code"] == (
        "worker_unauthorized"
    )

    paired = body(pair(remote, code))
    assert paired["device"] == "win-01"
    assert paired["name"] == "Windows"
    assert paired["app"] == "worker"
    server = cast("JsonObject", paired["server"])
    assert server["protocol"] == PROTOCOL
    token = str(paired["token"])
    assert body(remote.post(HELLO, json=INFO, headers=auth(token)))["worker"] == "win-01"

    # 代碼只能用一次；資料庫只存雜湊
    assert error(pair(remote, code), 401)["code"] == "invite_invalid"
    with services(app).sessions() as session:
        stored = session.scalars(select(DeviceInvite.code_hash)).all()
    assert stored
    assert code not in stored


def test_wrong_app_keeps_the_code(client: Client, remote: Client) -> None:
    register(client)
    code = invite(client).code

    refused = error(pair(remote, code, "recorder"), 409)
    assert refused["code"] == "invite_wrong_app"
    assert "RPA Worker" in str(refused["message"])

    assert body(pair(remote, code))["device"] == "win-01"


def test_expired_and_replaced_invitations_are_refused(
    app: FastAPI, client: Client, remote: Client
) -> None:
    register(client)
    first = invite(client).code
    second = invite(client).code  # 重新邀請：之前沒用過的邀請作廢
    assert error(pair(remote, first), 401)["code"] == "invite_invalid"

    with services(app).sessions() as session:
        row = session.scalars(select(DeviceInvite)).one()
        row.expires_at = row.created_at - timedelta(seconds=1)
        session.commit()
    expired = error(pair(remote, second), 401)
    assert expired["code"] == "invite_expired"
    assert str(INVITE_HOURS) in str(expired["message"])
    assert error(pair(remote, "x" * 32), 401)["code"] == "invite_invalid"


def test_disabled_and_deleted_devices_cannot_pair(
    app: FastAPI, client: Client, remote: Client
) -> None:
    register(client)
    code = invite(client).code
    body(client.patch("/api/workers/win-01", json={"disabled": True}))

    assert error(pair(remote, code), 409)["code"] == "worker_disabled"
    assert error(client.post("/api/workers/win-01/invite"), 409)["code"] == "worker_disabled"

    body(client.patch("/api/workers/win-01", json={"disabled": False}))
    code = invite(client).code
    body(client.delete("/api/workers/win-01"))
    assert error(pair(remote, code), 401)["code"] == "invite_invalid"
    with services(app).sessions() as session:
        assert session.scalars(select(DeviceInvite)).all() == []


def test_pairing_is_only_on_the_external_port(client: Client, remote: Client) -> None:
    register(client)
    code = invite(client).code
    assert pair(client, code).status_code == 404  # 管理頁面的埠沒有 Client API
    # M10.2：對外埠上的管理頁面只給錄製端的權杖（沒有權杖 401）
    assert remote.post("/api/workers/win-01/invite").status_code == 401
    assert remote.get("/devices").status_code == 401
    assert remote.post(PAIR, json={"code": code, "app": "phone"}).status_code == 422
    assert body(pair(remote, code))["device"] == "win-01"


def test_invitations_need_the_external_port(tmp_path: Path) -> None:
    data = tmp_path / "plain"
    app = create_app(
        Settings(data_dir=data, database_url=sqlite_url(data / "rpa.db"), start_worker=False)
    )
    with TestClient(app) as client:
        register(client)
        refused = error(client.post("/api/workers/win-01/invite"), 409)
        assert refused["code"] == "invite_needs_port"
        assert "--worker-port" in str(refused["message"])
        page = client.get("/devices").text
        assert 'data-action="new-worker" disabled' in page
        assert 'data-action="invite-worker"' not in page


def test_device_page_and_reported_version(client: Client, remote: Client) -> None:
    register(client)
    token = str(body(pair(remote, invite(client).code))["token"])
    body(remote.post(HELLO, json=INFO, headers=auth(token)))
    assert body(client.get("/api/workers/win-01"))["version"] == "0.1.0"

    moved = client.get("/workers", follow_redirects=False)
    assert moved.status_code == 301
    assert moved.headers["location"] == "/devices"
    page = client.get("/devices").text
    assert "新增裝置" in page
    assert "App 0.1.0" in page
    assert 'data-action="invite-worker" data-kind="worker" data-worker="win-01"' in page
    assert 'data-action="rotate-worker"' not in page
    assert 'href="/devices"' in page
