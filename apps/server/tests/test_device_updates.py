"""裝置跟著伺服器的版本更新（ADR 0018）：/update 的回覆、下載、「自動更新裝置」、裝置頁。"""

import hashlib
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_server.config import Settings
from rpa_server.device_updates import DeviceUpdates
from rpa_server.services import Services
from rpa_server.updates import UPDATE_FILE
from rpa_update import ed25519
from rpa_update.manifest import Manifest, scan_tree, write_update
from rpa_update.runtime import Runtime
from rpa_worker.pairing import parse_invite

JsonObject = dict[str, object]
WORKER_PORT = 8081
SEED = bytes(range(32))
KEY = ed25519.public_key(SEED)
TARGET = "worker-windows-x64"
RUNTIME_ID = "0123456789abcdef"
SERVER = Runtime("server-linux-x64", "fedcba9876543210", (KEY,))


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=WORKER_PORT)


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    with TestClient(app, base_url=f"http://testserver:{WORKER_PORT}") as other:
        yield other


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def updates(app: FastAPI) -> DeviceUpdates:
    return cast("Services", app.state.services).device_updates


def make_update(folder: Path, *, seed: bytes = SEED) -> Path:
    """版本資料夾裡的 update.zip：0.6.0-0000002，給 Windows 的 Worker 與 Linux 的伺服器。"""
    source = folder / "source"
    (source / "app" / "rpa_core").mkdir(parents=True)
    (source / "app" / "rpa_core" / "__init__.py").write_text("VALUE = 2\n")
    files = scan_tree(source)
    manifest = Manifest(
        version="0.6.0",
        commit="0000002",
        built_at="2026-10-25T09:00:00+00:00",
        fingerprint="f" * 16,
        protocol=1,
        features=(),
        runtimes={TARGET: RUNTIME_ID, SERVER.target: SERVER.id},
        files=files,
    )
    release = folder / "releases" / "0.6.0-0000002"
    release.mkdir(parents=True)
    write_update(release / UPDATE_FILE, manifest, {n: source / n for n in files}, seed)
    return release


def report(**changes: object) -> JsonObject:
    values: JsonObject = {
        "app": "worker",
        "target": TARGET,
        "runtime": RUNTIME_ID,
        "release": "0.5.0-0000001",
        "version": "0.5.0",
    }
    values.update(changes)
    return values


@pytest.fixture
def offered(app: FastAPI, client: Client, tmp_path: Path) -> Path:
    """伺服器有更新檔（分發包、裝了 0.6.0-0000002）。"""
    del client  # 伺服器啟動了
    release = make_update(tmp_path)
    service = updates(app)
    service.release_dir = release
    service.runtime = SERVER
    return release


def test_without_update_file(app: FastAPI, client: Client) -> None:
    del client
    service = updates(app)
    assert service.offer("worker", "win-01", report()) == {"status": "unavailable"}
    assert service.summary() == {"auto": True, "packaged": False}
    assert service.file() is None


def test_offer_statuses(app: FastAPI, offered: Path) -> None:
    service = updates(app)
    zipped = offered / UPDATE_FILE
    reply = service.offer("worker", "win-01", report())
    assert reply == {
        "status": "available",
        "version": "0.6.0",
        "release": "0.6.0-0000002",
        "size": zipped.stat().st_size,
        "sha256": hashlib.sha256(zipped.read_bytes()).hexdigest(),
    }
    assert service.offer("worker", "win-01", report(release="0.6.0-0000002"))["status"] == (
        "current"
    )
    # 環境代號不同、或更新檔沒有這個目標：要完整的安裝包
    assert service.offer("worker", "win-01", report(runtime="0" * 16))["status"] == "full"
    other = report(app="recorder", target="recorder-macos-arm64")
    assert service.offer("recorder", "mac-01", other)["status"] == "full"
    assert service.offer("worker", "win-01", report(failed="0.6.0-0000002"))["status"] == "failed"
    service.set_auto(False)
    assert service.offer("worker", "win-01", report())["status"] == "off"
    assert service.report("worker", "win-01") == {
        "status": "off",
        "release": "0.5.0-0000001",
        "version": "0.5.0",
        "failed": None,
        "target": TARGET,
        "runtime": report()["runtime"],
        "needed": report()["runtime"],
        "at": pytest.approx(service.clock(), abs=60),
    }
    # 要完整的安裝包時，裝置頁說明環境代號哪裡不同；更新檔沒有這個目標時 needed 是 None
    service.offer("worker", "win-01", report(runtime="0" * 16))
    full = service.report("worker", "win-01") or {}
    assert (full["status"], full["runtime"], full["needed"]) == (
        "full",
        "0" * 16,
        report()["runtime"],
    )
    service.offer("recorder", "mac-01", other)
    missing = service.report("recorder", "mac-01") or {}
    assert (missing["status"], missing["needed"]) == ("full", None)
    assert service.report("worker", "other") is None
    summary = service.summary()
    assert summary["auto"] is False
    assert summary["release"] == "0.6.0-0000002"
    assert summary["targets"] == [SERVER.target, TARGET]


