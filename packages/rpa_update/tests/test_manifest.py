import json
import zipfile
from pathlib import Path

import pytest

from rpa_update import ed25519
from rpa_update.errors import UpdateError
from rpa_update.manifest import (
    MANIFEST,
    SIGNATURE,
    FileEntry,
    Manifest,
    UpdateFile,
    check_path,
    scan_tree,
    sign_manifest,
    verify_signature,
    verify_tree,
    write_update,
)

SEED = bytes(range(32))
KEY = ed25519.public_key(SEED)
OTHER_SEED = bytes(range(1, 33))


def _tree(root: Path) -> Path:
    (root / "app" / "rpa_core").mkdir(parents=True)
    (root / "app" / "rpa_core" / "__init__.py").write_text("VALUE = 1\n")
    (root / "app" / "rpa_core-0.6.0.dist-info").mkdir()
    (root / "app" / "rpa_core-0.6.0.dist-info" / "METADATA").write_text("Name: rpa-core\n")
    (root / "server" / "bin").mkdir(parents=True)
    script = root / "server" / "bin" / "rpa"
    script.write_text("#!/usr/bin/env bash\n")
    script.chmod(0o755)
    return root


def _manifest(files: dict[str, FileEntry], **changes: object) -> Manifest:
    values: dict[str, object] = {
        "version": "0.6.0",
        "commit": "1a2b3c4",
        "built_at": "2026-10-25T09:00:00+00:00",
        "fingerprint": "f" * 16,
        "protocol": 1,
        "features": ("frame",),
        "runtimes": {"server-linux-x64": "0" * 16},
        "files": files,
    }
    values.update(changes)
    return Manifest(**values)  # type: ignore[arg-type]


def _update(tmp_path: Path, seed: bytes = SEED) -> tuple[Path, Manifest]:
    source = _tree(tmp_path / "source")
    files = scan_tree(source)
    manifest = _manifest(files)
    path = tmp_path / "RPA-Update-0.6.0.zip"
    write_update(path, manifest, {name: source / name for name in files}, seed)
    return path, manifest


def test_manifest_round_trip() -> None:
    manifest = _manifest({"app/a.py": FileEntry("a" * 64, 3)})
    assert Manifest.from_bytes(manifest.to_bytes()) == manifest
    assert manifest.release == "0.6.0-1a2b3c4"
    assert _manifest({}, commit="").release == "0.6.0"


def test_manifest_keeps_unknown_fields() -> None:
    data = json.loads(_manifest({}).to_bytes())
    data["delta"] = {"from": "0.5.0"}
    manifest = Manifest.from_bytes(json.dumps(data).encode())
    assert manifest.extra == {"delta": {"from": "0.5.0"}}
    assert json.loads(manifest.to_bytes())["delta"] == {"from": "0.5.0"}


@pytest.mark.parametrize(
    "change",
    [
        {"format": 2},
        {"version": 6},
        {"protocol": True},
        {"features": "frame"},
        {"runtimes": {"server-linux-x64": 1}},
        {"files": {"app/a.py": {"sha256": "zz", "size": 1}}},
        {"files": {"app/a.py": {"sha256": "a" * 64, "size": -1}}},
        {"files": {"../a.py": {"sha256": "a" * 64, "size": 1}}},
        {
            "files": {
                "app/A.py": {"sha256": "a" * 64, "size": 1},
                "app/a.py": {"sha256": "a" * 64, "size": 1},
            }
        },
    ],
)
def test_manifest_rejects_bad_fields(change: dict[str, object]) -> None:
    data = json.loads(_manifest({}).to_bytes())
    data.update(change)
    with pytest.raises(UpdateError):
        Manifest.from_bytes(json.dumps(data).encode())


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "a//b",
        "a/../b",
        "./a",
        "a\\b",
        "C:/a",
        "a/b ",
        "app/con.py",
        "app/LPT1",
        "a/%00",
    ],
)
def test_check_path_rejects_unsafe(path: str) -> None:
    with pytest.raises(UpdateError) as caught:
        check_path(path)
    assert caught.value.code == "unsafe_path"


@pytest.mark.parametrize(
    "path",
    [
        "app/rpa_core/__init__.py",
        "app/rpa_core-0.6.0.dist-info/RECORD",
        "app/x/.gitkeep",
        "app/zh-Hant.json",
    ],
)
def test_check_path_accepts_normal(path: str) -> None:
    assert check_path(path) == path


def test_signature_round_trip_and_rejections() -> None:
    data = _manifest({}).to_bytes()
    signature = sign_manifest(data, SEED)
    assert verify_signature(data, signature, [KEY]) == ed25519.key_id(KEY)
    with pytest.raises(UpdateError, match="signature_mismatch"):
        verify_signature(data + b" ", signature, [KEY])
    with pytest.raises(UpdateError, match="signature_untrusted"):
        verify_signature(data, signature, [ed25519.public_key(OTHER_SEED)])
    with pytest.raises(UpdateError, match="no_trusted_keys"):
        verify_signature(data, signature, [])
    with pytest.raises(UpdateError, match="signature_invalid"):
        verify_signature(data, b"not json", [KEY])


