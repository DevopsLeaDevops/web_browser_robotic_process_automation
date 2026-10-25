import json
from pathlib import Path

import pytest

from rpa_update import runtime
from rpa_update.errors import UpdateError
from rpa_update.runtime import Runtime, load_runtime, platform_tag, runtime_id, source_digest


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("linux", "x86_64", "linux-x64"),
        ("linux", "aarch64", "linux-arm64"),
        ("win32", "AMD64", "windows-x64"),
        ("darwin", "arm64", "macos-arm64"),
    ],
)
def test_platform_tag(system: str, machine: str, expected: str) -> None:
    assert platform_tag(system, machine) == expected


def test_runtime_id_ignores_key_order() -> None:
    a = runtime_id({"python": "3.13", "packages": ["a==1"]})
    b = runtime_id({"packages": ["a==1"], "python": "3.13"})
    assert a == b
    assert len(a) == 16
    assert runtime_id({"python": "3.14", "packages": ["a==1"]}) != a


def test_source_digest_follows_code(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    (tmp_path / "runtime.json").write_text("{}")
    first = source_digest(tmp_path)
    (tmp_path / "runtime.json").write_text('{"id": "other"}')
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.py").write_text("ignored")
    assert source_digest(tmp_path) == first
    (tmp_path / "a.py").write_bytes(b"x = 1\r\n")  # Windows 的 git 轉成 CRLF：相同
    assert source_digest(tmp_path) == first
    (tmp_path / "a.py").write_bytes(b"x = 2\n")
    assert source_digest(tmp_path) != first


def test_source_digest_of_installed_package() -> None:
    assert source_digest() == source_digest(Path(runtime.__file__).parent)


def test_runtime_round_trip(tmp_path: Path) -> None:
    info = Runtime("server-linux-x64", "0123456789abcdef", (bytes(32),), {"python": "3.13"})
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(info.to_json()))
    assert load_runtime(path) == info


def test_load_runtime_missing_file(tmp_path: Path) -> None:
    assert load_runtime(tmp_path / "runtime.json") is None


def test_development_environment_has_no_runtime() -> None:
    assert load_runtime() is None


@pytest.mark.parametrize(
    "data",
    [
        "[]",
        '{"format": 2, "target": "x", "id": "y", "keys": []}',
        '{"format": 1, "target": "x", "id": "y", "keys": ["!!"]}',
        '{"format": 1, "target": "x", "id": "y", "keys": ["AAAA"]}',
        "not json",
    ],
)
def test_load_runtime_rejects_bad_file(tmp_path: Path, data: str) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(data)
    with pytest.raises(UpdateError, match="runtime_invalid"):
        load_runtime(path)
