"""建置時用（ADR 0018）：寫出 runtime.json、產生測試用的金鑰。

    python -m rpa_update.build runtime --target server-linux-x64 [--output 路徑] [--component 名=值]
    python -m rpa_update.build keygen --private 私鑰.pem      # 印出公鑰（base64）

``runtime`` 用執行它的 Python 算環境代號：Python 的主、次版本、這個 Python 裝了哪些第三方套件
（不含工作區的套件與 pip）、rpa_update 的原始碼，加上 ``--component`` 另外給的內容（桌面 App
的外殼版本與收進去的模組）。信任的公鑰是 :data:`rpa_update.keys.RELEASE_KEYS`，再加上環境變數
``RPA_UPDATE_EXTRA_KEYS``（逗號分隔的 base64）：CI 測試升級路徑時用臨時產生的金鑰，發布流程
會確認這個變數是空的。

``keygen`` 只給 CI 與本機測試用；正式的私鑰用 OpenSSL 產生（見 docs/develop/release.html）。
"""

import argparse
import base64
import json
import os
import re
import sys
import sysconfig
from collections.abc import Iterable, Mapping, Sequence
from importlib.metadata import distributions
from pathlib import Path
from typing import Final

from rpa_update import ed25519
from rpa_update.keys import RELEASE_KEYS
from rpa_update.runtime import FORMAT, Runtime, runtime_id, source_digest

__all__ = [
    "EXTRA_KEYS_ENV",
    "installed_distributions",
    "main",
    "make_runtime",
    "private_to_pem",
    "trusted_keys",
]

EXTRA_KEYS_ENV: Final = "RPA_UPDATE_EXTRA_KEYS"
WORKSPACE: Final = re.compile(r"^(rpa-.+|testsite)$")
"""工作區的套件：在程式碼層，不算執行環境。"""
_NOT_RUNTIME: Final = frozenset({"pip", "setuptools", "wheel"})
_PRIVATE_PREFIX: Final = bytes.fromhex("302e020100300506032b657004220420")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def installed_distributions() -> list[str]:
    """這個 Python 的 site-packages 裡的第三方套件：``名稱==版本``，排序後回傳。

    只看 site-packages：使用者的 site-packages、目前的資料夾不屬於執行環境。
    """
    paths = sysconfig.get_paths()
    found: set[str] = set()
    for dist in distributions(path=sorted({paths["purelib"], paths["platlib"]})):
        name = _normalize(dist.metadata["Name"] or "")
        if name and not WORKSPACE.fullmatch(name) and name not in _NOT_RUNTIME:
            found.add(f"{name}=={dist.version}")
    return sorted(found)


def trusted_keys(environ: Mapping[str, str] | None = None) -> tuple[bytes, ...]:
    """寫進 runtime.json 的公鑰：發布用的公鑰加上 ``RPA_UPDATE_EXTRA_KEYS``。"""
    env = os.environ if environ is None else environ
    values = [*RELEASE_KEYS, *(v.strip() for v in env.get(EXTRA_KEYS_ENV, "").split(","))]
    keys: list[bytes] = []
    for value in values:
        if not value:
            continue
        key = base64.b64decode(value, validate=True)
        if len(key) != 32:
            raise ed25519.InvalidKeyError(f"公鑰要 32 位元組：{value}")
        if key not in keys:
            keys.append(key)
    return tuple(keys)


def make_runtime(
    target: str,
    *,
    distributions: Iterable[str] | None = None,
    extra: Mapping[str, object] | None = None,
    keys: Sequence[bytes] | None = None,
) -> Runtime:
    """這個執行環境的 :class:`Runtime`。"""
    components: dict[str, object] = {
        "format": FORMAT,
        "target": target,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "cache_tag": sys.implementation.cache_tag or "",
        "distributions": sorted(
            installed_distributions() if distributions is None else distributions
        ),
        "rpa_update": source_digest(),
        **(extra or {}),
    }
    return Runtime(
        target=target,
        id=runtime_id(components),
        keys=tuple(trusted_keys() if keys is None else keys),
        components=components,
    )


def private_to_pem(seed: bytes) -> str:
    """私鑰寫成 PKCS#8 的 PEM（和 ``openssl genpkey -algorithm ed25519`` 相同）。"""
    body = base64.b64encode(_PRIVATE_PREFIX + seed).decode("ascii")
    return f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\n"


def _write_runtime(args: argparse.Namespace) -> int:
    extra: dict[str, object] = {}
    items: list[str] = args.component or []
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise SystemExit(f"--component 要寫成 名稱=值：{item}")
        extra[name] = value
    info = make_runtime(str(args.target), extra=extra)
    default = Path(sysconfig.get_paths()["purelib"]) / "rpa_update" / "runtime.json"
    output = Path(args.output) if args.output else default
    output.write_text(json.dumps(info.to_json(), indent=1) + "\n", encoding="utf-8")
    sys.stdout.write(f"runtime: {info.target}={info.id}\n")
    sys.stdout.write(f"keys: {len(info.keys)}\n")
    return 0


def _keygen(args: argparse.Namespace) -> int:
    seed = os.urandom(32)
    path = Path(args.private)
    path.touch(mode=0o600, exist_ok=False)
    path.write_text(private_to_pem(seed), encoding="ascii")
    sys.stdout.write(base64.b64encode(ed25519.public_key(seed)).decode("ascii") + "\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rpa_update.build")
    commands = parser.add_subparsers(dest="command", required=True)
    runtime = commands.add_parser("runtime", help="寫出 runtime.json")
    runtime.add_argument("--target", required=True)
    runtime.add_argument("--output")
    runtime.add_argument("--component", action="append")
    runtime.set_defaults(handler=_write_runtime)
    keygen = commands.add_parser("keygen", help="產生測試用的金鑰")
    keygen.add_argument("--private", required=True)
    keygen.set_defaults(handler=_keygen)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
