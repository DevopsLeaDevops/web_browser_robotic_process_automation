"""產生更新檔（tools/build_update.py，ADR 0018）：目標與環境代號的參數、簽章私鑰的來源。

真正建出更新檔、在分發包與桌面 App 上套用由 CI（server-package.yml、desktop.yml）驗證。
"""

import base64
import json
import re
from pathlib import Path

import pytest

from rpa_update import ed25519
from rpa_update.build import private_to_pem
from rpa_update.runtime import Runtime
from tools import build_update

ROOT = Path(__file__).resolve().parents[2]


def test_parse_runtimes() -> None:
    assert build_update.parse_runtimes(
        ["server-linux-x64=0123456789abcdef", "worker-windows-x64=fedcba9876543210"]
    ) == {"server-linux-x64": "0123456789abcdef", "worker-windows-x64": "fedcba9876543210"}


@pytest.mark.parametrize(
    "value",
    [
        "server-linux-x64",
        "server-linux-x86=0123456789abcdef",
        "server-linux-x64=0123",
        "server-linux-x64=0123456789ABCDEF",
    ],
)
def test_parse_runtimes_rejects(value: str) -> None:
    with pytest.raises(SystemExit):
        build_update.parse_runtimes([value])


def test_conflicting_runtimes_are_rejected() -> None:
    with pytest.raises(SystemExit, match="兩個不同"):
        build_update.parse_runtimes(
            ["server-linux-x64=0123456789abcdef", "server-linux-x64=fedcba9876543210"]
        )


def test_signing_key_from_file_or_environment(tmp_path: Path) -> None:
    seed = bytes(range(32))
    pem = private_to_pem(seed)
    path = tmp_path / "key.pem"
    path.write_text(pem, encoding="ascii")
    assert build_update.signing_key(path, {}) == seed
    assert build_update.signing_key(None, {build_update.KEY_ENV: pem}) == seed
    with pytest.raises(SystemExit, match="沒有簽章的私鑰"):
        build_update.signing_key(None, {build_update.KEY_ENV: " "})
    with pytest.raises(SystemExit, match="私鑰不能用"):
        build_update.signing_key(None, {build_update.KEY_ENV: ed25519.public_to_pem(seed)})


def test_update_never_carries_the_runtime_package() -> None:
    assert "rpa-update" not in build_update.PACKAGES
    assert set(build_update.PACKAGES) >= {"rpa-server", "rpa-desktop", "rpa-cli"}


def test_desktop_spec_boots_through_the_layers() -> None:
    """桌面 App 的入口是啟動器；外殼收的套件和更新檔的程式碼層剛好互補。"""
    spec = (ROOT / "apps" / "desktop" / "packaging" / "rpa_desktop.spec").read_text(
        encoding="utf-8"
    )
    assert '"rpa_update" / "boot.py"' in spec
    assert '"rpa_update/runtime.json"' in spec
    code = re.search(r"CODE_DISTRIBUTIONS = \[(.*?)\]", spec)
    assert code is not None
    desktop = set(re.findall(r'"([a-z-]+)"', code.group(1)))
    # 桌面 App 的程式碼層都在更新檔裡（更新檔另外多了伺服器用的套件）
    assert desktop <= set(build_update.PACKAGES)
    assert "rpa-update" not in desktop


def test_release_needs_the_release_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = bytes(range(32))
    public = ed25519.public_key(seed)
    other = ed25519.public_key(bytes(range(1, 33)))
    path = tmp_path / "runtime-worker-windows-x64.json"
    path.write_text(json.dumps(Runtime("worker-windows-x64", "0" * 16, (public,)).to_json()))
    runtimes = build_update.read_runtime_files([path])
    assert [item.target for item in runtimes] == ["worker-windows-x64"]

    monkeypatch.setattr(build_update, "RELEASE_KEYS", ())
    with pytest.raises(SystemExit, match="RELEASE_KEYS 是空的"):
        build_update.check_release_keys(runtimes, seed)
    monkeypatch.setattr(build_update, "RELEASE_KEYS", (base64.b64encode(other).decode(),))
    with pytest.raises(SystemExit, match="對不上"):
        build_update.check_release_keys(runtimes, seed)
    monkeypatch.setattr(build_update, "RELEASE_KEYS", (base64.b64encode(public).decode(),))
    build_update.check_release_keys(runtimes, seed)
    # 安裝包多信任了一把臨時金鑰
    path.write_text(json.dumps(Runtime("worker-windows-x64", "0" * 16, (public, other)).to_json()))
    with pytest.raises(SystemExit, match="臨時金鑰"):
        build_update.check_release_keys(build_update.read_runtime_files([path]), seed)
    with pytest.raises(SystemExit, match="找不到"):
        build_update.read_runtime_files([tmp_path / "missing.json"])
