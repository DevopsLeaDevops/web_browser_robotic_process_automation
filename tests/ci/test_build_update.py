"""產生更新檔（tools/build_update.py，ADR 0018）：目標與環境代號的參數、簽章私鑰的來源。

真正建出更新檔、在分發包上套用由 CI（server-package.yml）驗證。
"""

from pathlib import Path

import pytest

from rpa_update import ed25519
from rpa_update.build import private_to_pem
from tools import build_update


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
