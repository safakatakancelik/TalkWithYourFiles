# 05 Retrieval and citations

Part of the revision 2 backend plan. This document defines ingestion, parsing, chunking, embeddings, search, the citation format, the mechanical check, how note weights act, and the context map.

## 1. Ingestion

`upload_file` and `add_file_version` create the file rows and return at once with status `processing` (`02-data-model.md` section 7.2). They hand `files/ingest.py::ingest(conn_factory, ctx, settings, file_version_id)` to the background `Jobs` (`01-architecture.md` section 7):

```
the app's copy ─► availability check ─► parser ─► extraction + blocks ─► chunker ─► chunks + chunks_fts
                                                                    ─► embedder, 64 chunks at a time ─► chunk_embeddings
then: first_read turn, and describe_image for images (04-agents.md section 11)
```

The whole pipeline is local and calls no model. Its steps and their events: `file.ingest_started`; `file.extraction_completed` or `file.extraction_failed`; `file.indexed` once every chunk is embedded. The extraction and its blocks are one transaction. Chunks are one transaction. Embeddings are written in batches of 64 chunks, one transaction each, so a long file never holds the database for long. A failure at any step leaves the file listed with status `unreadable`. The content is only ever opened for reading.

The file becomes `ready`, and so usable in questions, when `file.indexed` is recorded. Keyword search does not wait for anything else, and a file of thousands of pages is handled the same way as a short one: it takes longer to index, and after that a question costs the same.

File type is decided from the extension: `pdf`, `docx`, `csv`, `md`, `txt`; `png`, `jpg`, `jpeg`, `webp`, `gif`, `bmp`, `tif`, `tiff` are `image`; anything else is `other` and is listed without parsing, with status `unreadable`.

## 2. Parsing

```python
# files/parsers/base.py
@dataclass(frozen=True)
class ParsedBlock:
    kind: str            # 'heading' | 'paragraph' | 'row' | 'table' | 'image'
    label: str           # shown to people as the location
    text: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None

@dataclass(frozen=True)
class ParsedDocument:
    kind: str            # extraction kind: 'text' | 'ocr'
    blocks: list[ParsedBlock]

class Parser(Protocol):
    name: str
    version: str
    def supports(self, file_type: str) -> bool: ...
    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]: ...
```

| File type | Basic parser (always installed) | Docling parser (optional extra `rich`) |
|---|---|---|
| `txt` | `text`: one block per paragraph (split on blank lines). Label `Paragraph N` | not used |
| `md` | `text`: the same, and a line starting with `#` is a `heading` block. A paragraph's label is the text of the nearest heading above it, or `Paragraph N` | not used |
| `csv` | `csv` (standard library): one `row` block per data row, text `col=value, col=value, ...` in column order. Label `Row N`, counting data rows from 1 | not used |
| `pdf` | `pdf_basic` (`pypdf`): text of each page split into paragraphs on blank lines. Label `Page N` | `docling`: layout-aware text, tables, reading order, and OCR for pages with no text layer. Label `Page N` plus the nearest heading. `page` and `bbox` are filled |
| `docx` | `docx_basic` (`python-docx`): paragraphs and table rows in order. Label is the nearest heading above, or `Paragraph N` | `docling` |
| `image` | none: the file is `unreadable` unless a description is produced | `docling` with OCR, giving an extraction of kind `ocr`. Label `Image text` |

`TWYF_PARSER=auto` uses Docling when it is importable and the basic parser otherwise. Tests and CI use `basic`, which needs no model download. The Docling adapter is one file (`parsers/docling.py`). Task B37 writes it from the Docling documentation, using Docling's document converter and the page number and bounding box it gives for each item. Its tests are marked `models` and are not part of CI.

### Images

The owner asked for images to be handled through a transcription, a summary and interpretation guidance. These map onto existing concepts, so no new storage is needed:

