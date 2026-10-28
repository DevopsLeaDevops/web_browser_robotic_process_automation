"""M7c 上傳檔案：檔案區（上傳、上限、下載）、建立執行前的檢查、場景附件、保留規則、頁面、
遠端 Worker 下載與 Agent API。

執行都停在入參階段（缺少 Secret），不需要瀏覽器；真的上傳到網頁在 rpa_runner 的 test_upload.py。
"""

import base64
import hashlib
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_core.dsl.features import FEATURES
from rpa_server.config import Settings
from rpa_server.domain import now
from rpa_server.services import Services
from rpa_server.uploads import UNUSED_HOURS, UploadLimits
from rpa_worker import Worker
from rpa_worker.environment import PROTOCOL

JsonObject = dict[str, object]
PORT = 8081
WORKER_API = "/worker-api/v1"
AGENT_API = "/agent-api/v1"
LOGO = b"\x89PNG\r\n\x1a\n-logo-"
ORDERS = "編號,數量\nA-1,2\n".encode()

# 缺少 Secret：執行停在入參階段，不會啟動瀏覽器；檔案在那之前已經準備好、記進入參
SCENE = """\
schemaVersion: 1
id: import-orders
name: 匯入訂單
secrets: [RPA_TEST_SECRET_NOT_SET]
inputs:
  orders: { type: file, accept: [.csv], maxSize: 1KB, description: 訂單檔 }
  photos: { type: file, multiple: true, accept: [image/*], default: [files/logo.png] }
browser:
  baseUrl: http://127.0.0.1:9
steps:
  - { id: open, action: goto, url: / }
  - { id: pick, action: upload, target: { label: 匯入 }, files: "{{ inputs.orders }}" }
  - { id: photo, action: upload, target: { label: 圖片 }, files: "{{ inputs.photos }}" }
"""


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return replace(settings, worker_port=PORT)


@pytest.fixture
def remote(app: FastAPI, client: Client) -> Iterator[Client]:
    """打到對外埠（Worker API、Agent API）的用戶端。"""
    with TestClient(app, base_url=f"http://testserver:{PORT}") as other:
        yield other


def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload(client: Client, name: str, data: bytes, media: str = "") -> JsonObject:
    headers = {"Content-Type": media} if media else {}
    return body(
        client.post("/api/files", params={"name": name}, content=data, headers=headers), 201
    )


def make_scene(client: Client) -> int:
    """建立場景、加上附件 logo.png，再存成 SCENE（預設值用到附件）；回傳最新版本號碼。"""
    body(client.post("/api/scenes", json={"id": "import-orders", "name": "暫名"}), 201)
    saved = body(
        client.put("/api/scenes/import-orders/attachments/logo.png?base=1", content=LOGO), 200
    )
    assert saved["number"] == 2
    files = {"scenario.yaml": SCENE}
    revision = body(
        client.post(
            "/api/scenes/import-orders/revisions", json={"baseRevision": 2, "files": files}
        ),
        201,
    )
    assert revision["number"] == 3
    return 3


def validate(client: Client, inputs: JsonObject, **options: object) -> Response:
    return client.post(
        "/api/scenes/import-orders/revisions/3/validate",
        json={"inputs": inputs, "headless": True, **options},
    )


def problems(response: Response) -> list[str]:
    """入參有問題時的「名稱：說明」。"""
    details = error(response, 422)
    assert details["code"] == "inputs_invalid"
    items = [cast("JsonObject", item) for item in cast("list[object]", details["problems"])]
    return [f"{item['name']}：{item['message']}" for item in items]


# ---------------------------------------------------------------- 檔案區


def test_upload_is_stored_once_and_limited(app: FastAPI, client: Client) -> None:
    created = upload(client, "../資料/十月 訂單.csv", ORDERS, "text/csv")
    assert created["name"] == "十月 訂單.csv"  # 去掉路徑
    assert (created["size"], created["sha256"]) == (len(ORDERS), sha(ORDERS))
    assert created["mediaType"] == "text/csv"
    file_id = str(created["file"])
    assert body(client.get(f"/api/files/{file_id}"))["deleted"] is False
    content = client.get(f"/api/files/{file_id}/content")
    assert content.content == ORDERS
    assert "attachment" in content.headers["content-disposition"]

    again = upload(client, "copy.csv", ORDERS)
    assert again["file"] != file_id
    assert again["mediaType"] == "text/csv"  # 沒給類型時依副檔名
    folder = services(app).uploads.folder
    assert [path.name for path in folder.rglob("*") if path.is_file()] == [sha(ORDERS)]

    services(app).uploads.limits = UploadLimits(max_file=16)
    too_large = client.post("/api/files", params={"name": "big.bin"}, content=b"x" * 17)
    assert error(too_large, 413)["code"] == "file_too_large"
    assert not list(folder.glob(".incoming-*"))
    assert error(client.get("/api/files/" + "0" * 32), 404)["code"] == "upload_not_found"


