import re

from twyf.ids import new_id


def test_new_id_format() -> None:
    assert re.fullmatch(r"f_[0-9a-f]{32}", new_id("f"))


def test_new_ids_differ() -> None:
    assert new_id("ws") != new_id("ws")
