# 09 Decisions

Part of the revision 2 backend plan. Section 1 records what the owner decided during planning on 2026-11-15. Section 2 records the planner's choices, with what was rejected. Section 3 lists open questions. Section 4 lists sources. Section 5 checks the plan against the planning brief.

## 1. Owner decisions made during planning

These add to, and in two places change, the numbered decisions in `planning-brief.md`.

| # | Decision | Effect |
|---|---|---|
| O1 | The `.agents` protocol is the one at dotagentsprotocol.com (aj47) | `04-agents.md` section 1 |
| O2 | "New agent" creates a database row that points at a type defined in `.agents`. The app never writes into `.agents`. A speciality with no folder uses the base translator with the speciality in its prompt | `04-agents.md` section 1.4 |
| O3 | The MCP server is its own process and its tools call the HTTP API. The owner connects Claude Code to it and may use any other harness | `06-mcp.md`. See D2 and D3 |
| O4 | Retrieval combines vectors and keywords from the first version, keeps keyword-only possible, and leaves room for GraphRAG | `05-retrieval-and-citations.md` sections 4 and 5 |
| O5 | Answers may contain quoted and derived claims. Both are always cited. The verifier checks everything and the orchestrator decides from its results | `04-agents.md` sections 8 and 9 |
| O6 | **Changes brief decision 10.** Notes do not all need citations. A note that states facts must be cited. A note that is subjective guidance or reasoning need not be, for users and for translators alike. Who wrote each note is always recorded. Everything that feeds an answer is still checked by the verifier | Note kinds `summary` and `finding` require citations, `interpretation` does not (`02-data-model.md` section 7.1). Notes are never evidence (`05-retrieval-and-citations.md` section 7) |
| O7 | One built-in verifier per workspace, not creatable | `04-agents.md` section 1.4 |
| O8 | Workspaces can be created, renamed and soft-deleted. Nothing is removed from the database | Three operations (`03-contract.md` section 3) |
| O9 | "Run demo" in the UI keeps playing the mock. The real backend gets the demo as a test and a seed command, with real file contents | `10-demo-scenario.md` |
| O10 | PDFs need a good parser. Images are in scope through a transcription, a summary and interpretation guidance. Video is out. Use established free frameworks, nothing written from scratch where one exists | Docling (`05-retrieval-and-citations.md` section 2) |
| O11 | The stack is approved. The web framework is FastAPI. The owner's concern was ASGI and later serverless hosting, with local use for now | D4 |

## 2. Planner decisions

### Architecture

**D1. One operation registry generates both doors.** Routes and MCP tools are built by looping over `OPERATIONS`. *Rejected:* hand-written routes and tools kept equal by review (they drift), and generating MCP tools from the OpenAPI document (a second derivation that can lag).

**D2. The MCP server calls the HTTP API (O3).** The brief asked that the API and MCP be thin layers over one shared service layer so they cannot diverge. The owner's design puts MCP on top of HTTP instead. Both aims are met: there is still exactly one service layer, and D1 makes divergence impossible. The extra benefit is one process owning SQLite, running questions and cancellation. The cost is that the API must be running for MCP to work. *Rejected:* an in-process MCP server opening the database itself (two writers, two places where a question could run).

**D3. Agents think through a runtime boundary whose default is a queue worked over MCP.** The owner's description (the app runs on its own and saves to the database; a harness connects through MCP) reads most naturally as: the harness does the thinking by pulling work. The `queue` runtime does exactly that, and it works with any harness without the backend knowing its command line. The `command` runtime (headless CLI as a subprocess) is also built, because it is small and lets a question asked in the UI be answered with no harness sitting in a loop. *Rejected for now:* a direct model API runtime (the owner uses harnesses), and giving turns tools (D18).

**D4. FastAPI on ASGI.** ASGI is kept because the event stream and long-running agent work need it, and the MCP SDK is ASGI too. A synchronous framework would need threads and polling for the same result. Within ASGI the owner chose FastAPI. Hosting on a function-style serverless platform later needs the three changes listed in `01-architecture.md` section 5 ("Hosting later"). The plan keeps all question state in the database so that those changes stay small.

**D5. Server-sent events for the stream, explicit cancel.** *Rejected:* WebSocket (two-way, not needed, harder to replay), and cancelling on disconnect (a dropped connection would throw away paid work).

**D6. Hand-written SQL through `sqlite3`, no ORM.** The schema needs views, partial indexes, triggers and FTS5, which an ORM would only wrap. Typed row models keep types central. *Rejected:* SQLAlchemy and SQLModel.

### Data

**D7. An append-only event log beside current-state tables.** *Rejected:* full event sourcing. Rebuilding state from events would make every read a projection and every schema change an event-versioning problem, for no gain in a single-user local app. The log still gives the complete record the owner asked for, because every write and its event share one transaction.