# ---------------------------------------------------------------- 建立執行前的檢查


def test_run_checks_file_inputs_and_keeps_the_server_view(app: FastAPI, client: Client) -> None:
    make_scene(client)
    orders = upload(client, "orders.csv", ORDERS)
    photo = upload(client, "商品.png", LOGO)

    missing = problems(validate(client, {}))
    assert [item.split("：")[0] for item in missing] == ["orders"], missing
    unknown = problems(validate(client, {"orders": {"file": "0" * 32, "name": "a.csv"}}))
    assert any("a.csv" in item for item in unknown), unknown
    wrong_type = problems(validate(client, {"orders": {"file": photo["file"]}}))
    assert any("商品.png" in item for item in wrong_type), wrong_type
    big = upload(client, "big.csv", b"x" * 2048)
    too_large = problems(validate(client, {"orders": {"file": big["file"]}}))
    assert any("1 KB" in item for item in too_large), too_large
    no_attachment = problems(
        validate(client, {"orders": {"file": orders["file"]}, "photos": ["files/none.png"]})
    )
    assert any("files/none.png" in item for item in no_attachment), no_attachment

    # 網頁看到的檔名用給的 name；大小與 sha256 以伺服器的為準（送來的不算數）
    given = {"file": orders["file"], "name": "十月訂單.csv", "size": 1, "sha256": "f" * 64}
    queued = body(validate(client, {"orders": given}), 202)
    assert cast("JsonObject", queued["input"])["orders"] == {
        "file": orders["file"],
        "name": "十月訂單.csv",
        "size": len(ORDERS),
        "sha256": sha(ORDERS),
    }
    row = services(app).uploads.get(str(orders["file"]))
    assert row is not None
    assert row.used_at is not None

    # 本機 worker 執行：上傳檔與附件都準備好，停在缺少 Secret
    assert cast("Worker", app.state.worker).run_once()
    run = body(client.get(f"/api/runs/{queued['id']}"))
    result = cast("JsonObject", run["result"])
    assert result["input"] == {
        "orders": {"name": "十月訂單.csv", "size": len(ORDERS), "sha256": sha(ORDERS)},
        "photos": [{"name": "logo.png", "size": len(LOGO), "sha256": sha(LOGO)}],
    }
    assert any("RPA_TEST_SECRET_NOT_SET" in item for item in cast("list[str]", result["problems"]))

    page = client.get(f"/runs/{queued['id']}").text
    assert 'id="run-file-inputs"' in page
    assert f'href="/api/files/{orders["file"]}/content"' in page
    assert "十月訂單.csv" in page
    assert "/api/scenes/import-orders/revisions/3/attachments/logo.png" in page


# ---------------------------------------------------------------- 場景附件


def test_attachments_travel_with_revisions(client: Client) -> None:
    make_scene(client)
    listed = body(client.get("/api/scenes/import-orders/revisions/3/attachments"))
    assert listed["attachments"] == [
        {"path": "files/logo.png", "name": "logo.png", "size": len(LOGO), "sha256": sha(LOGO)}
    ]
    download = client.get("/api/scenes/import-orders/revisions/3/attachments/logo.png")
    assert download.content == LOGO
    assert (
        error(client.get("/api/scenes/import-orders/revisions/1/attachments/logo.png"), 404)["code"]
        == "attachment_not_found"
    )

    bad = client.put("/api/scenes/import-orders/attachments/訂單.csv?base=3", content=b"x")
    assert error(bad, 422)["code"] == "attachment_name"

    # 預設值還在用的附件不能刪
    used = error(client.delete("/api/scenes/import-orders/attachments/logo.png?base=3"), 422)
    assert used["code"] == "revision_invalid"
    codes = [cast("JsonObject", item)["code"] for item in cast("list[object]", used["issues"])]
    assert codes == ["server.attachment_missing"]

    added = body(
        client.put("/api/scenes/import-orders/attachments/template.csv?base=3", content=ORDERS)
    )
    assert added["number"] == 4
    revisions = cast("list[JsonObject]", body(client.get("/api/scenes/import-orders"))["revisions"])
    hashes = {item["number"]: item["contentHash"] for item in revisions}
    assert hashes[4] != hashes[3]  # 附件算在場景雜湊裡
    removed = body(client.delete("/api/scenes/import-orders/attachments/template.csv?base=4"))
    assert removed["number"] == 5
    names = [
        item["name"]
        for item in cast(
            "list[JsonObject]",
            body(client.get("/api/scenes/import-orders/revisions/5/attachments"))["attachments"],
        )
    ]
    assert names == ["logo.png"]

    scene_page = client.get("/scenes/import-orders").text
    assert 'id="attachments"' in scene_page
    assert "files/logo.png" in scene_page
    assert "<code>photos</code>" in scene_page  # 用在哪個入參


