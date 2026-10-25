import base64
import json
from pathlib import Path

import pytest

from rpa_update import build, ed25519, runtime
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


def test_make_runtime_and_trusted_keys() -> None:
    key = ed25519.public_key(bytes(range(32)))
    encoded = base64.b64encode(key).decode()
    assert build.trusted_keys({build.EXTRA_KEYS_ENV: f" {encoded},,{encoded}"}) == (key,)
    with pytest.raises(ed25519.InvalidKeyError):
        build.trusted_keys({build.EXTRA_KEYS_ENV: "AAAA"})
    info = build.make_runtime("server-linux-x64", distributions=["b==2", "a==1"], keys=[key])
    assert info.components["distributions"] == ["a==1", "b==2"]
    assert info.id == runtime_id(info.components)
    # 換了第三方套件：代號跟著換
    other = build.make_runtime("server-linux-x64", distributions=["a==1", "b==3"], keys=[key])
    assert other.id != info.id
    # 不同的目標也不同
    assert build.make_runtime("worker-windows-x64", distributions=["a==1", "b==2"]).id != info.id


def test_installed_distributions_skip_workspace_and_pip() -> None:
    found = build.installed_distributions()
    names = {item.split("==")[0] for item in found}
    assert "pydantic" in names
    assert not {name for name in names if name.startswith("rpa-")}
    assert "pip" not in names


def test_write_runtime_and_keygen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "dev.pem"
    assert build.main(["keygen", "--private", str(private)]) == 0
    public = capsys.readouterr().out.strip()
    seed = ed25519.private_from_pem(private.read_text())
    assert base64.b64decode(public) == ed25519.public_key(seed)

    output = tmp_path / "runtime.json"
    monkeypatch.setenv(build.EXTRA_KEYS_ENV, public)
    args = ["runtime", "--target", "server-linux-x64", "--output", str(output)]
    assert build.main([*args, "--component", "shell=6.22"]) == 0
    info = load_runtime(output)
    assert info is not None
    assert info.keys == (base64.b64decode(public),)
    assert info.components["shell"] == "6.22"
    assert f"runtime: server-linux-x64={info.id}" in capsys.readouterr().out
