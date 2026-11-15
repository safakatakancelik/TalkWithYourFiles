import pytest

from twyf.citations.normalize import normalize


def test_normalize() -> None:
    # 1. NFKC: the ligature and the full-width digit fold to plain letters and digits.
    assert normalize("ﬁve １") == "five 1"
    # 2. Curly quotes, dashes and non-breaking spaces.
    assert normalize("“it’s” – a—b c") == '"it\'s" - a-b c'
    # 3. Whitespace runs become one space, trimmed.
    assert normalize("  a \n\t b\r\n\nc  ") == "a b c"


@pytest.mark.parametrize("text", ["“One”\n\ntwo — three", "  plain  ", "", "ﬁ Ａ"])
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize(text)
    assert normalize(once) == once