**D8. The agent event stream is a column of the event log** (`wire_json`), not a second table. One write, nothing to keep in step.

**D9. Plain numbered SQL migrations.** *Rejected:* Alembic, which needs SQLAlchemy.

**D10. Type 2 history in `_versions` tables; immutable rows for notes, citations, messages, claims and turns.** Table by entity in `02-data-model.md` section 2.

**D11. Definitions are snapshotted by content hash, and a child's hash includes its parent's and its skills'.** So one id on a turn pins the whole prompt. *Rejected:* versioning by file modification time (not content), and by git commit (the working tree may be uncommitted).

**D12. Files are identified by SHA-256.** Same name and content: nothing new. Same name, new content: a new version. *Rejected:* always creating a new file (loses the link between versions).

**D13. Delete is soft everywhere, and only workspaces can be deleted in version 1 (O8).**

**D14. Reads are not recorded.** The brief asks for every action. Listing files changes nothing and would bury the log. Every state change and every agent call is recorded.

### Contract

**D15. Pydantic is the source; JSON Schema and TypeScript are generated; `types.ts` stays hand-written and is compared by the compiler.** *Rejected:* a schema file as the source generating both sides (the owner prefers Pydantic, and Python would lose validators), and replacing `types.ts` with the generated file (it is the file people read, and the brief asks to prefer additions).

**D16. Every change to `types.ts` is an addition.** `uploadFile` gains an optional `data` field rather than a new required one, so the mock is untouched.

**D17. `Citation.n` is local to the list that carries it.** Stable within a question's huddle, renumbered from 1 in the answer.

### Agents

**D18. Turns are pure: prompt and JSON in, JSON out, no tools.** A translator asks for more reading through a `searches` field and the backend runs it, up to three times. This keeps the runtime boundary the same for a script, a harness, a CLI or an API; makes every turn replayable; and means text in a file cannot trigger an action. *Rejected:* giving agents search tools through each provider's tool-calling.

**D19. Claims are drafted before the answer, not extracted from it.** The orchestrator writes atomic claims, the verifier checks them, and the chat agent may only write from claims that passed. Mechanical guards stop a new number entering the prose. *Rejected:* writing the answer first and splitting it into claims, which is the least reliable step in that design.

**D20. A derived claim is cited through the claims it rests on, and its arithmetic is recomputed by the backend with `simpleeval`.** The verifier judges whether the inputs and the reasoning are right.

**D21. The verifier sees only claims and their passages.** Not the question, the discussion or the notes, so it cannot be led.

**D22. A claim already verified is not verified again in a later round** when its text, kind, citations and inputs are identical. The brief says the verifier checks everything that was shared and used. That still holds: every claim in the answer has a `supported` verdict. This avoids paying twice for the same check.

**D23. A round is one huddle plus one verification; default limit 3.** After the limit only supported claims are written, with the rest listed as unverified.

**D24. The state machine is a pure function and the engine executes its commands.** So every transition can be tested without a database or a model.

**D25. Direct chat with a translator gets the mechanical check but not the verifier,** following brief decision 14.

**D26. A first read runs after each upload (configurable).** It is where a file's cited summary note and first entities come from, matching the demo's "earlier read". *Cost:* one turn per upload.

**D27. Agent conventions beyond the protocol sit under a `twyf` key in `config.json`.** The protocol leaves kinds, inheritance and per-agent skill lists open. The global `~/.agents` layer is not read, so behaviour depends only on the repository.

### Retrieval

**D28. Vectors stay in SQLite as BLOBs, searched exactly with `sqlite-vec`, with a numpy fallback.** The owner had not heard of `sqlite-vec` and asked whether another vector database would be better. For one user on one machine, a separate vector store adds a second thing to keep in step with versions, soft deletes and workspaces, and gives speed that is not needed below roughly 100,000 chunks per workspace. `sqlite-vec` is pre-1.0, so only one function of it is used and a fallback exists. The `VectorIndex` protocol is the place to add LanceDB or Qdrant when scale asks for it. *Rejected for version 1:* LanceDB, Chroma, Qdrant local mode, FAISS.

**D29. Hybrid search by reciprocal rank fusion of FTS5 BM25 and cosine similarity.** A standard method with no tuning. GraphRAG has a reserved slot (`Retriever` protocol, `entity_relations` table) and is not built.

**D30. Local embeddings with `fastembed` and `BAAI/bge-small-en-v1.5`.** Free, CPU-only, no PyTorch. The model is English-centred; a multilingual model is a one-line change and a re-embed.

