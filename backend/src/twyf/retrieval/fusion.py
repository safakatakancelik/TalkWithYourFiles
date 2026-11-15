from collections.abc import Hashable

RRF_K = 60


def rrf[T: Hashable](lists: list[list[T]]) -> dict[T, float]:
    """Reciprocal rank fusion: score = sum(1 / (60 + rank)) over the lists an item appears in. Ranks from 1."""
    scores: dict[T, float] = {}
    for ranked in lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (RRF_K + rank)
    return scores