def test_update_file_extracts_verified_tree(tmp_path: Path) -> None:
    path, manifest = _update(tmp_path)
    with UpdateFile(path, [KEY]) as update:
        assert update.manifest == manifest
        update.check()
        entries = update.extract("app/", tmp_path / "out" / "app")
        update.extract("server/", tmp_path / "out" / "server")
    verify_tree(tmp_path / "out" / "app", entries)
    assert (tmp_path / "out" / "app" / "rpa_core" / "__init__.py").read_text() == "VALUE = 1\n"
    assert (tmp_path / "out" / "server" / "bin" / "rpa").stat().st_mode & 0o111


def test_update_file_rejects_untrusted_key(tmp_path: Path) -> None:
    path, _ = _update(tmp_path, seed=OTHER_SEED)
    with pytest.raises(UpdateError) as caught:
        UpdateFile(path, [KEY])
    assert caught.value.code == "signature_untrusted"


def test_update_file_rejects_not_a_zip(tmp_path: Path) -> None:
    path = tmp_path / "x.zip"
    path.write_text("hello")
    with pytest.raises(UpdateError, match="not_an_update"):
        UpdateFile(path, [KEY])


def _rewrite(
    path: Path,
    target: Path,
    *,
    drop: str = "",
    add: tuple[str, bytes] | None = None,
    replace: tuple[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(target, "w") as out:
        for info in source.infolist():
            if info.filename == drop:
                continue
            data = source.read(info)
            if replace and info.filename == replace[0]:
                data = replace[1]
            out.writestr(info, data)
        if add:
            out.writestr(add[0], add[1])


def test_update_file_rejects_extra_member(tmp_path: Path) -> None:
    path, _ = _update(tmp_path)
    bad = tmp_path / "bad.zip"
    _rewrite(path, bad, add=("app/rpa_core/_speedups.so", b"\x7fELF"))
    with pytest.raises(UpdateError) as caught:
        UpdateFile(bad, [KEY])
    assert caught.value.code == "unexpected_file"


def test_update_file_rejects_missing_member(tmp_path: Path) -> None:
    path, _ = _update(tmp_path)
    bad = tmp_path / "bad.zip"
    _rewrite(path, bad, drop="app/rpa_core/__init__.py")
    with pytest.raises(UpdateError, match="file_missing"):
        UpdateFile(bad, [KEY])


def test_update_file_rejects_changed_content(tmp_path: Path) -> None:
    path, _ = _update(tmp_path)
    bad = tmp_path / "bad.zip"
    _rewrite(path, bad, replace=("app/rpa_core/__init__.py", b"VALUE = 2\n"))
    with UpdateFile(bad, [KEY]) as update:  # 大小相同，要讀內容才發現
        with pytest.raises(UpdateError, match="file_mismatch"):
            update.check()
        with pytest.raises(UpdateError, match="file_mismatch"):
            update.extract("app/", tmp_path / "out")


def test_update_file_rejects_changed_manifest(tmp_path: Path) -> None:
    path, manifest = _update(tmp_path)
    bad = tmp_path / "bad.zip"
    changed = _manifest(dict(manifest.files), version="9.9.9").to_bytes()
    _rewrite(path, bad, replace=(MANIFEST, changed))
    with pytest.raises(UpdateError, match="signature_mismatch"):
        UpdateFile(bad, [KEY])


def test_update_file_needs_signature(tmp_path: Path) -> None:
    path, _ = _update(tmp_path)
    bad = tmp_path / "bad.zip"
    _rewrite(path, bad, drop=SIGNATURE)
    with pytest.raises(UpdateError, match="not_an_update"):
        UpdateFile(bad, [KEY])


def test_verify_tree_rejects_extra_changed_and_missing(tmp_path: Path) -> None:
    root = _tree(tmp_path / "tree") / "app"
    entries = scan_tree(root)
    verify_tree(root, entries)

    (root / "rpa_core" / "evil.so").write_bytes(b"x")
    with pytest.raises(UpdateError, match="unexpected_file"):
        verify_tree(root, entries)
    (root / "rpa_core" / "evil.so").unlink()

    (root / "rpa_core" / "__init__.py").write_text("VALUE = 2\n")
    with pytest.raises(UpdateError, match="file_mismatch"):
        verify_tree(root, entries)

    (root / "rpa_core" / "__init__.py").unlink()
    with pytest.raises(UpdateError, match="file_missing"):
        verify_tree(root, entries)


def test_verify_tree_rejects_symlink(tmp_path: Path) -> None:
    root = _tree(tmp_path / "tree") / "app"
    entries = scan_tree(root)
    try:
        (root / "link").symlink_to(root / "rpa_core")
    except OSError:
        pytest.skip("這個系統不能建符號連結")
    with pytest.raises(UpdateError, match="unexpected_file"):
        verify_tree(root, entries)
