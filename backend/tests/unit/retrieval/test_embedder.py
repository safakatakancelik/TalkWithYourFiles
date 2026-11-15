import math

from twyf.config import Settings
from twyf.retrieval.embedder import HashEmbedder, NullEmbedder, get_embedder


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hash_embedder() -> None:
    embedder = HashEmbedder()
    lease, rent, other = embedder.embed(["The lease ends in June", "Rent and the lease", "Bananas are yellow"])
    assert len(lease) == 64 and embedder.dim == 64
    for vector in (lease, rent, other):
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)
    assert embedder.embed(["The lease ends in June"]) == [lease]
    assert _dot(lease, rent) > _dot(lease, other)


def test_get_embedder(settings: Settings) -> None:
    assert isinstance(get_embedder(settings), HashEmbedder)
    assert isinstance(get_embedder(settings.model_copy(update={"embedder": "none"})), NullEmbedder)
    assert get_embedder(settings) is get_embedder(settings)
