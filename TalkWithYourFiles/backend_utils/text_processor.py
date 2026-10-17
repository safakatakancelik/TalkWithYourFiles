from typing import List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Plus


"""
Text processing: split the text into chunks, build a searchable index, retrieve the chunks most related to a question.

Two kinds of index are supported:
- SemanticIndex: embeddings + an in-memory vector store (needs an OpenRouter key).
- KeywordIndex: BM25 keyword ranking, used when no embeddings provider is available (e.g. only an Anthropic key).

Both expose the same search(question, k) method, so the rest of the app doesn't care which one is used.
"""


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_text(text)


class SemanticIndex:
    def __init__(self, chunks: List[str], embeddings: Embeddings):
        self.store = InMemoryVectorStore.from_texts(chunks, embeddings)

    def search(self, question: str, k: int) -> List[str]:
        return [doc.page_content for doc in self.store.similarity_search(question, k=k)]


class KeywordIndex:
    def __init__(self, chunks: List[str]):
        self.chunks = chunks
        self.bm25 = BM25Plus([_tokenize(chunk) for chunk in chunks])

    def search(self, question: str, k: int) -> List[str]:
        return self.bm25.get_top_n(_tokenize(question), self.chunks, n=k)


def build_index(chunks: List[str], embeddings: Optional[Embeddings]):
    if embeddings is None:
        return KeywordIndex(chunks)
    return SemanticIndex(chunks, embeddings)


def _tokenize(text: str) -> List[str]:
    return [word for word in "".join(c.lower() if c.isalnum() else " " for c in text).split()]
