"""環境代號（ADR 0018）：桌面 App 每次建置都要算出相同的代號，發布時和上一版比較。

2026-10-26：0.6.1 的桌面 App 把 rpa_update 的 ``*.dist-info``（版本號、uv 記下的時間）算進環境代號，
每一版都不同，裝置一直被要求用完整的安裝包更新。真正的 PyInstaller 建置在 CI（desktop.yml）。
"""

import json
import sysconfig
import zipfile
from pathlib import Path

import pytest

from rpa_update import build
from rpa_update.manifest import MANIFEST, Manifest
from rpa_update.runtime import Runtime
from tools import runtime_changes
from tools.build_desktop import shell_files


def test_shell_files_skip_workspace_metadata() -> None:
    files = [
        ("rpa_update-0.6.1.dist-info/METADATA", "a"),
        ("rpa_update-0.6.1.dist-info\\uv_cache.json", "b"),
        ("rpa_core-0.6.1.dist-info/RECORD", "c"),
        ("playwright-1.58.0.dist-info/METADATA", "d"),
        ("rpa_update/keys.py", "e"),
        ("playwright/driver/package/index.js", "f"),
    ]
    assert shell_files(files) == [
        ("playwright-1.58.0.dist-info/METADATA", "d"),
        ("rpa_update/keys.py", "e"),
        ("playwright/driver/package/index.js", "f"),
    ]


def test_desktop_runtime_is_the_same_for_every_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rpa_update 的套件資訊換了版本號、uv 留下的時間不同：環境代號不變。第三方套件一換就變。"""
    site = tmp_path / "site"
    paths = {"purelib": str(site), "platlib": str(site)}
    monkeypatch.setattr(sysconfig, "get_paths", lambda: paths)
    third = site / "yaml" / "__init__.py"
    third.parent.mkdir(parents=True)
    third.write_text("x = 1\n")

    def components(version: str, built_at: int) -> dict[str, object]:
        info = site / f"rpa_update-{version}.dist-info"
        info.mkdir(exist_ok=True)
        (info / "METADATA").write_text(f"Name: rpa-update\nVersion: {version}\n")
        (info / "uv_cache.json").write_text(json.dumps({"timestamp": built_at}))
        files = [
            (f"{info.name}/{name}", str(info / name)) for name in ("METADATA", "uv_cache.json")
        ]
        files.append(("yaml/_yaml.so", str(third)))
        return build.shell_components(
            [("yaml", str(third))],
            shell_files(files),
            ours=["rpa_core", "rpa-core"],
            shell="pyinstaller 6.22.3",
        )

    first = components("0.6.1", 1)
    assert components("0.6.2", 2) == first
    third.write_text("x = 2\n")
    assert components("0.6.2", 2)["files"] != first["files"]


def write_update(path: Path, runtimes: dict[str, str], version: str = "0.6.1") -> Path:
    manifest = Manifest(
        version=version,
        commit="abc1234",
        built_at="2026-10-25T00:00:00+00:00",
        fingerprint="f3b941e8505c73fc",
        protocol=1,
        features=(),
        runtimes=runtimes,
        files={},
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MANIFEST, manifest.to_bytes())
    return path


def runtime_file(folder: Path, target: str, ident: str) -> Path:
    runtime = Runtime(target=target, id=ident, keys=(bytes(32),))
    path = folder / f"runtime-{target}.json"
    path.write_text(json.dumps(runtime.to_json()), encoding="utf-8")
    return path


def test_runtime_changes_against_the_previous_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    previous = write_update(
        tmp_path / "RPA-Update-0.6.1.zip",
        {"server-linux-x64": "de6e7107785c98ba", "worker-windows-x64": "0a9b1477abe16480"},
    )
    files = [
        runtime_file(tmp_path, "server-linux-x64", "de6e7107785c98ba"),
        runtime_file(tmp_path, "worker-windows-x64", "1111111111111111"),
        runtime_file(tmp_path, "recorder-macos-arm64", "2222222222222222"),
    ]
    notes = tmp_path / "notes.md"
    args = ["--previous", str(previous), "--notes", str(notes)]
    for path in files:
        args += ["--runtime-file", str(path)]
    assert runtime_changes.main(args) == 0
    out = capsys.readouterr().out
    assert "server-linux-x64: 和 v0.6.1 相同（de6e7107785c98ba）" in out
    assert "::warning title=環境代號（worker-windows-x64）::和 v0.6.1 不同" in out
    assert "0a9b1477abe16480 → 1111111111111111" in out
    assert "recorder-macos-arm64: v0.6.1 沒有這個目標" in out
    text = notes.read_text(encoding="utf-8")
    assert "## 從 v0.6.1 升級" in text
    assert "**用更新檔就好**：RPA 伺服器（Linux x64）。" in text
    assert "**要用完整的安裝包**：RPA 錄製端（macOS）、RPA Worker（Windows）。" in text
    assert "RPA Recorder (macOS), RPA Worker (Windows) need the full installer" in text


def test_runtime_changes_reads_a_manifest_file(tmp_path: Path) -> None:
    archive = write_update(tmp_path / "update.zip", {"server-linux-x64": "de6e7107785c98ba"})
    with zipfile.ZipFile(archive) as opened:
        (tmp_path / MANIFEST).write_bytes(opened.read(MANIFEST))
    assert runtime_changes.read_previous(tmp_path / MANIFEST).runtimes == {
        "server-linux-x64": "de6e7107785c98ba"
    }
    (tmp_path / "broken.zip").write_bytes(b"PK\x05\x06" + bytes(18))
    with pytest.raises(SystemExit):
        runtime_changes.read_previous(tmp_path / "broken.zip")


def test_without_a_previous_release_nothing_is_compared(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GH_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    path = runtime_file(tmp_path, "server-linux-x64", "de6e7107785c98ba")
    assert runtime_changes.main(["--latest", "--runtime-file", str(path)]) == 0
    assert "不比較上一次發布" in capsys.readouterr().out