**D31. Docling for rich parsing, with basic parsers always installed.** Docling is MIT, handles layout, tables, OCR and images, and keeps page positions. PyMuPDF was rejected for its AGPL licence against this project's MIT licence. MarkItDown was rejected because it drops positions. Tests use the basic parsers so they need no model download.

**D32. Quotes must match exactly after normalisation.** No fuzzy matching, because a paraphrase passed off as a quote is the failure this system exists to prevent.

**D33. Our own small chunker over blocks,** because chunk offsets must index the canonical text exactly, for every parser.

**D34. Notes are never evidence.** Weights change what agents see and in what order. They cannot make an uncited fact acceptable.

### Tooling

**D35. Python 3.13 or newer, `uv`, `ruff`, `pyright` strict, `pytest`, 90% coverage overall and 100% on the state machine, claims, arithmetic and citation code.**

## 3. Open questions for the owner

None blocks the implementation. Each has the behaviour the plan uses until the owner says otherwise.

1. **Parity gap.** `list_events`, `get_file_text` and `get_question_events` exist in the API and MCP but have no UI. The parity rule asks for one. Planned behaviour: leave them without UI in version 1.
2. **True erase.** Soft delete keeps everything. If a file must really be removed (for example personal data uploaded by mistake), a purge operation is needed that breaks the "nothing is removed" rule on purpose. Planned behaviour: none in version 1.
3. **First read on upload** costs one agent turn per file. Planned behaviour: on, switchable with `TWYF_FIRST_READ`.
4. **Other deletes and renames** (files, agents, notes, sessions). The schema is ready. Planned behaviour: not in version 1.
5. **Language.** The default embedding model is English-centred. Planned behaviour: keep it until the owner names other languages.
6. **Conversation memory.** The chat agent and orchestrator receive the last 6 messages of the session. Planned behaviour: that fixed window.
7. **Entity merging** in the context map ("Andes" and "Andes Green Coffee" are two nodes). Planned behaviour: no merging.
8. **Worker safety.** With the `queue` runtime the harness has its own tools. `06-mcp.md` section 6 asks the owner to run it with tools restricted. This cannot be enforced by the backend.

## 4. Sources

Read on 2026-11-15.

| Topic | Source | What was taken from it |
|---|---|---|
| `.agents` protocol | https://dotagentsprotocol.com and https://github.com/aj47/dotagentsprotocol-website | Folder layout, `agent.md` and `skill.md` frontmatter fields, `config.json` keys, merge layers, frontmatter format. It calls itself a draft, dated 2026-02-24, with no version number. It gives no schema for `models.json` and does not define allowed values of `role` or `connection-type` |
| Another `.agents` convention, not used | https://github.com/bgreenwell/dotagents | Has `personas/` and `skills/` but no agent definition format |
| MCP specification | https://modelcontextprotocol.io/specification/2026-07-28/changelog | Revision 2026-07-28: stateless, no sessions or initialize handshake, Streamable HTTP, HTTP+SSE deprecated, sampling deprecated |
| MCP Python SDK | https://py.sdk.modelcontextprotocol.io/migration/ and a local run of `mcp` 2.3.0 | `MCPServer`, `add_tool`, `@resource`, `@prompt`, `run(transport=...)`, `streamable_http_app(stateless_http=...)`, in-memory `Client(server)` |
| Vectors in SQLite | https://github.com/asg017/sqlite-vec and a local run of `sqlite-vec` 0.1.9 on Python 3.13 and 3.14 | Loads into the standard `sqlite3` module; pre-1.0; exact search |
| Alternatives considered | https://github.com/1yefuwang1/vectorlite, https://github.com/sqliteai/sqlite-vector, https://sqlite.org/vec1/doc/trunk/doc/vec1.md | Approximate search options, not needed at this scale |
| Docling | https://pypi.org/project/docling/ and https://arxiv.org/abs/2408.09869 | MIT licence; PDF, DOCX, images; layout, tables, OCR; page provenance. Its API was not run for this plan |

Versions seen installed together on Python 3.13 and 3.14: `mcp` 2.3.0, `pydantic` 2.14.3, `uvicorn` 0.54.0, `sqlite-vec` 0.1.9, `fastembed` 0.9.1, `pypdf` 7.1.0, `python-docx` 1.2.0, `httpx` 0.28.1, `reportlab` 5.1.0. FastAPI and Docling were not installed for this plan.

## 5. Check against the planning brief

### Numbered decisions

