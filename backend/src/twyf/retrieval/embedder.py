import hashlib
import importlib
import importlib.metadata
import importlib.util
import logging
import math
import re
from typing import Any, Protocol

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


class FastEmbedEmbedder:  # pragma: no cover -- needs the rich extra and a model; tested with -m models
    """The default: a local ONNX model through fastembed, by default BAAI/bge-small-en-v1.5 (384 dimensions).

    Optional: installed with `uv sync --extra rich`. The model is downloaded from Hugging Face on first use."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.name = model_name
        self.version = importlib.metadata.version("fastembed")
        self._model: Any = importlib.import_module("fastembed").TextEmbedding(model_name)
        self.dim = len(self._raw(["dimension probe"])[0])

    def _raw(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._model.embed(texts)]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for vector in self._raw(texts):
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
    if importlib.util.find_spec("fastembed") is None:
        log.warning("fastembed is not installed (uv sync --extra rich): search is by keyword only")
        return NullEmbedder()
    return FastEmbedEmbedder(settings.embed_model)
