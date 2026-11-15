"""The canonical form of text. Every block is stored like this, and every quote is compared like this."""

import re
import unicodedata

_CHARS = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
        "–": "-", "—": "-",
        " ": " ", " ": " ", " ": " ",
    }
)  # fmt: skip
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC; straight quotes, plain dashes and spaces; every run of whitespace one space; trimmed."""
    text = unicodedata.normalize("NFKC", text).translate(_CHARS)
    return _SPACE.sub(" ", text).strip()
