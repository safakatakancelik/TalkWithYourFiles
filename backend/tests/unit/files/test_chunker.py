import itertools
import random

from twyf.files.chunker import MAX_CHUNK, BlockSpan, chunk


def _blocks(texts: list[str]) -> tuple[str, list[BlockSpan]]:
    spans: list[BlockSpan] = []
    position = 0
    for text in texts:
        spans.append(BlockSpan(position, position + len(text), text))
        position += len(text) + 1
    return "\n".join(texts), spans


def _sentences(n: int, length: int = 99) -> str:
    return " ".join(("Word " * (length // 5)).strip()[: length - 1] + "." for _ in range(n))


def test_chunker_rules() -> None:
    rng = random.Random(7)
    texts = [_sentences(rng.randint(1, 4)) for _ in range(40)] + [_sentences(30)] + ["Short tail."]
    full, blocks = _blocks(texts)
    chunks = chunk(blocks)
    # 4: each chunk's text is exactly the slice of the extraction text.
    assert all(full[c.char_start : c.char_end] == c.text for c in chunks)
    # Every block is covered, in order.
    assert chunks[0].char_start == 0 and chunks[-1].char_end == len(full)
    assert all(a.char_start < b.char_start for a, b in itertools.pairwise(chunks))
    # 1 and 2: packed up to the limit, and the long block (over 1,500) was split into pieces of at most 1,200.
    long_block = blocks[40]
    assert len(long_block.text) > 1500
    assert all(len(c.text) <= MAX_CHUNK for c in chunks)
    inside = [c for c in chunks if long_block.char_start <= c.char_start and c.char_end <= long_block.char_end]
    assert len(inside) >= 2
    assert all(full[c.char_end - 1] == "." for c in inside[:-1])


def test_chunker_packs_until_the_limit() -> None:
    _full, blocks = _blocks(["a" * 500, "b" * 500, "c" * 500])
    chunks = chunk(blocks)
    assert [(c.char_start, c.char_end) for c in chunks] == [(0, 1001), (1002, 1502)]
    assert chunks[1].text == "c" * 500


def test_chunker_overlap() -> None:
    _full, blocks = _blocks(["a" * 700, "b" * 200, "c" * 700, "d" * 100])
    chunks = chunk(blocks)
    # 3: the second chunk starts with the last (short) block of the first.
    assert [(c.char_start, c.char_end) for c in chunks] == [(0, 901), (701, 1703)]
    assert chunks[1].text.startswith("b" * 200)
    # A last block over 300 characters is not repeated.
    _full, blocks = _blocks(["a" * 600, "b" * 400, "c" * 600])
    assert [(c.char_start, c.char_end) for c in chunk(blocks)] == [(0, 1001), (1002, 1602)]


def test_chunker_empty() -> None:
    assert chunk([]) == []
