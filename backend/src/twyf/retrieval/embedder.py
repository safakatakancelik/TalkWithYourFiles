import hashlib
import logging
import math
import re
from typing import Protocol

from twyf.config import Settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    version: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...  # unit length


_TOKEN = re.compile(r"\w+")


class HashEmbedder:
    """For tests: each lower-case word adds 1 at index sha256(word) mod 64, then the vector is normalised."""

    name = "hash"
    version = "1"
    dim = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for token in _TOKEN.findall(text.lower()):
                vector[int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vector))
            out.append([v / norm for v in vector] if norm else vector)
        return out


class NullEmbedder:
    """`TWYF_EMBEDDER=none`: no vectors, keyword search only."""

    name = "none"
    version = "0"
    dim = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


_cache: dict[tuple[str, str], Embedder] = {}


def get_embedder(settings: Settings) -> Embedder:
    key = (settings.embedder, settings.embed_model)
    if key not in _cache:
        _cache[key] = _make(settings)
    return _cache[key]


def _make(settings: Settings) -> Embedder:
    if settings.embedder == "hash":
        return HashEmbedder()
    if settings.embedder == "none":
        return NullEmbedder()
    # FastEmbedEmbedder is written in task B37. Until then the default embedder searches by keyword only.
    log.warning("the fastembed embedder is not available: search is by keyword only")
    return NullEmbedder()