| Owner's idea | Here | Produced by |
|---|---|---|
| Transcription | Extraction of kind `ocr` | Docling OCR. Mechanical, no model judgement |
| Description of what the image shows | Extraction of kind `description`, label `Image description (written by a model)` | A `describe_image` turn, when the runtime has vision |
| Summary | A note of kind `summary`, citing the transcription or description | The `first_read` turn |
| Interpretation guidance | Notes of kind `interpretation` | Any translator, or the user |

Both extractions are chunked and searched like any text. A citation into a description is checked mechanically like any other, and its location label tells the verifier and the user that the cited words were written by a model about the image. Video and audio are out of scope.

### Canonical text

Every block's text is passed through `citations/normalize.py::normalize` before it is stored:

1. Unicode NFKC.
2. Curly quotes become straight quotes. En and em dashes become `-`. Non-breaking spaces become spaces.
3. Every run of whitespace becomes one space. Leading and trailing whitespace is removed.

Empty blocks are dropped. The extraction's `text` is the blocks joined by `"\n"`. Each block row stores its `char_start` and `char_end` in that text. All later offsets (chunks, quotes, passages) index into this one string. `text_sha256` is its SHA-256.

## 3. Chunking

`files/chunker.py::chunk(blocks) -> list[Chunk(char_start, char_end, text)]`:

- Pack consecutive blocks into a chunk until adding the next would pass 1,200 characters.
- A single block longer than 1,500 characters is split at sentence ends (`. `, `? `, `! `) into pieces of at most 1,200 characters.
- Each chunk after the first starts with the last block of the previous chunk (overlap), unless that block is longer than 300 characters.
- A chunk's text is exactly `extraction.text[char_start:char_end]`.

This is about forty lines over our own block model, so one chunker serves every parser. A framework chunker was not used because offsets into the canonical text must be exact.

## 4. Embeddings and the vector index

```python
# retrieval/embedder.py
class Embedder(Protocol):
    name: str
    version: str
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...     # unit length

# retrieval/vector_index.py
class VectorIndex(Protocol):
    def search(self, conn, *, workspace_id: str, model_id: int, query: list[float],
               k: int, file_ids: list[str] | None) -> list[tuple[int, float]]: ...   # (chunk_id, similarity), best first
```

| Implementation | Use |
|---|---|
| `FastEmbedEmbedder` | Default. `fastembed.TextEmbedding(settings.embed_model)`, by default `BAAI/bge-small-en-v1.5`: 384 dimensions, English-centred, runs locally on CPU |
| `HashEmbedder` | Tests. Splits text into lower-case word tokens, adds 1 at index `sha256(token) mod 64` for each, normalises. Deterministic, no download, and texts that share words score higher |
| `NullEmbedder` (`TWYF_EMBEDDER=none`) | Keyword search only |
| `SqliteVecIndex` | Default. One SQL statement using the `sqlite-vec` function `vec_distance_cosine(vector, :query)` over `chunk_embeddings`, filtered by workspace, model and files, ordered, limited. The extension is loaded on each connection with `sqlite_vec.load(conn)` |
| `NumpyIndex` | Fallback when the extension cannot be loaded. Reads the same rows and computes dot products with numpy |

Vectors are stored once, as float32 BLOBs in `chunk_embeddings` (`struct.pack(f"<{dim}f", *vector)`), in the same database file as everything else. Both indexes read that table, so there is no separate index to keep in step with soft deletes, versions or workspaces. Search is exact. Each embedding row names its `embedding_models` row, so changing the model means adding rows for the new model, not rewriting old ones.

**Changing the embedding model.** Set `TWYF_EMBED_MODEL` (any model `fastembed` supports, for example a multilingual one) and restart. At start the server finds or inserts the `embedding_models` row for the configured name and version, and queues one background job, `retrieval/reembed.py::reembed`, that embeds every chunk and note of live files lacking a vector for that model, in batches of 64. Search uses only vectors of the current model. Until the job has reached a chunk, that chunk is found by keyword search only. Old vectors are kept. A different embedder altogether is a new class implementing `Embedder`.