def test_forms_offer_file_pickers(client: Client) -> None:
    make_scene(client)
    form = client.get("/scenes/import-orders/run?purpose=validation&revision=3").text
    assert 'data-file-input="orders"' in form
    assert 'accept=".csv"' in form
    assert '<option value="files/logo.png"' in form
    assert "<code>maxSize: 1KB</code>" in form
    assert "<code>multiple</code>" in form
    debug = client.get("/scenes/import-orders/debug").text
    assert 'data-file-input="photos"' in debug


# ---------------------------------------------------------------- 保留規則


def test_retention_keeps_used_and_pinned_files(app: FastAPI, client: Client) -> None:
    make_scene(client)
    uploads = services(app).uploads
    unused = str(upload(client, "unused.csv", b"1")["file"])
    old = str(upload(client, "old.csv", b"2")["file"])
    recent = str(upload(client, "recent.csv", b"3")["file"])
    pinned = str(upload(client, "pinned.csv", b"4")["file"])
    moment = now() + timedelta(hours=UNUSED_HOURS + 1)
    uploads.touch([{"file": old}], moment=moment - timedelta(days=uploads.limits.keep_days + 1))
    uploads.touch([{"file": recent}], moment=moment - timedelta(days=1))

    # 組合場景節點的固定值用到的上傳檔不刪（存檔時有問題也一樣算）
    definition = {
        "version": 2,
        "mode": "dag",
        "nodes": [
            {
                "id": "n1",
                "sceneId": "import-orders",
                "revision": 1,
                "inputs": {"orders": {"value": {"file": pinned, "name": "pinned.csv"}}},
            }
        ],
        "edges": [],
    }
    response = client.post("/api/workflows", json={"name": "固定檔案", "definition": definition})
    assert response.status_code == 201, response.text
    assert pinned in services(app)._pinned_uploads()  # pyright: ignore[reportPrivateUsage]

    deleted = uploads.sweep(moment)
    assert sorted(deleted) == sorted([unused, old])
    assert body(client.get(f"/api/files/{unused}"))["deleted"] is True
    assert error(client.get(f"/api/files/{old}/content"), 404)["code"] == "upload_not_found"
    assert client.get(f"/api/files/{pinned}/content").content == b"4"
    assert client.get(f"/api/files/{recent}/content").content == b"3"

    # 總量上限：從最久沒用的開始刪，固定的不刪
    uploads.limits = UploadLimits(max_total=1)
    later = moment + timedelta(days=2)
    assert uploads.sweep(later) == [recent]


# ---------------------------------------------------------------- 遠端 Worker


