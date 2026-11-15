"""Packs blocks into chunks whose offsets index exactly into the extraction text (05-retrieval section 3)."""

import re
from dataclasses import dataclass

MAX_CHUNK = 1200
SPLIT_ABOVE = 1500
MAX_OVERLAP = 300
_SENTENCE_END = re.compile(r"[.?!] ")


@dataclass(frozen=True)
class BlockSpan:
    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True)
class ChunkSpan:
    char_start: int
    char_end: int
    text: str


def _pieces(block: BlockSpan) -> list[tuple[int, int]]:
    """A block as spans: itself, or split at sentence ends into pieces of at most MAX_CHUNK characters.

    A piece ends with its punctuation mark. The space after it starts no piece."""
    if len(block.text) <= SPLIT_ABOVE:
        return [(block.char_start, block.char_end)]
    cuts = [(m.start() + 1, m.end()) for m in _SENTENCE_END.finditer(block.text)]
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(block.text):
        limit = start + MAX_CHUNK
        end, next_start = limit, limit
        if limit >= len(block.text):
            end = next_start = len(block.text)
        else:
            fitting = [c for c in cuts if start < c[0] <= limit]
            if fitting:
                end, next_start = fitting[-1]
        spans.append((block.char_start + start, block.char_start + end))
        start = next_start
    return spans


def chunk(blocks: list[BlockSpan]) -> list[ChunkSpan]:
    if not blocks:
        return []
    base = blocks[0].char_start
    text = "\n".join(b.text for b in blocks)
    assert all(b.char_end - b.char_start == len(b.text) for b in blocks)
    units = [span for b in blocks for span in _pieces(b)]
    chunks: list[ChunkSpan] = []
    current: list[tuple[int, int]] = []

    def emit() -> None:
        start, end = current[0][0], current[-1][1]
        chunks.append(ChunkSpan(start, end, text[start - base : end - base]))

    for unit in units:
        if current and unit[1] - current[0][0] > MAX_CHUNK:
            emit()
            last = current[-1]
            overlap = last[1] - last[0] <= MAX_OVERLAP and unit[1] - last[0] <= MAX_CHUNK
            current = [last] if overlap else []
        current.append(unit)
    emit()
    return chunks
