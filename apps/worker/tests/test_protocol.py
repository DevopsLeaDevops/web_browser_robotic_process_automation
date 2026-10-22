"""Worker API 的資料格式：任務的編碼與解碼、執行目錄的打包與安全解開、這台電腦的資訊（M9a）。"""

import zipfile
from pathlib import Path

import pytest

from rpa_runner.login import LoginSettings
from rpa_worker.environment import (
    PROTOCOL,
    WorkerInfo,
    code_fingerprint,
    has_display,
    package_version,
)
from rpa_worker.protocol import (
    ArtifactError,
    JobPayload,
    is_safe_path,
    pack_directory,
    unpack_directory,
)


def payload(**changes: object) -> JobPayload:
    values: dict[str, object] = {
        "run_id": "ba-001-20261013-010203-abcdef",
        "files": {"scenario.yaml": b"id: x\r\nname: y\n", "scripts/automation.py": b"print(1)\n"},
        "inputs": {"title": "甲", "quantity": 2},
        "engine": "firefox",
        "base_url": "http://127.0.0.1:8765/",
        "headless": False,
        "deadline_ms": 30_000,
        "locale": "en",
        "login": LoginSettings(
            role="clerk",
            state=Path("/server/data/roles/clerk/state.json"),
            check_url="http://127.0.0.1:8765/account",
            check={"testId": "who"},
            secrets=("CLERK_PASSWORD",),
            name="Clerk",
        ),
        "login_state": b'{"cookies": []}',
        "secrets": {"CLERK_PASSWORD": "s3cret"},
        "record_video": True,
    }
    values.update(changes)
    return JobPayload(**values)  # pyright: ignore[reportArgumentType]


def test_payload_round_trip_keeps_bytes_and_replaces_state_path(tmp_path: Path) -> None:
    original = payload()
    data = original.to_json()

    assert "state" not in data["login"]  # pyright: ignore[reportOperatorIssue]
    assert "/server/data" not in str(data)

    restored = JobPayload.from_json(data, state_path=tmp_path / "state.json")
    assert restored.files == original.files  # \r\n 照位元組保留
    assert restored.inputs == original.inputs
    assert (restored.engine, restored.base_url, restored.headless) == (
        "firefox",
        original.base_url,
        False,
    )
    assert restored.deadline_ms == 30_000
    assert restored.locale == "en"
    assert restored.login is not None
    assert restored.login.state == tmp_path / "state.json"
    assert restored.login.check == {"testId": "who"}
    assert restored.login.secrets == ("CLERK_PASSWORD",)
    assert restored.login_state == b'{"cookies": []}'
    assert restored.secrets == {"CLERK_PASSWORD": "s3cret"}
    assert restored.record_video is True


def test_payload_from_an_older_portal_does_not_record(tmp_path: Path) -> None:
    """舊版管理 Portal 不送 recordVideo：不錄（M12）。"""
    data = payload().to_json()
    del data["recordVideo"]

    assert JobPayload.from_json(data, state_path=tmp_path / "s.json").record_video is False


def test_payload_without_login(tmp_path: Path) -> None:
    data = payload(login=None, login_state=None, locale=None).to_json()

    restored = JobPayload.from_json(data, state_path=tmp_path / "state.json")

    assert restored.login is None
    assert restored.login_state is None
    assert restored.locale is None
    assert restored.headless is False


@pytest.mark.parametrize(
    "files",
    [
        {"../evil.py": "eA=="},
        {"/etc/passwd": "eA=="},
        {"a\\b.py": "eA=="},
        {".hidden": "eA=="},
        {"scenario.yaml": "not base64!"},
    ],
)
def test_payload_rejects_unsafe_files(tmp_path: Path, files: dict[str, str]) -> None:
    data = payload().to_json()
    data["files"] = {"scenario.yaml": "eA==", **files}

    with pytest.raises(ValueError, match=r"unsafe file name|base64|Invalid|Incorrect|Non-base64"):
        JobPayload.from_json(data, state_path=tmp_path / "s.json")


def test_payload_requires_scenario_file_and_safe_run_id(tmp_path: Path) -> None:
    data = payload().to_json()
    data["scenarioFile"] = "missing.yaml"
    with pytest.raises(ValueError, match="scenario file missing"):
        JobPayload.from_json(data, state_path=tmp_path / "s.json")

    data = payload().to_json()
    data["runId"] = "../x"
    with pytest.raises(ValueError, match="invalid runId"):
        JobPayload.from_json(data, state_path=tmp_path / "s.json")


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("result.json", True),
        ("scenario/scripts/a.py", True),
        ("trace.zip", True),
        ("../x", False),
        ("a/../x", False),
        ("", False),
        ("/abs", False),
        ("a//b", True),  # PurePosixPath 會合併成 a/b
        (".env", False),
        ("a b", False),
    ],
)
def test_safe_paths(name: str, safe: bool) -> None:
    assert is_safe_path(name) is safe


