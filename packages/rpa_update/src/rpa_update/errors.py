"""更新的錯誤：每個錯誤有一個代號與參數，介面依代號顯示自己語言的訊息。

rpa_update 只用標準函式庫、跟著執行環境走（ADR 0018），不載入訊息目錄；命令列與 App
用 ``update.error.<代號>`` 從自己的訊息目錄取文字，日誌直接寫 ``str(error)``。
"""

from collections.abc import Mapping

__all__ = ["UpdateError"]


class UpdateError(Exception):
    """更新檔或程式碼層不能用；``code`` 是代號，``params`` 是訊息裡的參數。"""

    def __init__(self, code: str, **params: object) -> None:
        self.code = code
        self.params: Mapping[str, object] = params
        details = ", ".join(f"{key}={value}" for key, value in params.items())
        super().__init__(f"{code}: {details}" if details else code)
