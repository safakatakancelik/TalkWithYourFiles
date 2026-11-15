from datetime import UTC, datetime

_frozen: str | None = None


def now() -> str:
    """UTC ISO 8601 with milliseconds and a Z. Returns the frozen value while one is set."""
    if _frozen is not None:
        return _frozen
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def freeze(value: str | None) -> None:
    global _frozen
    _frozen = value
