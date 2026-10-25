"""發布用的公鑰（ADR 0018）：完整的安裝包建置時寫進 runtime.json，之後用它驗證更新檔。

私鑰只放在 GitHub Secrets 的 ``RPA_UPDATE_SIGNING_KEY``（PEM），不進倉庫。換金鑰時先在這裡加上
新的公鑰、發一版完整的安裝包，等裝置都換上之後再改用新的私鑰簽章，最後拿掉舊的公鑰。

每一把是 base64 的 32 位元組（``openssl pkey -pubout`` 的 PEM 去掉前面 12 位元組的格式資訊）。
"""

from typing import Final

__all__ = ["RELEASE_KEYS"]

RELEASE_KEYS: Final[tuple[str, ...]] = ("+zBkjVUh9RensU1hgeWNOeJuRqH82tguO7byaNXCr6w=",)
"""發布版信任的公鑰（2026-10-25 產生）。是空的時候發布流程會失敗，不會發出驗證不了的版本。"""
