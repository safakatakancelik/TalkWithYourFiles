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


def require_text(value: str, field: str) -> str:
    """The value without surrounding spaces. An empty one is a `validation` error."""
    text = value.strip()
    if not text:
        raise ServiceError("validation", f"{field} must not be empty", {"field": field})
    return text
