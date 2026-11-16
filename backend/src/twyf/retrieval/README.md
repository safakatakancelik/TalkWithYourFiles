# Retrieval

The only way an agent reaches file content: a fixed number of passages chosen by search.

| File | What it is |
|---|---|
| `hybrid.py` | `HybridRetriever`: keyword and vector search fused; passages; the first chunks of a file |
| `keyword.py` | Keyword search with SQLite FTS5 |
| `vector_index.py` | Vector search with `sqlite-vec`, or numpy |
| `embedder.py` | `FastEmbedEmbedder` (the `rich` extra), `HashEmbedder` for tests, `NullEmbedder` |
| `weights.py` | How note weights act: which notes an agent gets, in what order, and the boost for passages cited by high notes |
| `fusion.py` | Reciprocal rank fusion |
| `reembed.py` | Embeds chunks and notes again when the embedding model changes |
