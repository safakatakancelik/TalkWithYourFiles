from typing import Any

HTTP_STATUS: dict[str, int] = {
    "validation": 400,
    "not_found": 404,
    "conflict": 409,
    "too_large": 413,
    "internal": 500,
}


class ServiceError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details