`sqlite-vec` 0.1.9 was loaded successfully on Python 3.13 and 3.14 while writing this plan. It is pre-1.0, which is why only one plain function from it is used and a fallback exists. Replacing it with LanceDB, Qdrant or another store later means writing one more `VectorIndex`.

## 5. Search

```python
# retrieval/hybrid.py
class Passage(Wire): passage_id: str; chunk_id: int; file_id: str; file_name: str; location: str; text: str; score: float

class Retriever(Protocol):
    def search(self, ctx, *, workspace_id: str, query: str, file_ids: list[str] | None, k: int) -> list[Passage]: ...
```

`passage_id` is `"p" + str(chunk_id)`. `location` is the label of the first block the chunk covers. Only chunks of the current version of usable files are searched (view `v_usable_files`: live, and passing the availability check of `02-data-model.md` section 7.2).

Search is the only way an agent reaches file content. However long a file is, a translator's turn gets `TWYF_PASSAGES_PER_TURN` passages (8), and may ask for up to `TWYF_SEARCHES_PER_TURN` further searches (3) with queries of its own. So a five-thousand-page file costs a question no more than a five-page one: the vectors and keywords find the close areas, and the translator reads and cites only those.

| Mode | Steps |
|---|---|
| `keyword` | Tokens of the query (letters and digits, at least 2 characters, lower-case, minus a short stop word list) are quoted and joined with `OR` into an FTS5 query. Top 20 by `bm25(chunks_fts)` |
| `vector` | Embed the query. Top 20 from the `VectorIndex` |
| `hybrid` (default) | Both lists, fused by reciprocal rank fusion: `score = sum(1 / (60 + rank))` over the lists the chunk appears in |

Then the weight boost of section 7 is applied and the top `k` are returned (`k = TWYF_PASSAGES_PER_TURN` for a work turn). A first read does not search: it takes the first `TWYF_FIRST_READ_CHUNKS` chunks in file order (`04-agents.md` section 11).

The query for a `work` turn is the question followed by the focus. Every search is recorded as `retrieval.searched` with the query, mode and returned chunk ids.

**Graph retrieval is not part of version 1. Do not build it.** The owner plans to try GraphRAG later. The `Retriever` protocol is the slot for it: a `GraphRetriever` would find entities in the query, follow `entity_mentions` and `entity_relations` (`02-data-model.md` section 4.9) to files and passages, and fuse that list with the other two. Version 1 only creates the tables.

## 6. Citations

### 6.1 Format

A citation pins a quote to an exact place in an exact version of a file:

| Field | Meaning |
|---|---|
| `file_id`, `file_version_id` | Which file, and which version of it. A citation never moves to a newer version |
| `extraction_id` | Which text was read (parser and version, or OCR, or description) |
| `char_start`, `char_end` | The quote's offsets in `extractions.text` |
| `quote` | The exact characters at those offsets |
| `passage_start`, `passage_end`, `passage` | The surrounding text shown to people and to the verifier |
| `location` | The label of the block that contains the quote, for example `Page 3` or `Row 5` |
| `found_by_agent_id`, `turn_id` | Who found it, in which turn |

On the wire (`03-contract.md` section 2) these appear as `fileId`, `agentId`, `location`, `passage`, `quote`, and the optional `id`, `extractionId`, `start`, `end`, `page`, `fileName`, `fileVersion`.

### 6.2 Creating a citation

Agents never write offsets. They return a quote and the id of the passage they read it in. `citations/locate.py`:

```python
def create_citation(conn, ctx, *, workspace_id: str, passage_id: str, quote: str,
                    agent_id: str, turn_id: str | None) -> CitationRow:
    """Raises QuoteRejected(reason) and records citation.rejected. On success records citation.created."""
```

1. `q = normalize(quote)`. Reject with `too_short` when `len(q) < 8`, and `too_long` when `len(q) > 600`.
2. Find `q` with `str.find` in the chunk's text. If absent, find it in the whole extraction text. If absent, reject with `quote_not_found`.
3. `char_start`, `char_end` are the match's offsets in the extraction text.
4. The passage is the containing block when the block is at most 600 characters. Otherwise it is the quote widened to sentence ends on both sides, to at most 600 characters, never past the block.
5. Insert the row. Run `check` (section 6.3) on it before commit.

