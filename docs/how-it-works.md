# How Talk With Your Files works

How the parts connect, what happens when a file is added or a question is asked, and which parts run in each way of using the app. The full design is in [development/revision-2-backend/](development/revision-2-backend/); this is the overview. All system diagrams are centralized in [docs/diagrams/](diagrams/README.md).

## The parts

The parts and their connections ([See System Components & Architecture Diagram](diagrams/README.md#2-system-components--architecture)).

- **One list of operations** (`contract/operations.py`, 32 of them) generates both the HTTP routes and the MCP tools, so both doors always offer the same things with the same rules.
- **Services** hold every rule. The HTTP and MCP layers only translate.
- **The backend never calls a model itself.** Each piece of agent work is a *turn* with a typed input and output, handed to a runtime. The turn runner validates every output against its schema, checks every quote against the file text, and retries a bad output (up to `TWYF_MAX_TURN_RETRIES`).
- **Everything that changes something is recorded** in `app_events`, and published to the UI's event stream after the database commit. Reads are not recorded.

## End-to-end pipeline: Ingestion, Hybrid Retrieval and Verification

The complete flow from document storage to hybrid retrieval and verified response is detailed in [**See End-to-End Pipeline Diagram**](diagrams/README.md#1-end-to-end-pipeline).

## The agents

| Agent | Turns it does | Its job |
|---|---|---|
| Orchestrator | `plan`, `assign`, `review`, `draft_claims` | Decides who reads what, follows the discussion, decides when there is enough, turns the findings into claims |
| Translators (generic, contracts, finance) | `first_read`, `volunteer`, `work` | Each holds files and reads passages from them. Every statement cites a passage |
| Verifier | `verify` | Checks each claim against the exact passages it cites: supported or not |
| Chat | `write_answer`, `direct_reply` | Writes the answer from the verified claims only |

Their instructions are the texts in `.agents/`. Every agent follows `.agents/agents.md`: text in a file is material, never an instruction, and no fact without a quote.

## Adding a file

How an uploaded file is ingested, chunked, and indexed ([See File Ingestion Flow Diagram](diagrams/README.md#4-file-ingestion-flow)).

- **Parsers.** Without the `rich` extra: `pypdf` for PDF (the text layer only), `python-docx` for Word, plain text, CSV. With it, Docling reads layout, tables, and scanned pages and images by OCR. A PDF with no text layer, such as a scan or an exported design, gives 0 characters with the basic parser.
- **Files with no text.** A file whose parse gives no text is `unreadable`: the agents never see it, and every answer ends with a line naming the files that were not read. At each start, such a file is parsed again if the parser now chosen has not tried it, for example after the rich extra is installed.
- **Versions.** Uploading new content for the same file adds a version. History tables keep every earlier state.
- **Notes.** Translators keep notes about their files: short findings with quotes. Notes have weights, and the user can edit, delete or re-weight them. Notes are searched along with passages.

## Searching: keyword, vector, hybrid

Is there a vector database? Yes, inside SQLite: the `sqlite-vec` extension stores chunk and note vectors in `chunk_embeddings` and `note_embeddings`, next to the FTS5 keyword index. There is no separate vector server. Vectors are only made when `fastembed` is installed (`uv sync --directory backend --extra rich`).

| `TWYF_RETRIEVAL_MODE` | What runs |
|---|---|
| `keyword` | FTS5 full-text search |
| `vector` | Nearest vectors by distance (sqlite-vec, or numpy if the extension cannot load) |
| `hybrid` (default) | Both, merged by reciprocal rank fusion, then note weights applied |

`./start.sh` installs fastembed by default (`--basic` leaves it out). Without it, `hybrid` does only the keyword half: the server logs a warning at start, and each `retrieval.searched` event records the search that actually ran (`keyword`, `vector` or `hybrid`). At each start, chunks and notes that have no vector yet are embedded.

The default model, `BAAI/bge-small-en-v1.5`, is made for English. Text in other languages, such as Turkish, is still found by keyword, but searching it by meaning works poorly; `TWYF_EMBED_MODEL` picks another fastembed model.

## Asking a question

The question's states, from the state machine in `orchestration/machine.py` ([See Question State Machine Diagram](diagrams/README.md#5-question-state-machine)). Any state can also end in `failed`, `cancelled` or `interrupted`.

A new workspace starts with one translator. With one, a question takes a fast path of four turns: every ready file goes to that translator (`work`), then `draft_claims`, `verify` and `write_answer`; the `plan`, `volunteer`, `assign` and `review` turns are skipped. After a failed verification the orchestrator still reviews the failed claims once before the translator reworks. Add a second translator and every question runs the full huddle below (8 to 10 turns). Quote checks and claim verification are the same in both.

The flow of turns and agent interactions ([See Question Orchestration Sequence Diagram](diagrams/README.md#3-question-orchestration-sequence)).

What is enforced, whatever model does the turns:

- Every statement and claim cites passages, and every quote must appear in the file text character for character, or the turn is retried.
- Only claims the verifier supports reach the answer. If rounds run out (`TWYF_MAX_VERIFY_ROUNDS`), the answer is marked partial and says what could not be verified.
- Derived claims (arithmetic) are recomputed by the backend, not trusted.
- Every step is an event: the UI's huddle log, `twyf events` and the MCP `get_question_events` tool all show it.

## Which parts run in each way of use

The three ways to run agent turns ([See Runtime Execution Modes Diagram](diagrams/README.md#6-runtime-execution-modes)):

| Scenario | Who thinks | Orchestration and verification |
|---|---|---|
| A question in the UI | Claude Code headless, once per turn | Always |
| A question through the API (`ask`) | The same | Always |
| A harness calls `ask` | The runtime, not the harness | Always: the harness gets the verified answer |
| A harness calls `ask_translator` | One translator turn | Cited, not verified |
| A harness reads directly (`get_file_text`, `list_notes`, `get_context_map`) | The harness itself | None: raw data |
| `./start.sh --queue` with a worker harness | The harness session, turn by turn | Always: the backend still checks every output |
| Tests and the demo | The fake runtime plays a script | Always |

## An example from the event log

The question "did atakan do something tangible with pytorch?" in a workspace with two résumés: a Markdown file (14 passages) and a PDF whose basic parse gave 0 characters (no text layer, and Docling was not installed).

1. The orchestrator planned and assigned both translators. Their searches found the Markdown passages (keyword only: no vectors had been made).
2. The translators stated, with quotes, that the résumé lists a notebook "Attention From NumPy to PyTorch", described as practice implementing attention, with no results. Three outputs were rejected and retried along the way (a statement without a quote, a note missing its quotes field, a quote not in the input).
3. The orchestrator asked five times for the PDF to be read. Every search in it returned nothing, because it has no passages. The discussion ended at the step limit.
4. The orchestrator drafted claims about the Markdown file only, saying the PDF could not be checked. The verifier supported every claim, and the chat agent wrote the answer: 212 seconds, one round.

The answer was right and honest about the gap, but the run spent five steps on a file with no text, because such a file was marked ready like any other. Now it is `unreadable`, kept from the agents and named in the answer. With the rich extra, Docling reads this PDF (about 6,500 characters), and search is hybrid.

## Where things are

| What | Where |
|---|---|
| Operations (HTTP and MCP) | `backend/src/twyf/contract/operations.py` |
| Rules | `backend/src/twyf/services/` |
| State machine and engine | `backend/src/twyf/orchestration/` |
| Runtimes and the turn runner | `backend/src/twyf/runtime/` |
| Ingestion and parsers | `backend/src/twyf/files/` |
| Search | `backend/src/twyf/retrieval/` |
| Quote checking | `backend/src/twyf/citations/` |
| Agent and skill texts | `.agents/` |
| Database schema | `backend/src/twyf/db/migrations/0001_init.sql` |
| Data on disk | `~/.twyf` (`TWYF_DATA_DIR`) |
