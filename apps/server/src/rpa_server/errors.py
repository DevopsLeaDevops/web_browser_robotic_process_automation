"""服務層的錯誤：API 轉成 JSON、頁面轉成錯誤頁。"""

__all__ = ["ServiceError", "conflict", "invalid", "not_found"]


class ServiceError(Exception):
    """操作失敗：status 是對應的 HTTP 狀態碼，code 給程式判斷，message 是目前語言的說明。"""

    def __init__(self, status: int, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def to_json(self) -> dict[str, object]:
        return {"error": {"code": self.code, "message": self.message, **self.details}}


def not_found(code: str, message: str) -> ServiceError:
    return ServiceError(404, code, message)


def conflict(code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(409, code, message, **details)


def invalid(code: str, message: str, **details: object) -> ServiceError:
    return ServiceError(422, code, message, **details)
