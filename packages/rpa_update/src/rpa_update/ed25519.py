"""Ed25519 簽章（RFC 8032）：只用標準函式庫，伺服器、桌面 App 的啟動器都能用（ADR 0018）。

照 RFC 8032 第 6 節的參考程式改寫（擴充座標、不做常數時間）：

- 驗證（``verify``）：伺服器安裝更新檔、裝置下載後、啟動器每次啟動時用。輸入都是公開的
  （公鑰、清單、簽章），不需要常數時間。
- 簽章（``sign``）：只在 CI 產生更新檔時用一次。執行時間會隨私鑰不同，但 CI 的機器上沒有
  能量測時間的人；不要拿它在伺服器或裝置上簽章。

金鑰用 OpenSSL 產生的 PEM（``openssl genpkey -algorithm ed25519``）：私鑰是 PKCS#8、
公鑰是 SubjectPublicKeyInfo；只認 Ed25519 的固定格式，不解析其他 ASN.1。
"""

import base64
import binascii
import hashlib
import re
from typing import Final

__all__ = [
    "InvalidKeyError",
    "key_id",
    "private_from_pem",
    "public_from_pem",
    "public_key",
    "public_to_pem",
    "sign",
    "verify",
]


class InvalidKeyError(ValueError):
    """金鑰的格式不對。"""


type _Point = tuple[int, int, int, int]

_P: Final = 2**255 - 19
_Q: Final = 2**252 + 27742317777372353535851937790883648493
_D: Final = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1: Final = pow(2, (_P - 1) // 4, _P)
_IDENTITY: Final[_Point] = (0, 1, 1, 0)


def _inverse(x: int) -> int:
    return pow(x, _P - 2, _P)


def _add(a: _Point, b: _Point) -> _Point:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    pa = (y1 - x1) * (y2 - x2) % _P
    pb = (y1 + x1) * (y2 + x2) % _P
    pc = 2 * t1 * t2 * _D % _P
    pd = 2 * z1 * z2 % _P
    e, f, g, h = pb - pa, pd - pc, pd + pc, pb + pa
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiply(scalar: int, point: _Point) -> _Point:
    result = _IDENTITY
    while scalar > 0:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a: _Point, b: _Point) -> bool:
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inverse(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _base() -> _Point:
    y = 4 * _inverse(5) % _P
    x = _recover_x(y, 0)
    assert x is not None
    return (x, y, 1, x * y % _P)


_G: Final = _base()


def _compress(point: _Point) -> bytes:
    x, y, z, _ = point
    inverse = _inverse(z)
    x, y = x * inverse % _P, y * inverse % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decompress(data: bytes) -> _Point | None:
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _hash_int(*parts: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little") % _Q


def _expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise InvalidKeyError("Ed25519 的私鑰要 32 位元組")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key(seed: bytes) -> bytes:
    """私鑰（32 位元組的種子）對應的公鑰（32 位元組）。"""
    scalar, _ = _expand(seed)
    return _compress(_multiply(scalar, _G))


def sign(seed: bytes, message: bytes) -> bytes:
    """用私鑰簽 ``message``，回傳 64 位元組的簽章。只在 CI 用（見模組說明）。"""
    scalar, prefix = _expand(seed)
    public = _compress(_multiply(scalar, _G))
    r = _hash_int(prefix, message)
    encoded_r = _compress(_multiply(r, _G))
    s = (r + _hash_int(encoded_r, public, message) * scalar) % _Q
    return encoded_r + s.to_bytes(32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """``signature`` 是不是 ``public`` 對 ``message`` 的簽章。格式不對也回傳 False。"""
    if len(public) != 32 or len(signature) != 64:
        return False
    a = _decompress(public)
    if a is None:
        return False
    encoded_r = signature[:32]
    r = _decompress(encoded_r)
    if r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _hash_int(encoded_r, public, message)
    return _equal(_multiply(s, _G), _add(r, _multiply(h, a)))


def key_id(public: bytes) -> str:
    """公鑰的代號：SHA-256 的前 16 個十六進位字元。簽章檔用它指出是哪一把金鑰簽的。"""
    return hashlib.sha256(public).hexdigest()[:16]


# ---------------------------------------------------------------- PEM

_PRIVATE_PREFIX: Final = bytes.fromhex("302e020100300506032b657004220420")
"""PKCS#8 的 Ed25519 私鑰（RFC 8410），後面接 32 位元組的種子。"""
_PUBLIC_PREFIX: Final = bytes.fromhex("302a300506032b6570032100")
"""SubjectPublicKeyInfo 的 Ed25519 公鑰（RFC 8410），後面接 32 位元組的公鑰。"""
_PEM: Final = re.compile(
    r"-----BEGIN (?P<label>[A-Z ]+)-----\s*(?P<body>[A-Za-z0-9+/=\s]+?)\s*-----END (?P=label)-----"
)


def _pem_body(text: str, label: str) -> bytes:
    found = _PEM.search(text)
    if found is None or found.group("label") != label:
        raise InvalidKeyError(f"不是 PEM 格式的 {label}")
    try:
        return base64.b64decode("".join(found.group("body").split()), validate=True)
    except binascii.Error as error:
        raise InvalidKeyError(f"PEM 的內容不是 base64：{error}") from None


def private_from_pem(text: str) -> bytes:
    """從 ``openssl genpkey -algorithm ed25519`` 的輸出取出 32 位元組的種子。"""
    der = _pem_body(text, "PRIVATE KEY")
    if len(der) != len(_PRIVATE_PREFIX) + 32 or not der.startswith(_PRIVATE_PREFIX):
        raise InvalidKeyError("不是 Ed25519 的私鑰（PKCS#8）")
    return der[len(_PRIVATE_PREFIX) :]


def public_from_pem(text: str) -> bytes:
    """從 ``openssl pkey -pubout`` 的輸出取出 32 位元組的公鑰。"""
    der = _pem_body(text, "PUBLIC KEY")
    if len(der) != len(_PUBLIC_PREFIX) + 32 or not der.startswith(_PUBLIC_PREFIX):
        raise InvalidKeyError("不是 Ed25519 的公鑰（SubjectPublicKeyInfo）")
    return der[len(_PUBLIC_PREFIX) :]


def public_to_pem(public: bytes) -> str:
    """公鑰寫成 PEM（和 ``openssl pkey -pubout`` 相同）。"""
    if len(public) != 32:
        raise InvalidKeyError("Ed25519 的公鑰要 32 位元組")
    body = base64.b64encode(_PUBLIC_PREFIX + public).decode("ascii")
    return f"-----BEGIN PUBLIC KEY-----\n{body}\n-----END PUBLIC KEY-----\n"
