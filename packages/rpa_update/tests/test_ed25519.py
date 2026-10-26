import base64
import shutil
import subprocess
from pathlib import Path

import pytest

from rpa_update import ed25519

# RFC 8032 第 7.1 節的測試向量 1～3：(私鑰, 公鑰, 訊息, 簽章)
VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize(("secret", "public", "message", "signature"), VECTORS)
def test_rfc8032_vectors(secret: str, public: str, message: str, signature: str) -> None:
    seed, key, data, sig = (bytes.fromhex(v) for v in (secret, public, message, signature))
    assert ed25519.public_key(seed) == key
    assert ed25519.sign(seed, data) == sig
    assert ed25519.verify(key, data, sig)


def test_verify_rejects_changes() -> None:
    seed = bytes.fromhex(VECTORS[2][0])
    key = ed25519.public_key(seed)
    sig = ed25519.sign(seed, b"manifest")
    assert not ed25519.verify(key, b"manifesT", sig)
    assert not ed25519.verify(key, b"manifest", sig[:-1] + bytes([sig[-1] ^ 1]))
    assert not ed25519.verify(ed25519.public_key(bytes(32)), b"manifest", sig)
    assert not ed25519.verify(key, b"manifest", sig[:63])
    assert not ed25519.verify(key[:31], b"manifest", sig)
    # s 不小於群的階：拒絕（防止同一則訊息有第二個簽章）
    high = int.from_bytes(sig[32:], "little") + 2**252 + 27742317777372353535851937790883648493
    assert not ed25519.verify(key, b"manifest", sig[:32] + high.to_bytes(32, "little"))


def test_private_key_is_32_bytes() -> None:
    with pytest.raises(ed25519.InvalidKeyError):
        ed25519.sign(b"short", b"")


def test_key_id_is_stable() -> None:
    key = bytes.fromhex(VECTORS[0][1])
    assert ed25519.key_id(key) == ed25519.key_id(bytes(key))
    assert len(ed25519.key_id(key)) == 16


def test_pem_round_trip() -> None:
    seed = bytes.fromhex(VECTORS[0][0])
    der = bytes.fromhex("302e020100300506032b657004220420") + seed
    body = base64.b64encode(der).decode()
    pem = f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\n"
    assert ed25519.private_from_pem(pem) == seed
    public = ed25519.public_key(seed)
    assert ed25519.public_from_pem(ed25519.public_to_pem(public)) == public


@pytest.mark.parametrize(
    "text",
    [
        "",
        "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----",
        "-----BEGIN PRIVATE KEY-----\n!!!!\n-----END PRIVATE KEY-----",
        # RSA 之類其他演算法的私鑰：前綴不同
        "-----BEGIN PRIVATE KEY-----\n"
        + base64.b64encode(bytes(48)).decode()
        + "\n-----END PRIVATE KEY-----",
    ],
)
def test_private_from_pem_rejects_other_formats(text: str) -> None:
    with pytest.raises(ed25519.InvalidKeyError):
        ed25519.private_from_pem(text)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="需要 openssl")
def test_matches_openssl(tmp_path: Path) -> None:
    """OpenSSL 產生的金鑰：我們讀得懂，簽出來的簽章 OpenSSL 也驗證得過。"""
    private = tmp_path / "key.pem"
    created = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(private)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("這個 openssl 不支援 Ed25519")
    public_pem = subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    seed = ed25519.private_from_pem(private.read_text())
    assert ed25519.public_from_pem(public_pem) == ed25519.public_key(seed)

    message = tmp_path / "manifest.json"
    message.write_bytes(b'{"version": "0.6.0"}\n')
    signature = tmp_path / "manifest.raw"
    signature.write_bytes(ed25519.sign(seed, message.read_bytes()))
    public = tmp_path / "pub.pem"
    public.write_text(public_pem)
    verified = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public),
            "-rawin",
            "-in",
            str(message),
            "-sigfile",
            str(signature),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if "-rawin" in verified.stderr and verified.returncode != 0:
        pytest.skip("這個 openssl 沒有 -rawin")
    assert verified.returncode == 0, verified.stderr