Matching is exact after normalisation. There is no fuzzy matching: a paraphrase presented as a quote must fail. A rejected quote fails the turn's validation, and the retry tells the agent which quote was not found.

Reusing a citation (`Quote.citation_id`) creates no new row.

### 6.3 The mechanical check

```python
# citations/check.py
def check(conn, citation_id: str) -> CheckResult:        # ok: bool, reason: str | None
```

It passes only when all of these hold:

1. The extraction exists and `sha256(extraction.text) == extraction.text_sha256`.
2. `extraction.text[char_start:char_end] == quote`.
3. `extraction.text[passage_start:passage_end] == passage`.
4. `passage_start <= char_start < char_end <= passage_end`.
5. The extraction belongs to `file_version_id`, which belongs to `file_id`, which belongs to `workspace_id`.

It runs when a citation is created, and again on every citation of every claim just before the verifier is called. A claim with a failing citation gets verdict `mechanical_fail` and is not sent to the verifier. The verifier's judgement therefore only ever concerns passages that are proven to exist in the file.

## 7. Note weights

Weights come from the `weights` lookup: `off` 0, `low` 0.5, `normal` 1, `high` 2.

| Where | Effect |
|---|---|
| Notes given to an agent | `off` notes are never given to any agent and are never searched. They stay visible to the user. The same holds for every note about a file that is deleted, `missing` or `changed` |
| Order and budget | For a `work` turn the agent gets the notes on its assigned files, ordered by weight (high first) and then newest first, up to 20 notes or 6,000 characters. When the budget runs out, `low` notes are the first left out |
| Notes from other files | Up to 5 more notes found by hybrid search over note text (`notes_fts`, `note_embeddings`), ranked by fused score times the weight's factor |
| Wording | Each note is labelled with its weight. The `work-on-files` skill tells the agent to treat `high` notes as the user's priority and `low` notes as background |
| Passage search | A chunk that overlaps a citation of a `high` note has its fused score multiplied by 1.25 |
| Planning | The orchestrator's `plan` and `assign` inputs carry each file's non-`off` notes with weights |

Three limits keep weights from weakening the citation rule:

1. A note is never evidence. A claim can only stand on citations into files. An agent that wants to rely on a note's fact reuses that note's citations.
4. Notes written about an earlier version of a file are still given to agents, with `earlier_version` true, and the `work-on-files` skill tells the agent that the file has changed since and that their facts must be found again in the current passages. Their citations cannot be reused (`02-data-model.md` section 7.2).
2. Notes of kind `interpretation` are guidance. They can steer where an agent looks and how it reads, and nothing else.
3. A weight change acts on later turns only. It is recorded per note (`note.weight_set`), and `note_weights` keeps every past value.

## 8. The context map

- **File nodes.** Every live file is a node whose id is the file id and whose label is its current name.
- **Entity nodes.** `first_read`, `work` and `direct_reply` turns may return up to 5 `EntityOut(label, type, passage_id)` each. `contextmap/service.py::add_mentions` normalises the label (lower case, whitespace collapsed), inserts or finds the `entities` row by `(workspace_id, norm_label)`, and inserts `entity_mentions(entity, file)` when new. The file is the one the passage belongs to. Labels are cut to 60 characters. Types outside the list in `02-data-model.md` section 4.9 become `other`.
- **Links.** One link per `entity_mentions` row, from the file id to the entity id.
- **During a question.** New entities and new links are collected and sent in one `context` event just before the answer, and recorded as `context.extended`. Entities and links that already existed are not sent again.
- **Reading.** `get_context_map` returns live file nodes, entities with at least one mention in a live file, and their links.
- **Not in version 1.** Nothing writes to `entity_relations`. Near-duplicate entities ("Andes" and "Andes Green Coffee") are not merged: they are two nodes.