| Brief decision | Where it is honoured |
|---|---|
| 1 Workspaces isolated | `02-data-model.md` section 1 rule 4; `test_workspace_isolation` |
| 2 Files independent of agents, never changed | `02-data-model.md` sections 4.3 and 7.2; no column links a file to an agent |
| 3 Translator pool, pairing per question | `04-agents.md` section 4; `assignments` table |
| 4 Notes are the only link | `02-data-model.md` section 4.6 |
| 5 Weights | `05-retrieval-and-citations.md` section 7; `note_weights` |
| 6 Anyone can read earlier notes | `list_notes`; notes in every agent input |
| 7 The record kept | Blobs, messages and notes with citations are immutable and never removed |
| 8 Parity | `06-mcp.md` section 2; `test_parity`; gap listed in section 3 item 1 |
| 9 One local user, rows carry user and workspace | `users`, `workspace_id` on every table, `user_id` on every event |
| 10 Translator output based on citations | Statements always. Notes as changed by O6 |
| 11 Every claim in an answer cited | `04-agents.md` sections 8 and 10 |
| 12 Demo summary notes cited | `10-demo-scenario.md` section 3 |
| 13 to 16 Verifier | `04-agents.md` section 9 |
| 17 Round limit, only verified claims after it | `04-agents.md` section 5.3 |
| 18 `.agents` protocol, cited, gaps stated | `04-agents.md` section 1; section 4 above |
| 19 to 21 Translator as base type, subtypes, other kinds later | `04-agents.md` sections 1.3 and 1.4 |
| 22 Python, one contract with TypeScript | `03-contract.md` section 1 |
| 23 SQLite | `02-data-model.md` |
| 24 Provider-agnostic runtime boundary | `04-agents.md` section 6 |
| 25 MCP server | `06-mcp.md` |
| 26 Backend agnostic of the frontend | `01-architecture.md` section 4 |
| 27 Frontend features and demo keep working | `03-contract.md` sections 6 and 7; only additions |
| 28 Every action recorded with its source | `02-data-model.md` sections 3 and 5; `07-test-plan.md` section 7. Reads excepted (D14) |
| 29 Everything versioned | `02-data-model.md` sections 4.4 and 7.4 |
| 30 Slowly changing dimensions, lookups, linking tables | `02-data-model.md` sections 2 and 4.1 |
| 31 Types central | Pydantic contract, typed turn models, pyright strict |
| 32 Tests cover everything | `07-test-plan.md` |

### Items under "What you must reason about"

| Item | Answered in |
|---|---|
| One source of truth for types, drift check | `03-contract.md` section 1 |
| Transport, event stream, cancel | `03-contract.md` section 4.2 |
| Contract additions, every change to `types.ts` | `03-contract.md` sections 4.1 and 6 |
| Frontend work | `03-contract.md` section 7; tasks F1 to F7 |
| Full SQLite schema | `02-data-model.md` section 4 |
| Recording approach, taxonomy, actor and source, identifiers | `02-data-model.md` sections 3 and 5 |
| Versioning of agents, skills, prompts | `02-data-model.md` section 7.4 |
| Slowly changing dimension per entity | `02-data-model.md` section 2 |
| Raw file storage, duplicates, re-uploads | `02-data-model.md` section 7.2 |
| Meaning of delete | `02-data-model.md` section 7.3 |
| Migrations | `02-data-model.md` section 8 |
| Parsing, chunking, embeddings, vectors | `05-retrieval-and-citations.md` sections 2 to 4 |
| Locating a citation | `05-retrieval-and-citations.md` section 6 |
| Mechanical citation check | `05-retrieval-and-citations.md` section 6.3 |
| Weights in retrieval and answers | `05-retrieval-and-citations.md` section 7 |
| Context map | `05-retrieval-and-citations.md` section 8 |
| Orchestrator state machine | `04-agents.md` section 5 |
| What the verifier receives and returns | `04-agents.md` section 9 |
| How claims are extracted | `04-agents.md` section 8; D19 |
| Volunteering and calling | `04-agents.md` section 4 |
| Runtime boundary, scripted fake | `04-agents.md` section 6 |
| `.agents` layout | `04-agents.md` section 1 |
| MCP tools, resources, prompts, transport | `06-mcp.md` |
| Untrusted content | `01-architecture.md` section 9; `test_injection_is_inert` |
| Privacy | `01-architecture.md` section 10 |
| Failure handling | `01-architecture.md` section 8 |
| Concurrency | `01-architecture.md` section 7 |
| Cost and performance | `01-architecture.md` section 11 |
| Observability | `01-architecture.md` section 11 |
| Configuration and secrets | `01-architecture.md` section 6 |
| Answer quality evaluation | `07-test-plan.md` section 8 |
| Layout, dependencies, linting, type checking, CI | `01-architecture.md` sections 3, 4 and 12 |

### A split that differs from the brief

One document was added: `10-demo-scenario.md`. The demo's file contents, seed data and scripted turns are needed by four tasks and would have swamped the test plan.
