"""驗證通過與發布之間的空檔（2026-10-28，任務 20261028-main-ci-red）：不需要瀏覽器。

RunQueue.complete 先提交「通過」，之後才由 on_finished 把驗證紀錄寫進領域資料夾；發布看的是那份
紀錄。這段空檔裡打開運行頁或按發布，曾經看不到「發布」按鈕（Portal 測試等不到按鈕而逾時）或回
409 not_validated（每晚測試在 Windows 偶爾遇到）。測試用一個不做事的 on_finished 把空檔撐開。
"""

from collections.abc import Callable
from typing import cast

from fastapi import FastAPI
from httpx2 import Client, Response
from sqlalchemy import select

from rpa_server.jobs import Outcome
from rpa_server.models import Revision, Run
from rpa_server.services import Services

JsonObject = dict[str, object]


def body(response: Response, status: int = 200) -> JsonObject:
    assert response.status_code == status, response.text
    data: object = response.json()
    assert isinstance(data, dict)
    return cast("JsonObject", data)


def passed_but_not_recorded(app: FastAPI, client: Client) -> tuple[Services, str]:
    """BA-001 v1 的驗證已經提交「通過」，on_finished 還沒執行；回傳服務與執行編號。"""
    services = cast("Services", app.state.services)
    assert client.post("/api/scenes/import").status_code < 400
    queued = body(
        client.post(
            "/api/scenes/ba-001/revisions/1/validate",
            json={"inputs": {"title": "空檔", "quantity": 1}},
        ),
        202,
    )
    run_id = str(queued["id"])
    job = services.queue.claim()
    assert job is not None
    assert job.run_id == run_id
    with services.sessions() as session:
        revision = session.scalars(
            select(Revision).where(Revision.scene_id == "ba-001", Revision.number == 1)
        ).one()
        content_hash = revision.content_hash
    later: Callable[[str], None] = services.queue.on_finished
    services.queue.on_finished = lambda _: None
    try:
        assert services.queue.complete(run_id, Outcome("passed", scenario_hash=content_hash))
    finally:
        services.queue.on_finished = later
    assert body(client.get(f"/api/runs/{run_id}"))["status"] == "passed"
    assert body(client.get("/api/scenes/ba-001/revisions/1"))["verified"] is False
    return services, run_id


def verification_files(services: Services, run_id: str) -> list[str]:
    folder = services.packs.verification_path("ba-001", 1, run_id).parent
    return sorted(path.name for path in folder.glob("*.yaml"))


def test_publish_right_after_the_validation_passed(app: FastAPI, client: Client) -> None:
    services, run_id = passed_but_not_recorded(app, client)

    scene = body(client.post("/api/scenes/ba-001/revisions/1/publish"))

    assert scene["publishedRevision"] == 1
    assert verification_files(services, run_id) == [f"{run_id}.yaml"]
    # 之後 on_finished 照常寫一次：同一份紀錄，不會多出第二份
    services.run_finished(run_id)
    assert verification_files(services, run_id) == [f"{run_id}.yaml"]
    with services.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "passed"


def test_run_page_offers_publish_right_after_the_validation_passed(
    app: FastAPI, client: Client
) -> None:
    services, run_id = passed_but_not_recorded(app, client)

    page = client.get(f"/runs/{run_id}").text

    assert 'data-action="publish"' in page
    assert body(client.get("/api/scenes/ba-001/revisions/1"))["verified"] is True
    assert verification_files(services, run_id) == [f"{run_id}.yaml"]


def test_failed_validation_is_not_settled_into_a_proof(app: FastAPI, client: Client) -> None:
    services, run_id = passed_but_not_recorded(app, client)
    with services.sessions() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "failed"
        session.commit()

    assert services.packs.settle_verification(run_id) is True
    response = client.post("/api/scenes/ba-001/revisions/1/publish")

    assert response.status_code == 409
    error = cast("JsonObject", response.json()["error"])
    assert error["code"] == "not_validated"