def test_remote_worker_downloads_only_its_files(
    app: FastAPI, client: Client, remote: Client
) -> None:
    make_scene(client)
    orders = upload(client, "orders.csv", ORDERS)
    other = upload(client, "other.csv", b"other")
    token = str(body(client.post("/api/workers", json={"id": "win-01"}), 201)["token"])
    headers = {"Authorization": f"Bearer {token}"}
    info = {
        "name": "WIN-01",
        "protocol": PROTOCOL,
        "fingerprint": "x",
        "os": "Windows 11",
        "browsers": ["chromium", "firefox"],
        "display": True,
    }

    # 舊的 App 看不懂上傳：留在佇列裡（只能遠端時標為失敗）
    body(remote.post(f"{WORKER_API}/hello", json={**info, "features": ["frame"]}, headers=headers))
    queued = body(validate(client, {"orders": {"file": orders["file"]}}, target="remote"), 202)
    response = remote.post(f"{WORKER_API}/claim", json={"waitSeconds": 0}, headers=headers)
    assert response.status_code == 204
    failed = body(client.get(f"/api/runs/{queued['id']}"))
    assert failed["status"] == "failed"
    assert "upload" in str(failed["error"])

    body(
        remote.post(
            f"{WORKER_API}/hello", json={**info, "features": sorted(FEATURES)}, headers=headers
        )
    )
    queued = body(validate(client, {"orders": {"file": orders["file"]}}, target="remote"), 202)
    job = body(remote.post(f"{WORKER_API}/claim", json={"waitSeconds": 0}, headers=headers))
    assert job["runId"] == queued["id"]
    assert job["inputFiles"] == [{"id": orders["file"], "size": len(ORDERS), "sha256": sha(ORDERS)}]
    assert (job["maxFileBytes"], job["maxRunBytes"]) == (None, None)  # 和預設相同時不送
    files = cast("dict[str, str]", job["files"])
    assert base64.b64decode(files["files/logo.png"]) == LOGO  # 附件跟著版本的檔案

    base = f"{WORKER_API}/runs/{queued['id']}/files"
    got = remote.get(f"{base}/{orders['file']}", headers=headers)
    assert got.status_code == 200
    assert got.content == ORDERS
    assert error(remote.get(f"{base}/{other['file']}", headers=headers), 404)["code"] == (
        "upload_not_found"
    )
    stranger = str(body(client.post("/api/workers", json={"id": "win-02"}), 201)["token"])
    refused = remote.get(
        f"{base}/{orders['file']}", headers={"Authorization": f"Bearer {stranger}"}
    )
    assert error(refused, 409)["code"] == "run_not_assigned"


# ---------------------------------------------------------------- Agent API


def test_agent_uploads_its_own_files(app: FastAPI, client: Client, remote: Client) -> None:
    make_scene(client)
    created = body(
        client.post(
            "/api/agents",
            json={
                "id": "agent-erp",
                "name": "ERP 助理",
                "policy": {"scopes": ["scenes:read", "scenes:write", "runs:validate", "runs:read"]},
            },
        ),
        201,
    )
    headers = {"Authorization": f"Bearer {created['key']}"}

    def post_file(name: str, data: bytes) -> Response:
        return remote.post(
            f"{AGENT_API}/files", params={"name": name}, content=data, headers=headers
        )

    assert error(post_file("a.csv", ORDERS), 403)["code"] == "scope_missing"
    scopes = ["scenes:read", "scenes:write", "files:write", "runs:validate", "runs:read"]
    body(client.patch("/api/agents/agent-erp", json={"policy": {"scopes": scopes}}))
    mine = body(post_file("agent.csv", ORDERS), 201)
    assert (
        body(remote.get(f"{AGENT_API}/files/{mine['file']}", headers=headers))["name"]
        == "agent.csv"
    )
    portal = upload(client, "portal.csv", ORDERS)
    assert (
        error(remote.get(f"{AGENT_API}/files/{portal['file']}", headers=headers), 404)["code"]
        == "upload_not_found"
    )

    url = f"{AGENT_API}/scenes/import-orders/revisions/3/validate"
    theirs = remote.post(
        url, json={"inputs": {"orders": {"file": portal["file"]}}}, headers=headers
    )
    assert error(theirs, 404)["code"] == "upload_not_found"
    queued = body(
        remote.post(url, json={"inputs": {"orders": {"file": mine["file"]}}}, headers=headers), 202
    )
    assert cast("JsonObject", queued["input"])["orders"] == {
        "file": mine["file"],
        "name": "agent.csv",
        "size": len(ORDERS),
        "sha256": sha(ORDERS),
    }

    saved = remote.put(
        f"{AGENT_API}/scenes/import-orders/attachments/template.csv",
        params={"base": 3},
        content=ORDERS,
        headers=headers,
    )
    assert body(saved, 201)["number"] == 4
    listed = body(
        remote.get(f"{AGENT_API}/scenes/import-orders/revisions/4/attachments", headers=headers)
    )
    paths = [
        cast("JsonObject", item)["path"] for item in cast("list[object]", listed["attachments"])
    ]
    assert paths == ["files/logo.png", "files/template.csv"]