def test_pack_and_unpack_directory(tmp_path: Path) -> None:
    source = tmp_path / "run"
    (source / "scenario").mkdir(parents=True)
    (source / "result.json").write_text("{}", encoding="utf-8")
    (source / "scenario" / "scenario.yaml").write_bytes(b"id: x\r\n")
    archive = tmp_path / "run.zip"

    assert pack_directory(source, archive) == 2

    target = tmp_path / "out"
    names = unpack_directory(archive, target)
    assert names == ["result.json", "scenario/scenario.yaml"]
    assert (target / "scenario" / "scenario.yaml").read_bytes() == b"id: x\r\n"


@pytest.mark.parametrize("bad", ["../escape.txt", "/abs.txt", ".hidden"])
def test_unpack_rejects_unsafe_names_without_writing(tmp_path: Path, bad: str) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("result.json", "{}")
        handle.writestr(bad, "x")

    with pytest.raises(ArtifactError):
        unpack_directory(archive, tmp_path / "out")

    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "out" / "result.json").exists()


def test_unpack_rejects_non_zip_and_existing_files(tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(ArtifactError):
        unpack_directory(junk, tmp_path / "a")

    archive = tmp_path / "ok.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("result.json", "{}")
    occupied = tmp_path / "b"
    occupied.mkdir()
    (occupied / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ArtifactError):
        unpack_directory(archive, occupied)


def test_unpack_limits_file_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rpa_worker.protocol.MAX_ARTIFACT_FILES", 2)
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for index in range(3):
            handle.writestr(f"f{index}.txt", "x")

    with pytest.raises(ArtifactError):
        unpack_directory(archive, tmp_path / "out")


def test_has_display() -> None:
    assert has_display({}, "win32") is True
    assert has_display({}, "darwin") is True
    assert has_display({}, "linux") is False
    assert has_display({"DISPLAY": ":0"}, "linux") is True
    assert has_display({"WAYLAND_DISPLAY": "wayland-0"}, "linux") is True


def test_code_fingerprint_ignores_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf = tmp_path / "lf" / "pkg_fp"
    crlf = tmp_path / "crlf" / "pkg_fp"
    for folder, text in ((lf, b"x = 1\ny = 2\n"), (crlf, b"x = 1\r\ny = 2\r\n")):
        folder.mkdir(parents=True)
        (folder / "__init__.py").write_bytes(text)

    def fingerprint(root: Path) -> str:
        monkeypatch.syspath_prepend(str(root.parent))  # pyright: ignore[reportUnknownMemberType]
        import importlib
        import sys

        sys.modules.pop("pkg_fp", None)
        importlib.invalidate_caches()
        value = code_fingerprint(("pkg_fp",))
        sys.modules.pop("pkg_fp", None)
        return value

    first = fingerprint(lf)
    second = fingerprint(crlf)
    assert first == second
    assert len(first) == 16
    assert code_fingerprint() == code_fingerprint()


def test_worker_info_to_json() -> None:
    info = WorkerInfo(
        name="win-01",
        fingerprint="abc",
        os="Windows 11",
        python="3.13.1",
        host="WIN-01",
        browsers=("chromium",),
        display=True,
        version="0.1.0",
    )

    assert info.to_json() == {
        "name": "win-01",
        "protocol": PROTOCOL,
        "fingerprint": "abc",
        "os": "Windows 11",
        "python": "3.13.1",
        "host": "WIN-01",
        "browsers": ["chromium"],
        "display": True,
        "version": "0.1.0",
        # 看得懂的 DSL 擴充（M7a）：管理 Portal 交出用到 iframe 的場景之前比對
        "features": ["anyFrame", "frame", "page", "popup"],
    }


def test_worker_info_reports_the_package_version() -> None:
    assert WorkerInfo.detect("box").version == package_version() != ""
    assert package_version("no-such-distribution") == ""


def test_all_page_recordings_survive_worker_upload_archive(tmp_path: Path) -> None:
    source = tmp_path / "run"
    source.mkdir()
    expected = {
        "video.webm": b"main",
        "video-page-2.webm": b"popup",
        "video.json": b'{"version":2}',
    }
    for name, content in expected.items():
        (source / name).write_bytes(content)
    archive = tmp_path / "run.zip"
    assert pack_directory(source, archive) == len(expected)
    target = tmp_path / "unpacked"
    assert set(unpack_directory(archive, target)) == set(expected)
    assert {name: (target / name).read_bytes() for name in expected} == expected
