"""沒有畫面的伺服器（例如沒有桌面的 Linux）：錄製、逐步調試、人工登入的入口變灰，提示改用錄製端。

測試的伺服器預設沒有畫面（Settings.display=False）；有畫面的情況另外建一個 app。
透過錄製端看頁面的情況在 test_recorder_api.py。
"""

from collections.abc import Iterator
from dataclasses import replace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from httpx2 import Client, Response

from rpa_server.config import Settings

JsonObject = dict[str, object]
HINT = 'class="disabled-hint" title="這台伺服器沒有畫面'


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def error(response: Response, status: int) -> JsonObject:
    data = body(response, status)["error"]
    assert isinstance(data, dict)
    return cast("JsonObject", data)


@pytest.fixture
def shown(settings: Settings) -> Iterator[Client]:
    """有畫面的伺服器；管理頁面聽 8080（rpa serve 會填入 portal_port）。"""
    from rpa_server.app import create_app

    with TestClient(create_app(replace(settings, display=True, portal_port=8080))) as client:
        yield client


def prepare(client: Client) -> None:
    body(client.post("/api/scenes/import"))
    body(client.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    body(client.patch("/api/scenes/ba-001", json={"domainId": "lab"}))
    role = {
        "id": "erp-clerk",
        "name": "ERP 職員",
        "loginUrl": "http://127.0.0.1:9/login",
        "checkUrl": "http://127.0.0.1:9/home",
        "check": "{ testId: current-user }",
    }
    body(client.post("/api/roles", json=role), 201)


def test_entries_are_greyed_out_without_a_display(client: Client) -> None:
    prepare(client)
    scene = client.get("/scenes/ba-001").text
    assert 'href="/scenes/ba-001/debug"' not in scene
    assert HINT in scene
    assert "請透過 RPA 錄製端打開管理 Portal" in scene
    card = client.get("/domains/lab").text
    assert 'href="/scenes/ba-001/debug"' not in card
    assert 'data-action="debug"' not in card
    assert HINT in card
    # 逐步調試頁照樣打得開（看說明、從這裡驗證），但不能開始
    debug = client.get("/scenes/ba-001/debug").text
    assert "不能在這裡逐步調試" in debug
    assert '<button class="button primary" type="submit" disabled>' in debug
    assert HINT in debug
    # 錄製頁照樣打得開（貼上錄製稿不需要畫面），只有「開始錄製」是灰的
    recording = client.get("/recording").text
    assert '<span class="disabled-hint" data-for="record" title="這台伺服器沒有畫面' in recording
    assert 'data-for="record" disabled>' in recording
    assert 'data-for="paste" hidden>' in recording
    roles = client.get("/roles").text
    assert HINT in roles
    assert 'data-action="login" data-role="erp-clerk" disabled>' in roles


def test_entries_are_links_with_a_display(shown: Client) -> None:
    prepare(shown)
    scene = shown.get("/scenes/ba-001").text
    assert 'href="/scenes/ba-001/debug"' in scene
    assert "disabled-hint" not in scene
    card = shown.get("/domains/lab").text
    assert 'href="/scenes/ba-001/debug" title=' in card
    debug = shown.get("/scenes/ba-001/debug").text
    assert '<button class="button primary" type="submit">' in debug
    assert "disabled-hint" not in debug
    recording = shown.get("/recording").text
    assert 'data-for="record">' in recording
    assert "disabled-hint" not in recording
    assert "disabled-hint" not in shown.get("/roles").text


def test_english_hint(client: Client) -> None:
    prepare(client)
    scene = client.get("/scenes/ba-001?lang=en").text
    assert 'title="This server has no display' in scene
    assert "RPA Recorder" in scene


def test_the_portal_itself_is_not_a_start_url(shown: Client) -> None:
    body(shown.post("/api/domains", json={"id": "lab", "name": "實驗"}), 201)
    target = {"sceneId": "rec-001", "new": True, "name": "錄製", "domainId": "lab"}
    # TestClient 的 Host 是 testserver（埠 80）；管理頁面 8080
    for url in ("http://testserver/", "http://127.0.0.1:8080/scenes", "http://localhost:8080"):
        refused = shown.post("/api/recordings", json={"target": target, "url": url})
        problem = error(refused, 422)
        assert problem["code"] == "recording_url_portal"
        assert "管理 Portal 自己的位址" in str(problem["message"])
        assert "http://127.0.0.1:8765/" in str(problem["message"])
    assert body(shown.get("/api/recordings"))["recordings"] == []
