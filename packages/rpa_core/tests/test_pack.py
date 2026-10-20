"""領域資料夾的格式：讀取、校驗、發布門檻與寫入（M11）。"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from rpa_core.dsl import validate_file
from rpa_core.dsl.sources import scenario_digest
from rpa_core.i18n import use_locale
from rpa_core.pack import (
    PACK_FILE,
    PackManifest,
    PublishedRef,
    RevisionInfo,
    RoleDefinition,
    RunRef,
    SceneManifest,
    ServerRef,
    Verification,
    WorkerRef,
    dump_model,
    is_sensitive,
    read_pack,
    write_model,
)

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "scenarios" / "demo"
SERVER = ServerRef(id="3a9d0c1e", name="jia-mac")
AT = "2026-10-19T05:10:00-07:00"


@pytest.fixture(autouse=True)
def _zh_hant() -> Iterator[None]:
    with use_locale("zh-Hant"):
        yield


def add_revision(folder: Path, scene: str, number: int, source: Path) -> str:
    """把範例場景放成第 number 版，寫版本說明檔，回傳雜湊。"""
    target = folder / "scenes" / scene / "revisions" / str(number)
    if source.is_dir():
        shutil.copytree(source, target)
        scenario_file = target / "scenario.yaml"
    else:
        target.mkdir(parents=True)
        scenario_file = target / "scenario.yaml"
        shutil.copyfile(source, scenario_file)
    scenario = validate_file(scenario_file).scenario
    assert scenario is not None
    digest = scenario_digest(scenario_file, scenario)
    info = RevisionInfo(number=number, hash=digest, created_at=AT, by="甲", server=SERVER)
    write_model(target.with_name(f"{number}.yaml"), info)
    return digest


def verify(
    folder: Path, scene: str, number: int, digest: str | None, *, status: str = "passed", at: str
) -> str:
    run_id = f"{scene}-{at[:10].replace('-', '')}-{at[11:19].replace(':', '')}-a1b2c3"
    record = Verification.model_validate(
        {
            "revision": number,
            "hash": digest,
            "status": status,
            "startedAt": at,
            "finishedAt": at,
            "by": "乙",
            "server": {"id": "5f3a", "name": "yi-mac"},
            "worker": {"id": "local"},
            "engine": "firefox",
            "headless": True,
            "run": {"server": "5f3a", "id": run_id},
            "summary": {"steps": 3, "durationSeconds": 4.2},
        }
    )
    write_model(
        folder / "scenes" / scene / "verifications" / str(number) / f"{run_id}.yaml", record
    )
    return run_id


def make_pack(tmp_path: Path) -> Path:
    folder = tmp_path / "testsite"
    write_model(
        folder / PACK_FILE,
        PackManifest(spec_version=1, id="testsite", name="測試網站自動化"),
    )
    write_model(folder / "scenes" / "ba-001" / "scene.yaml", SceneManifest(id="ba-001"))
    add_revision(folder, "ba-001", 1, DEMO / "ba-001.yaml")
    return folder


def publish(folder: Path, scene: str, number: int, verification: str | None) -> None:
    published = PublishedRef(
        revision=number, verification=verification, at=AT, by="丙", server=SERVER
    )
    write_model(
        folder / "scenes" / scene / "scene.yaml", SceneManifest(id=scene, published=published)
    )


def codes(folder: Path) -> list[str]:
    return [issue.code for issue in read_pack(folder).issues]


def test_valid_pack_with_published_revision(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    digest = add_revision(folder, "ba-001", 2, DEMO / "ba-001.yaml")
    proof = verify(folder, "ba-001", 2, digest, at="2026-10-19T06:15:00-07:00")
    publish(folder, "ba-001", 2, proof)

    pack = read_pack(folder, expected_id="testsite")

    assert pack.ok, pack.issues
    assert pack.manifest is not None
    assert pack.manifest.name == "測試網站自動化"
    scene = pack.scenes["ba-001"]
    assert scene.latest == 2
    assert scene.published == 2
    assert scene.revisions[1].status == "draft"
    assert scene.revisions[2].status == "passed"
    assert [entry.id for entry in scene.revisions[2].proofs()] == [proof]
    assert scene.revisions[2].digest == digest


def test_script_scenario_revision(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    write_model(
        folder / "scenes" / "ba-001-script" / "scene.yaml", SceneManifest(id="ba-001-script")
    )
    add_revision(folder, "ba-001-script", 1, DEMO / "ba-001-script")

    pack = read_pack(folder)

    assert pack.ok, pack.issues
    revision = pack.scenes["ba-001-script"].revisions[1]
    assert revision.kind == "script"
    assert revision.usable


def test_changed_revision_cannot_be_published(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    proof = verify(folder, "ba-001", 1, read_hash(folder), at="2026-10-19T06:15:00-07:00")
    publish(folder, "ba-001", 1, proof)
    scenario = folder / "scenes" / "ba-001" / "revisions" / "1" / "scenario.yaml"
    scenario.write_text(scenario.read_text(encoding="utf-8") + "# 改過\n", encoding="utf-8")

    pack = read_pack(folder)

    revision = pack.scenes["ba-001"].revisions[1]
    assert revision.problem == "pack.revision_hash_mismatch"
    assert not revision.usable
    assert pack.scenes["ba-001"].published is None
    assert "pack.published_changed" in [issue.code for issue in pack.issues]
    assert not pack.ok


def read_hash(folder: Path) -> str:
    pack = read_pack(folder)
    info = pack.scenes["ba-001"].revisions[1].info
    assert info is not None
    return info.hash


def test_published_without_matching_proof_is_not_published(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    failed = verify(
        folder, "ba-001", 1, read_hash(folder), status="failed", at="2026-10-19T06:15:00-07:00"
    )
    verify(folder, "ba-001", 1, "0" * 64, at="2026-10-19T06:20:00-07:00")
    publish(folder, "ba-001", 1, failed)

    pack = read_pack(folder)

    scene = pack.scenes["ba-001"]
    assert scene.published is None
    # 最近一次是通過，但雜湊和版本不符：算失敗
    assert scene.revisions[1].status == "failed"
    issue = next(issue for issue in pack.issues if issue.code == "pack.published_unverified")
    assert issue.path == "scenes/ba-001/scene.yaml"
    assert issue.message == (
        "發布的第 1 版沒有雜湊相符的通過驗證紀錄；不當成已發布，請驗證後再發布"
    )


def test_any_passed_record_is_enough_and_latest_decides_status(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    digest = read_hash(folder)
    proof = verify(folder, "ba-001", 1, digest, at="2026-10-19T06:15:00-07:00")
    # 另一台後來驗證失敗：狀態是失敗，但仍然可以依前一份通過的紀錄發布（第 8 節）
    verify(folder, "ba-001", 1, digest, status="failed", at="2026-10-19T15:16:00+01:00")
    publish(folder, "ba-001", 1, proof)

    scene = read_pack(folder).scenes["ba-001"]

    assert scene.revisions[1].status == "failed"
    assert scene.published == 1


def test_missing_manifest_and_wrong_id(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    assert read_pack(folder, expected_id="scm_purchase").manifest is None
    (folder / PACK_FILE).unlink()

    pack = read_pack(folder)

    assert pack.manifest is None
    assert [issue.code for issue in pack.issues] == ["pack.no_manifest"]
    # 場景照樣讀得到，Portal 依 manifest 決定要不要套用
    assert "ba-001" in pack.scenes


def test_unknown_spec_version(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    (folder / PACK_FILE).write_text("specVersion: 2\nid: testsite\nname: x\n", encoding="utf-8")

    pack = read_pack(folder)

    assert pack.manifest is None
    assert pack.issues[0].code == "pack.spec_version"


def test_invalid_files_report_lines_and_skip_items(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    scene = folder / "scenes" / "ba-002"
    scene.mkdir(parents=True)
    (scene / "scene.yaml").write_text("id: ba-002\narchivd: true\n", encoding="utf-8")
    info = folder / "scenes" / "ba-001" / "revisions" / "1.yaml"
    info.write_text(info.read_text(encoding="utf-8") + "extra: 1\n", encoding="utf-8")

    pack = read_pack(folder)

    issues = {issue.path: issue for issue in pack.issues}
    assert issues["scenes/ba-002/scene.yaml"].line == 2
    assert "archived" in issues["scenes/ba-002/scene.yaml"].message
    assert "ba-002" not in pack.scenes
    assert pack.scenes["ba-001"].revisions[1].problem == "pack.revision_info_invalid"


def test_scenario_issues_are_reported_with_the_revision(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    target = folder / "scenes" / "ba-001" / "revisions" / "2"
    target.mkdir()
    text = (
        (DEMO / "ba-001.yaml").read_text(encoding="utf-8").replace("action: click", "action: tap")
    )
    (target / "scenario.yaml").write_text(text, encoding="utf-8")

    pack = read_pack(folder)

    revision = pack.scenes["ba-001"].revisions[2]
    assert revision.problem == "pack.revision_no_info"
    found = [issue for issue in pack.issues if issue.path.endswith("2/scenario.yaml")]
    assert found[0].code == "pack.revision_invalid"
    assert found[1].line is not None
    assert pack.scenes["ba-001"].latest == 2
    assert pack.scenes["ba-001"].latest_usable() is pack.scenes["ba-001"].revisions[1]


def test_roles(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    good = RoleDefinition(
        id="testsite-user",
        name="測試網站：一般使用者",
        login_url="http://127.0.0.1:8765/login",
        check={"testId": "current-user"},
        engine="firefox",
        auto_login=(
            "- id: user\n  action: fill\n  target: { label: 帳號 }\n"
            '  value: "{{ secrets.TS_USER }}"\n'
        ),
    )
    write_model(folder / "roles" / "testsite-user.yaml", good)
    bad = good.model_copy(update={"id": "broken", "check": {"nope": 1}})
    write_model(folder / "roles" / "broken.yaml", bad)

    pack = read_pack(folder)

    assert list(pack.roles) == ["testsite-user"]
    assert pack.roles["testsite-user"].definition == good
    text = (folder / "roles" / "testsite-user.yaml").read_text(encoding="utf-8")
    assert "autoLogin: |\n  - id: user\n    action: fill\n" in text
    assert [issue.code for issue in pack.issues] == ["pack.role_check_invalid"]


def test_sensitive_files_are_errors(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    (folder / "roles").mkdir()
    (folder / "roles" / "state.json").write_text("{}", encoding="utf-8")
    (folder / ".git").mkdir()
    (folder / ".git" / "secrets.json").write_text("{}", encoding="utf-8")

    assert codes(folder) == ["pack.sensitive_file"]
    assert is_sensitive("secrets.local.json")
    assert is_sensitive(".env")
    assert is_sensitive("id_ed25519")
    assert not is_sensitive("id_ed25519.pub")
    assert not is_sensitive("scenario.yaml")


def test_dump_is_stable_and_round_trips(tmp_path: Path) -> None:
    manifest = SceneManifest(id="ba-001")
    assert dump_model(manifest) == "id: ba-001\narchived: false\npublished: null\n"

    record = Verification(
        revision=2,
        hash=None,
        status="failed",
        finished_at="2026-10-19T06:15:42-07:00",
        by="乙",
        server=ServerRef(id="5f3a", name="yi-mac"),
        worker=WorkerRef(id="win-01", os="windows"),
        run=RunRef(server="5f3a", id="ba-001-20261019-131500-a1b2c3"),
    )
    text = dump_model(record)
    assert "hash: null\n" in text
    assert "startedAt" not in text
    path = tmp_path / "record.yaml"
    write_model(path, record)
    assert path.read_text(encoding="utf-8") == text

    manifest_path = tmp_path / PACK_FILE
    pack = PackManifest.model_validate(
        {
            "specVersion": 1,
            "id": "e2e-procure",
            "name": "採購到驗收（跨領域）",
            "requires": [
                {"domain": "testsite", "source": {"repo": "git@example.com:a/b.git"}},
                {"domain": "scm_purchase"},
            ],
        }
    )
    write_model(manifest_path, pack)
    assert manifest_path.read_text(encoding="utf-8").splitlines()[:6] == [
        "specVersion: 1",
        "id: e2e-procure",
        'name: "採購到驗收（跨領域）"',
        "requires:",
        "  - domain: testsite",
        "    source:",
    ]


def test_timestamps_need_an_offset(tmp_path: Path) -> None:
    folder = make_pack(tmp_path)
    info = folder / "scenes" / "ba-001" / "revisions" / "1.yaml"
    info.write_text(
        info.read_text(encoding="utf-8").replace(AT, "2026-10-19T05:10:00"), encoding="utf-8"
    )

    issue = next(issue for issue in read_pack(folder).issues if issue.path.endswith("1.yaml"))

    assert issue.code == "format.timestamp"
    assert "UTC" in issue.message