def test_untrusted_update_file_is_not_offered(app: FastAPI, client: Client, tmp_path: Path) -> None:
    del client
    service = updates(app)
    service.release_dir = make_update(tmp_path, seed=bytes(range(1, 33)))
    service.runtime = SERVER
    assert service.offer("worker", "win-01", report())["status"] == "unavailable"
    assert service.summary()["packaged"] is True


def test_report_must_name_the_device(app: FastAPI, offered: Path) -> None:
    del offered
    from rpa_server.errors import ServiceError

    with pytest.raises(ServiceError, match="app"):
        updates(app).offer("worker", "win-01", report(app="server"))


def test_worker_api(client: Client, remote: Client, offered: Path) -> None:
    created = body(client.post("/api/workers", json={"id": "win-01", "name": "Win"}), 201)
    token = str(created["token"])
    assert remote.post("/worker-api/v1/update", json=report()).status_code == 401
    reply = body(remote.post("/worker-api/v1/update", json=report(), headers=auth(token)))
    assert reply["status"] == "available"
    downloaded = remote.get("/worker-api/v1/update/file", headers=auth(token))
    assert downloaded.status_code == 200
    assert downloaded.content == (offered / UPDATE_FILE).read_bytes()
    assert remote.get("/worker-api/v1/update/file").status_code == 401
    # 管理頁面的埠沒有 Worker API
    assert client.post("/worker-api/v1/update", json=report(), headers=auth(token)).status_code == (
        404
    )
    page = client.get("/devices").text
    assert 'data-update="available"' in page
    assert "0.6.0-0000002" in page


def test_client_api_for_recorders(client: Client, remote: Client, offered: Path) -> None:
    del offered
    body(client.post("/api/recorders", json={"id": "mac-01", "name": "Mac"}), 201)
    invited = cast("JsonObject", body(client.post("/api/recorders/mac-01/invite"))["invite"])
    code = parse_invite(str(invited["line"])).code
    pairing = body(remote.post("/client-api/v1/pair", json={"code": code, "app": "recorder"}))
    token = str(pairing["token"])
    recorder = report(app="recorder", target="recorder-macos-arm64")
    reply = body(remote.post("/client-api/v1/update", json=recorder, headers=auth(token)))
    assert reply["status"] == "full"
    assert remote.get("/client-api/v1/update/file", headers=auth(token)).status_code == 200


def test_missing_file_is_404(client: Client, remote: Client) -> None:
    created = body(client.post("/api/workers", json={"id": "win-01", "name": "Win"}), 201)
    response = remote.get("/worker-api/v1/update/file", headers=auth(str(created["token"])))
    assert response.status_code == 404
    assert body(response, 404)["error"] == {
        "code": "update_unavailable",
        "message": "這台伺服器沒有可以給裝置下載的更新檔。",
    }


def test_auto_setting_api(client: Client) -> None:
    assert body(client.get("/api/settings/device-updates"))["auto"] is True
    assert body(client.put("/api/settings/device-updates", json={"auto": False}))["auto"] is False
    assert body(client.get("/api/settings/device-updates"))["auto"] is False
    page = client.get("/devices").text
    assert 'name="device-updates-auto"' in page
    assert 'name="device-updates-auto" checked' not in page


def test_detect_uses_the_release_folder(app: FastAPI, tmp_path: Path) -> None:
    sessions = cast("Services", app.state.services).sessions
    found = DeviceUpdates.detect(sessions, {"RPA_RELEASE_DIR": str(tmp_path)})
    assert found.release_dir == tmp_path
    assert DeviceUpdates.detect(sessions, {}).release_dir is None
