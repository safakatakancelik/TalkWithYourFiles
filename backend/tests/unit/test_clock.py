import re
from collections.abc import Iterator

import pytest

from twyf import clock


@pytest.fixture(autouse=True)
def _unfreeze() -> Iterator[None]:
    yield
    clock.freeze(None)


def test_now_is_utc_with_milliseconds() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", clock.now())


def test_frozen_value_returned() -> None:
    clock.freeze("2026-01-01T00:00:00.000Z")
    assert clock.now() == "2026-01-01T00:00:00.000Z"
    clock.freeze(None)
    assert clock.now() != "2026-01-01T00:00:00.000Z"
