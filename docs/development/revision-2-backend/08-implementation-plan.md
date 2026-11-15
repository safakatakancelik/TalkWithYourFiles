# 08 Implementation plan

Part of the revision 2 backend plan. Ordered tasks for the implementer. Tasks B01 to B38 build the backend. Tasks F1 to F8 change the frontend.

## How to use this plan

- Do the tasks in order. After every task the project runs and all tests pass.
- Before a task, read only the sections it lists under **Read**. All documents are in `docs/development/revision-2-backend/`.
- Write the tests named under **Tests** first, from their pass conditions in `07-test-plan.md`, then the code.
- A task is done when its **Done when** command succeeds. Unless it says otherwise, that command is run from `backend/` and is followed by the full check:
  `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest`
- Do not add features, options or abstractions that no document names. `09-decisions.md` section 3 lists what is deliberately not in version 1: build none of it. The documents have no open questions. If a document and the code disagree, or something needed is missing, stop and ask the owner.
- Never import from `frontend/` in the backend. Never write a route or an MCP tool by hand: both come from `OPERATIONS`.
- Commit after each task with the task id in the message.
- **OWNER REVIEW** lines are stopping points. Stop there and wait.

Conventions used in every task: all Python lives under `backend/src/twyf/`, all tests under `backend/tests/`. Test modules mirror source modules: `src/twyf/files/chunker.py` is tested by `tests/unit/files/test_chunker.py`.

---

## Stage 1: foundation, contract and schema

### B01 Scaffold the backend
- **Goal:** an installable, empty package with tooling.
- **Read:** `01-architecture.md` sections 3, 4, 12.
- **Files:** `backend/pyproject.toml` (project `twyf`, Python `>=3.13`, src layout, script `twyf = "twyf.cli:main"`; dependencies `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `httpx`, `mcp>=2,<3`, `sqlite-vec`, `numpy`, `pypdf`, `python-docx`, `simpleeval`, `python-multipart`; extra `rich = ["docling", "fastembed"]`; dev group `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `pyright`, `jsonschema`, `reportlab`; pytest `asyncio_mode = "auto"`, `addopts = '-m "not models"'`, marker `models`; ruff line length 120; pyright strict on `src`), `src/twyf/__init__.py` (`__version__ = "2.0.0a1"`), `src/twyf/cli.py` (`main()` with `argparse` subcommands that print "not implemented" for now), `tests/unit/test_smoke.py`, `.github/workflows/ci.yml` with the `backend` job only, and add `backend/.venv/`, `.twyf/`, `__pycache__/`, `.coverage`, `coverage.json` to the root `.gitignore`.
- **Tests:** `test_smoke`: `import twyf` works and `twyf --help` exits 0.
- **Done when:** `uv sync && uv run pytest tests/unit/test_smoke.py`.
- **Depends on:** nothing.

### B02 Settings, ids and clock
- **Goal:** typed configuration and two helpers every module uses.
- **Read:** `01-architecture.md` section 6. `02-data-model.md` section 1.
- **Files:** `config.py`, `ids.py`, `clock.py`, tests for each.
- **Signatures:** `class Settings(BaseSettings)` with one field per row of the settings table and `model_config = SettingsConfigDict(env_prefix="TWYF_", env_file=".env")`; `Settings.behaviour_json() -> str` (sorted JSON of the non-secret settings that shape behaviour: runtime, rounds, steps, retries, timeout, parser, embedder, retrieval mode, first read). `ids.new_id(prefix: str) -> str`. `clock.now() -> str`, `clock.freeze(value: str | None) -> None`.
- **Tests:** defaults match the table; environment variables override; `new_id("f")` matches `^f_[0-9a-f]{32}$`; `now()` ends in `Z`, has milliseconds, and returns the frozen value when frozen.
- **Done when:** `uv run pytest tests/unit/test_config.py tests/unit/test_ids.py tests/unit/test_clock.py`.
- **Depends on:** B01.

### B03 Wire models
- **Goal:** every wire type as a Pydantic model.
- **Read:** `03-contract.md` sections 1 ("Pydantic conventions") and 2. `frontend/src/backend/types.ts`.
- **Files:** `contract/__init__.py`, `contract/base.py` (`Wire`, `Opt`), `contract/models.py`, `tests/unit/contract/test_models.py`.
- **Signatures:** the models of the table in section 2, with exactly those names and fields. `Weight = Literal["off","low","normal","high"]`, `FileType = Literal["pdf","docx","csv","md","txt","image","other"]`. Constants `ORCHESTRATOR = "orchestrator"`, `VERIFIER = "verifier"`, `USER = "user"`. Helper `dump(model: Wire) -> dict` = `model_dump(mode="json", by_alias=True, exclude_none=True)`.
- **Tests:** `test_models_roundtrip`, `test_optional_fields_omitted` (`07-test-plan.md` section 2, Contract).
- **Done when:** `uv run pytest tests/unit/contract/test_models.py`.
- **Depends on:** B01.

### B04 Agent events and turn models
- **Goal:** the event union and every turn's input and output model.
- **Read:** `03-contract.md` section 4.1. `04-agents.md` sections 3, 8, 9.1, 9.2, 10 (the `Segment` model) and 6.3 (`TurnOffer`).
- **Files:** `contract/events.py`, `contract/turns.py`, tests.
- **Signatures:** one model per event type, each with `type: Literal[...]`; `AgentEvent = Annotated[Union[...], Field(discriminator="type")]`; `parse_event(data: dict) -> AgentEvent`. In `turns.py`: the shared models, `PlanInput/PlanOutput`, `VolunteerInput/Output`, `AssignInput/Output`, `WorkInput/Output`, `ReviewInput/Output`, `DraftClaimsInput/Output`, `ClaimOut`, `ClaimIn`, `VerifyInput/Output`, `VerdictOut`, `CitationVerdictOut`, `WriteAnswerInput/Output`, `Segment`, `DirectReplyInput/Output`, `FirstReadInput/Output`, `DescribeImageInput/Output`, `TurnOffer`, `Usage`; and `TURN_MODELS: dict[str, tuple[type[Wire], type[Wire], list[str]]]` mapping each turn type to its input model, output model and skill ids (table in `04-agents.md` section 3). Every input model also has `previous_error: Opt[str] = None`.
- **Tests:** `test_agent_event_union`; each turn output model validates a sample and rejects an extra field.
- **Done when:** `uv run pytest tests/unit/contract`.
- **Depends on:** B03.

### B05 Operation registry, errors and service stubs
- **Goal:** the full list of operations, with every handler present as a stub.
- **Read:** `03-contract.md` section 3. `01-architecture.md` section 2.
- **Files:** `contract/operations.py`, `services/errors.py`, `services/__init__.py`, one stub module per service named in the handler strings (`workspaces.py`, `files.py`, `agents.py`, `notes.py`, `sessions.py`, `questions.py`, `events.py`, `turns.py`, `contextmap.py`), `recording/context.py`, tests.
- **Signatures:** `Operation` as in section 3; `OPERATIONS: list[Operation]` with all 32 rows of the table; one input model per operation named `<OperationNameInCamel>Input` (for example `UploadFileInput(ws: str)`, `SetNoteWeightInput(ws, note_ids, weight)`); `get_operation(name) -> Operation`; `resolve_handler(op) -> Callable`. `class ServiceError(Exception)` with `code`, `message`, `details`, and `HTTP_STATUS: dict[str, int]`. `@dataclass(frozen=True) class RequestContext: actor_id: str; source: str; user_id: str; request_id: str; client: str | None = None; cause_event_id: int | None = None`, with `ctx.caused_by(event_id) -> RequestContext` and `ctx.as_actor(actor_id, source="internal") -> RequestContext`. Every handler has the signature `def <name>(ctx: RequestContext, input: <InputModel>) -> <output>` and for now raises `ServiceError("internal", "not implemented")`. Stream handlers are `async def ... -> AsyncIterator[AgentEvent]`.
- **Tests:** `test_operations_unique_and_resolvable`.
- **Done when:** `uv run pytest tests/unit/contract/test_operations.py`.
- **Depends on:** B04.

### B06 Contract export
- **Goal:** `contract/schema.json` generated and guarded.
- **Read:** `03-contract.md` section 1. `07-test-plan.md` section 6.
- **Files:** `contract/export.py`, `cli.py` (subcommand `export-contract`), `contract/schema.json` at the repository root (generated, committed), `tests/fixtures/samples.json`, tests. Add the `contract` job to CI with only its Python half for now.
- **Signatures:** `build_schema() -> dict` returning `{"$schema": ..., "title": "twyf contract", "$defs": {<every wire model, event and operation input model>}, "operations": [{name, method, path, input, output, kind, backendMethod}]}`, built with `pydantic.json_schema.models_json_schema(..., mode="serialization", by_alias=True)`; `write_schema(path: Path) -> None` writing sorted keys, two-space indent and a final newline.
- **Tests:** `test_schema_is_current`, `test_samples_validate`.
- **Done when:** `uv run twyf export-contract && git diff --exit-code ../contract && uv run pytest tests/unit/contract`.
- **Depends on:** B05.

### B07 Database, migrations and the schema
- **Goal:** the whole schema, applied by a migration runner.
- **Read:** all of `02-data-model.md`. `01-architecture.md` section 7.
- **Files:** `db/connection.py`, `db/migrate.py`, `db/migrations/0001_init.sql`, tests under `tests/unit/db/`, and the `conn` fixture in `tests/conftest.py`.
- **Signatures:** `connect(path: Path) -> sqlite3.Connection` (sets `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`, loads `sqlite-vec` and remembers on the connection whether that worked); `transaction(conn) -> ContextManager[sqlite3.Connection]` (`BEGIN IMMEDIATE`, commit, rollback on error); `migrate(path: Path) -> list[int]` returning the versions applied. `0001_init.sql` holds the statements of section 4 in order, then the seed rows of section 6, with one `event_types` row for every code in section 5 (expand the rows written with `/` into separate codes).
- **Tests:** the six tests under "Database" in `07-test-plan.md` section 2.
- **Done when:** `uv run pytest tests/unit/db`.
- **Depends on:** B02.

> **OWNER REVIEW 1.** The owner reads `contract/schema.json` and `0001_init.sql` against `03-contract.md` and `02-data-model.md`. Changes after this point cost more.

---

## Stage 2: recording, definitions and plain data

### B08 Recorder, event broker and the event log reader
- **Goal:** every later task can record an action in one call.
- **Read:** `02-data-model.md` sections 3 and 5. `03-contract.md` section 4.2 (last paragraph). `01-architecture.md` section 6 ("Secrets").
- **Files:** `recording/recorder.py`, `recording/broker.py`, `db/repos/events.py`, `services/events.py` (real `list_events`), tests, and the `ctx` and `events` fixtures.
- **Signatures:** `record(conn, ctx: RequestContext, event_type: str, *, workspace_id: str | None = None, session_id=None, question_id=None, round_id=None, turn_id=None, entity_type=None, entity_id=None, payload: dict | None = None, wire: AgentEvent | None = None, definition_version_id: int | None = None, config_version_id: int | None = None) -> int` (inserts inside the caller's transaction, returns the event id, and registers the event for publishing when the transaction commits); `class EventBroker: subscribe(question_id) -> AsyncIterator[tuple[int, AgentEvent]]; publish(question_id, event_id, event); close(question_id)`. `events.list(conn, *, workspace_id, question_id, event_type, after, limit) -> list[EventRecord]`; `events.wire_events(conn, question_id, after=0) -> list[tuple[int, AgentEvent]]`.
- **Tests:** the five tests under "Recording".
- **Done when:** `uv run pytest tests/unit/recording`.
- **Depends on:** B05, B07.

### B09 Agent definitions: folder skeleton, loader, snapshots
- **Goal:** `.agents` exists and is versioned into the database.
- **Read:** `04-agents.md` section 1. `02-data-model.md` sections 4.4 and 7.4.
- **Files:** the `.agents` folder at the repository root with every file in section 1.1. Each `agent.md` and `skill.md` gets correct frontmatter and a one-paragraph body for now (B23 writes the real text). Each `config.json` gets its `twyf` block. `agents/definitions.py`, `db/repos/definitions.py`, `db/repos/versioned.py`, tests.
- **Signatures:** `versioned.set_version(conn, table: str, key_col: str, key: str | int, values: dict) -> int` (closes the current row and inserts the next version; used by every type 2 table) and `versioned.as_of(conn, table, key_col, key, at: str) -> sqlite3.Row | None`. `parse_frontmatter(text: str) -> tuple[dict[str, str], str]`. `load_folder(path: Path) -> LoadedAgents` (dataclasses `LoadedAgent(slug, kind, frontmatter, body, config, extends, specialty, skills, source_path)`, `LoadedSkill(slug, frontmatter, body, source_path)`, plus `rules: str` from `agents.md`). `sync(conn, ctx, settings) -> SyncResult` (lists of new definition and skill version ids). `resolve(conn, kind: str, specialty: str) -> int` (a `definition_id`). `current_version(conn, definition_id) -> DefinitionVersion`. `sync_config(conn, ctx, settings) -> int`.
- **Tests:** the first six tests under "Agents and definitions", and `test_type2_history` for definitions and config.
- **Done when:** `uv run pytest tests/unit/agents`.
- **Depends on:** B08.

### B10 Workspaces and agents
- **Goal:** the first real operations.
- **Read:** `02-data-model.md` sections 4.2, 4.5, 6 (last paragraph), 7.3 (rows for workspaces and agents). `03-contract.md` section 2 (mapping rules).
- **Files:** `db/repos/workspaces.py`, `db/repos/agents.py`, `services/workspaces.py`, `services/agents.py`, `services/mapping.py`, tests, and the `ws` fixture.
- **Signatures:** `workspaces.list(ctx, input) -> list[Workspace]`, `create(ctx, CreateWorkspaceInput) -> Workspace` (also creates the orchestrator, verifier, chat agent and two generic translators, each with an `actors` row and an `agent.created` event), `rename`, `delete`, `require(conn, ws_id) -> None` raising `not_found`. `agents.list(ctx, input) -> list[Agent]` (translators only), `agents.create(ctx, CreateAgentInput) -> Agent`, `agents.rename(ctx, RenameAgentInput) -> Agent`, `agents.delete(ctx, DeleteAgentInput) -> None` (both for translators only; the `conflict` rule for a running huddle is added in B28), `agents.builtin(conn, ws_id, kind) -> AgentRow`. `mapping.actor_to_wire(conn, ws_id, actor_id) -> str` applying the constants rule.
- **Tests:** repository tests (`test_create_and_get`, `test_workspace_isolation`, `test_type2_history`, `test_soft_delete_hidden`) for both, and service tests for each function.
- **Done when:** `uv run pytest tests/unit/services/test_workspaces.py tests/unit/services/test_agents.py tests/unit/db/repos`.
- **Depends on:** B09.

### B11 File references: upload, reference by path, availability
- **Goal:** files are referred to, versioned and checked. Parsing comes in B13.
- **Read:** `02-data-model.md` sections 4.3, 7.2 and 7.3 (row `delete_file`). `01-architecture.md` section 9 ("Uploads", "References by path"). `05-retrieval-and-citations.md` section 1 (file types). `09-decisions.md` O16.
- **Files:** `files/store.py`, `files/types.py`, `files/integrity.py`, `files/jobs.py`, `db/repos/files.py`, `services/files.py` (`upload`, `reference`, `list`, `delete`), tests, and the `jobs` fixture.
- **Signatures:** `store.save(data_dir: Path, stream: BinaryIO, max_bytes: int) -> tuple[str, int, Path]` (sha256, size, path under `files/`; raises `ServiceError("too_large")`; never overwrites an existing file); `integrity.sha256_of(path: Path) -> str`; `integrity.verify(conn, ctx, file_version_id: str) -> str`; `integrity.verify_workspace(conn, ctx, workspace_id: str) -> list[tuple[str, str]]` (file id and state for every file that is not `ok`); `types.file_type(name: str) -> FileType`; `class Jobs(Protocol): submit(fn: Callable[[], None]) -> None; join() -> None`, with `InlineJobs` and `ThreadJobs`; `files.upload(ctx, input: UploadFileInput, *, name: str, stream: BinaryIO, file_id: str | None = None) -> FileItem`; `files.reference(ctx, input: ReferenceFileInput, *, file_id: str | None = None) -> FileItem`; `files.list(ctx, input) -> list[FileItem]` (runs `verify_workspace` first); `files.delete(ctx, DeleteFileInput) -> None`. `upload` and `reference` submit `files.ingest.ingest` to `Jobs` when that module exists; until B13 the status stays `processing`. No function in the backend opens file content for writing, and none removes it.
- **Tests:** `test_store_named_by_hash`, `test_store_rejects_oversize`, `test_upload_cases`, `test_reference_file`, `test_content_never_written`, the five `test_verify_*` tests, `test_jobs`, `test_file_type_from_extension`, repository tests for files.
- **Done when:** `uv run pytest tests/unit/files tests/unit/services/test_files.py`.
- **Depends on:** B10.

### B12 Normalisation and the basic parsers
- **Goal:** text, Markdown, CSV, PDF and DOCX become blocks.
- **Read:** `05-retrieval-and-citations.md` section 2.
- **Files:** `citations/normalize.py`, `files/parsers/base.py`, `text.py`, `csv.py`, `pdf_basic.py`, `docx_basic.py`, `files/parsers/__init__.py` (`pick_parser(settings, file_type) -> Parser | None`), small fixture files under `tests/fixtures/parsing/` (create the PDF and DOCX with a script kept in `backend/scripts/make_parsing_fixtures.py`), tests.
- **Signatures:** `normalize(text: str) -> str`; `ParsedBlock`, `ParsedDocument`, `Parser` as in section 2.
- **Tests:** `test_normalize`, the five parser tests.
- **Done when:** `uv run pytest tests/unit/files/parsers tests/unit/citations/test_normalize.py`.
- **Depends on:** B01.

### B13 Extractions, chunks and the ingestion pipeline
- **Goal:** an uploaded file becomes searchable text.
- **Read:** `05-retrieval-and-citations.md` sections 1, 2 ("Canonical text") and 3. `02-data-model.md` section 4.3.
- **Files:** `files/chunker.py`, `files/ingest.py`, `db/repos/extractions.py`, tests. `services/files.py` gains `get_text` and the real `status`.
- **Signatures:** `chunk(blocks: list[BlockSpan]) -> list[ChunkSpan]` (`BlockSpan(char_start, char_end, text)`, `ChunkSpan(char_start, char_end, text)`); `build_extraction(doc: ParsedDocument) -> tuple[str, list[BlockRow]]`; `ingest(conn_factory, ctx, settings, file_version_id: str) -> None` (run `integrity.verify` and stop if the file is not `ok`; record `file.ingest_started`; parse; store extraction and blocks; chunk; fill `chunks` and `chunks_fts`; record the events; embedding is added in B14); `pending_ingestion(conn) -> list[str]` (live file versions with no extraction); `files.get_text(ctx, GetFileTextInput) -> FileText`.
- **Tests:** `test_canonical_text_offsets`, `test_parse_failure_marks_unreadable`, `test_chunker_rules`, `test_unusable_file_hidden_from_agents` (the search part is added in B15).
- **Done when:** `uv run pytest tests/unit/files`.
- **Depends on:** B11, B12.

### B14 Embedders and vector indexes
- **Goal:** vectors are stored and searched.
- **Read:** `05-retrieval-and-citations.md` section 4. `02-data-model.md` section 4.3 (embedding tables).
- **Files:** `retrieval/embedder.py` (`HashEmbedder`, `NullEmbedder`, `get_embedder(settings)`; `FastEmbedEmbedder` comes in B37), `retrieval/vector_index.py` (`SqliteVecIndex`, `NumpyIndex`, `get_index(conn)`), `db/repos/embeddings.py`, `retrieval/reembed.py`, tests. `files/ingest.py` embeds chunks after chunking, 64 at a time, one transaction per batch.
- **Signatures:** as in section 4, plus `pack(vector: list[float]) -> bytes`, `unpack(blob: bytes) -> list[float]`, `embeddings.model_id(conn, embedder) -> int`, `reembed(conn_factory, ctx, embedder, batch: int = 64) -> int` (the number of vectors written).
- **Tests:** `test_hash_embedder`, `test_vector_index_contract`, `test_ingest_batches`, `test_reembed_for_new_model` (its note part is added in B17).
- **Done when:** `uv run pytest tests/unit/retrieval/test_embedder.py tests/unit/retrieval/test_vector_index.py`.
- **Depends on:** B13.

### B15 Search
- **Goal:** keyword, vector and hybrid retrieval of passages.
- **Read:** `05-retrieval-and-citations.md` section 5.
- **Files:** `retrieval/keyword.py`, `retrieval/hybrid.py`, tests.
- **Signatures:** `keyword.fts_query(text: str) -> str`; `keyword.search(conn, *, workspace_id, query, file_ids, k) -> list[tuple[int, float]]`; `class HybridRetriever` implementing `Retriever`, constructed with `(settings, embedder, index)`; `first_chunks(conn, *, workspace_id, file_id, k) -> list[Passage]`. Every query reads files through the view `v_usable_files`. The weight boost is a parameter `boost: Callable[[int], float] | None` for now.
- **Tests:** `test_keyword_search`, `test_hybrid_fusion`, `test_only_current_versions_searched`.
- **Done when:** `uv run pytest tests/unit/retrieval`.
- **Depends on:** B14.

### B16 Citations: locate and check
- **Goal:** the only way a citation can come into being, and the mechanical check.
- **Read:** `05-retrieval-and-citations.md` section 6. `02-data-model.md` sections 4.6 and 7.1.
- **Files:** `citations/locate.py`, `citations/check.py`, `db/repos/citations.py`, tests.
- **Signatures:** `create_citation(...)` and `check(...)` as in sections 6.2 and 6.3; `class QuoteRejected(Exception): reason: str`; `@dataclass CheckResult: ok: bool; reason: str | None`; `citations.to_wire(conn, citation_id, n: int) -> Citation`.
- **Tests:** the six tests under "Citations" except `test_normalize`.
- **Done when:** `uv run pytest tests/unit/citations` with 100% coverage of `citations/` (`--cov=twyf.citations --cov-fail-under=100`).
- **Depends on:** B13.

### B17 Notes and weights
- **Goal:** notes with the citation rule, weights and their effect on what agents get.
- **Read:** `02-data-model.md` sections 4.6, 7.1 and 7.3 (rows `edit_note`, `delete_note`). `05-retrieval-and-citations.md` section 7.
- **Files:** `db/repos/notes.py`, `services/notes.py`, `retrieval/weights.py`, tests. `retrieval/hybrid.py` uses the boost from `weights.py`.
- **Signatures:** `notes.list(ctx, input) -> list[Note]`; `notes.add(ctx, AddNoteInput) -> Note` (user note, kind `interpretation`); `notes.create_agent_note(conn, ctx, *, workspace_id, file_id, author_id, kind, text, citation_ids: list[str], numbers: list[int], question_id, turn_id) -> NoteRow` (enforces section 7.1; fills `notes_fts` and `note_embeddings`); `notes.set_weight(ctx, SetNoteWeightInput) -> None`; `notes.edit(ctx, EditNoteInput) -> Note` (user notes only; a new `note_versions` row; replaces the note's `notes_fts` row and embedding); `notes.delete(ctx, DeleteNoteInput) -> None`; `weights.notes_for_turn(conn, *, workspace_id, file_ids, query) -> list[NoteIn]`; `weights.passage_boost(conn, workspace_id) -> Callable[[int], float]`.
- **Tests:** repository tests for notes, service tests, `test_weight_off_excluded`, `test_note_order_and_budget`, `test_high_note_boosts_passage`, and the note parts of `test_unusable_file_hidden_from_agents` and `test_reembed_for_new_model`.
- **Done when:** `uv run pytest tests/unit/services/test_notes.py tests/unit/retrieval`.
- **Depends on:** B15, B16.

### B18 Sessions and messages
- **Goal:** sessions listed latest first, renamed and soft-deleted, and messages stored with citations.
- **Read:** `02-data-model.md` sections 4.7 and 7.3 (row for sessions). `03-contract.md` section 2.
- **Files:** `db/repos/sessions.py`, `services/sessions.py`, tests.
- **Signatures:** `sessions.list`, `sessions.create`, `sessions.rename(ctx, RenameSessionInput) -> Session`, `sessions.delete(ctx, DeleteSessionInput) -> None` (the `conflict` rule for a running question is added in B28), `sessions.messages(ctx, GetMessagesInput) -> list[ChatMsg]`; `sessions.add_message(conn, ctx, *, workspace_id, session_id, role, text, question_id=None, citation_ids: list[str] = [], unverified: list[Unverified] | None = None) -> str`.
- **Tests:** repository and service tests.
- **Done when:** `uv run pytest tests/unit/services/test_sessions.py`.
- **Depends on:** B16.

### B19 Context map
- **Goal:** file nodes, entities and links.
- **Read:** `05-retrieval-and-citations.md` section 8. `02-data-model.md` section 4.9.
- **Files:** `db/repos/entities.py`, `contextmap/service.py`, `services/contextmap.py`, tests.
- **Signatures:** `add_mentions(conn, ctx, *, workspace_id, entities: list[EntityOut], passage_file: Callable[[str], str], question_id: str | None, entity_id: str | None = None) -> tuple[list[MapNode], list[MapLink]]` (returns only what is new); `contextmap.get(ctx, input) -> ContextMap`.
- **Tests:** `test_entity_upsert`, `test_map_read`.
- **Done when:** `uv run pytest tests/unit/contextmap`.
- **Depends on:** B13.

### B20 The HTTP API
- **Goal:** every non-streaming operation built so far is reachable over HTTP.
- **Read:** `03-contract.md` section 3 (binding rule, errors, headers). `01-architecture.md` sections 5, 7, 9.
- **Files:** `http/app.py`, `http/errors.py`, `http/context.py`, `cli.py` (subcommand `serve`), tests under `tests/integration/`, and the `app` and `client` fixtures.
- **Signatures:** `build_app(settings: Settings, runtime: AgentRuntime | None = None, jobs: Jobs | None = None) -> FastAPI` (`jobs` defaults to `ThreadJobs`; a lifespan that migrates, syncs definitions and config, creates the first workspace when none exists, records `server.started`, submits `ingest` for every result of `pending_ingestion`, and submits `reembed` when the configured embedding model has no row yet; one `app.add_api_route("/api/v1" + op.path, endpoint, methods=[op.method], name=op.name)` per `json` and `upload` operation; `GET /api/v1/health`; CORS; optional static files); `context_from_request(request) -> RequestContext`; an exception handler mapping `ServiceError` and validation errors to `ErrorBody`. Each generated endpoint builds the input model by the binding rule and calls the handler with `run_in_threadpool`.
- **Tests:** `test_every_operation_has_a_route` (stream operations may answer `internal` until B28), `test_workspace_lifecycle`, `test_upload_and_list`, `test_upload_too_large`, `test_upload_traversal_name`, `test_agents_and_notes`, `test_error_shapes`, `test_source_and_client_headers`, `test_list_events_filters`, `test_static_dir`, `test_upload_returns_before_ingestion`, `test_ingestion_resumed_at_start`, `test_reference_file_api`, `test_renames_and_edits`, `test_soft_deletes`.
- **Done when:** `uv run pytest tests/integration` and `uv run twyf serve` answers `curl localhost:8321/api/v1/health`.
- **Depends on:** B17, B18, B19.

> **OWNER REVIEW 2.** The owner starts the server, opens `http://127.0.0.1:8321/docs`, uploads a file and reads the event log with `curl "localhost:8321/api/v1/events"`.

---

## Stage 3: agents

### B21 Runtime protocol and the fake runtime
- **Goal:** the boundary to a model, and the scripted runtime every later test uses.
- **Read:** `04-agents.md` sections 2, 6.1 and 6.3 (`FakeRuntime` and its placeholders).
- **Files:** `runtime/base.py`, `runtime/fake.py`, `runtime/__init__.py` (`get_runtime(settings) -> AgentRuntime`), tests, and the `fake` fixture.
- **Signatures:** as in section 6.1; `@dataclass ScriptStep: match: dict[str, Any]; output: dict | Exception; times: int = 1`; `FakeRuntime(script)`, `FakeRuntime.from_file(path: Path)`, `fake.requests`, `fake.unused() -> list[ScriptStep]`.
- **Tests:** `test_fake_script_steps`, `test_fake_placeholders`.
- **Done when:** `uv run pytest tests/unit/runtime/test_fake.py`.
- **Depends on:** B04.

### B22 Prompts and the turn runner
- **Goal:** one function that runs a turn, records it and validates it.
- **Read:** `04-agents.md` sections 6.2 and 7. `02-data-model.md` section 4.8 (`agent_turns`). `01-architecture.md` section 8 (first two rows).
- **Files:** `agents/prompts.py`, `runtime/runner.py`, `db/repos/turns.py`, tests.
- **Signatures:** `render(...)` as in section 7; `TurnRunner.run(...)` as in section 6.2; `class TurnFailed(Exception): turn_type: str; agent_id: str; reason: str`.
- **Tests:** `test_render_prompt`, `test_runner_records_turn`, `test_runner_retries_invalid_output`, `test_runner_gives_up`, `test_runner_timeout`, repository tests for turns.
- **Done when:** `uv run pytest tests/unit/runtime tests/unit/agents`.
- **Depends on:** B09, B21.

### B23 Write the agent and skill texts
- **Goal:** the real prompt text in `.agents`.
- **Read:** all of `04-agents.md`. `05-retrieval-and-citations.md` sections 6.2 and 7.
- **Files:** every `agent.md` and `skill.md` under `.agents`, and `.agents/agents.md`.
- **Content rules:** `agents.md` holds the four rules of `04-agents.md` section 7. Each agent body states the role from section 1.4 and the "Agents" table of `docs/development/revision-2-initialization/design.md` in under 150 words. Each skill body states, in order: what the turn is for, what each input field means, what each output field must contain, and the validation rules for that turn from section 3. `verify-claims` contains the five bullet points of section 9.2. `draft-claims` contains the claim rules of section 8 and one quoted and one derived example. `write-answer` contains the four rules of section 10. `cite-passages` says to copy quotes exactly and to give the passage id. `translator-contracts` and `translator-finance` add two or three sentences on what to look for (clauses, dates, parties and obligations; figures, units, periods and how numbers are derived). Plain words, no role-play.
- **Tests:** `test_repo_agents_folder_loads`; a new `test_skill_texts_name_their_fields` asserting each turn skill's body mentions every field name of its output model.
- **Done when:** `uv run pytest tests/unit/agents`.
- **Depends on:** B22.

> **OWNER REVIEW 3.** The owner reads every file in `.agents`. These texts decide how the agents behave.

### B24 The state machine
- **Goal:** the pure transition function.
- **Read:** `04-agents.md` section 5.
- **Files:** `orchestration/machine.py`, tests.
- **Signatures:** `QState` as in section 5; one frozen dataclass per event (`Start`, `PlanDone`, `VolunteersDone`, `AssignDone`, `WorkDone`, `ReviewDone`, `ClaimsDrafted`, `Verified`, `AnswerWritten`, `Cancel`, `Fatal`) and per command (`StartRound`, `RunPlan`, `EmitBroadcast`, `RunVolunteers`, `RunAssign`, `Join`, `Assign`, `RunWork`, `Say`, `RunReview`, `RunDraftClaims`, `EmitVerify`, `RunVerify`, `EmitVerdict`, `EmitRehuddle`, `Leave`, `RunWriteAnswer`, `EmitContext`, `EmitAnswer`, `Complete`, `CancelTurns`, `EmitCancelled`, `EmitError`); `transition(state, event) -> tuple[QState, list[Command]]`; `class InvalidTransition(Exception)`; `FINAL_STATES: frozenset[str]`.
- **Tests:** the five `test_machine_*` tests.
- **Done when:** `uv run pytest tests/unit/orchestration/test_machine.py --cov=twyf.orchestration.machine --cov-branch --cov-fail-under=100`.
- **Depends on:** B01.

### B25 Arithmetic, claim rules and answer assembly
- **Goal:** the mechanical parts of verification and answer writing.
- **Read:** `04-agents.md` sections 8, 9.3 and 10. `10-demo-scenario.md` section 4.
- **Files:** `orchestration/arithmetic.py`, `orchestration/claims.py`, `db/repos/claims.py`, tests.
- **Signatures:** `evaluate(expression: str) -> float` (raises `ArithmeticRejected`); `within_tolerance(computed: float, stated: float) -> bool`; `validate_claims(claims: list[ClaimOut], known_citation_ids: set[str]) -> list[str]`; `store_claims(conn, ctx, *, question_id, round_id, turn_id, claims) -> list[ClaimRow]` (computes citations of derived claims, `computed_result`, `content_sha256`, and carried verdicts); `passes(verdicts: list[str]) -> bool`; `validate_segments(segments, verified: dict[str, str], mode: str) -> list[str]`; `assemble_answer(segments, claim_citations: dict[str, list[str]]) -> tuple[str, list[str]]` (text and citation ids in marker order); `fallback_answer(claims, claim_citations) -> tuple[str, list[str]]`.
- **Tests:** `test_arithmetic`, `test_claim_rules`, `test_carried_verdict`, `test_pass_rule`, `test_assemble_answer`, `test_answer_guards`.
- **Done when:** `uv run pytest tests/unit/orchestration --cov=twyf.orchestration.claims --cov=twyf.orchestration.arithmetic --cov-branch --cov-fail-under=100`.
- **Depends on:** B16, B24.

### B26 The engine: from question to settled huddle
- **Goal:** the engine runs plan, volunteering, pairing, work and review, and emits their events.
- **Read:** `04-agents.md` sections 3 (validation table), 4, 5.2 and 5.4. `02-data-model.md` sections 4.7, 4.8 and 7.2 ("The availability check" and the paragraph after it). `03-contract.md` sections 2 (numbering of `Citation.n`) and 4.1.
- **Files:** `orchestration/engine.py`, `orchestration/inputs.py` (builds each turn's input), `orchestration/validators.py` (the rules of the validation table), `db/repos/questions.py`, `db/repos/huddle.py`, tests under `tests/unit/orchestration/`.
- **Signatures:** `class Engine: def __init__(self, settings, conn_factory, runner: TurnRunner, retriever: Retriever, broker: EventBroker)`; `async def run(self, ctx: RequestContext, question_id: str) -> None` (a loop: `state, commands = transition(state, event)`, record `question.state_changed`, execute each command, feed the resulting event; stops at a final state). One private method per command. `named(conn, workspace_id, question) -> tuple[list[str], list[str]]`. In this task `RunDraftClaims` feeds `ClaimsDrafted(0)` and the answer is the `nothing_found` text without a chat turn, so a question can run end to end.
- **Tests:** engine tests with `FakeRuntime` that assert the events and rows for: broadcast to all with two volunteers; a direct call; a follow-up that calls a new translator; the search loop limited to `TWYF_SEARCHES_PER_TURN`; a file that is `missing` at the start is in no turn input; `test_named_files_and_agents`.
- **Done when:** `uv run pytest tests/unit/orchestration`.
- **Depends on:** B17, B18, B19, B22, B25.

### B27 The engine: claims, verification, rounds and the answer
- **Goal:** the rest of the state machine's commands.
- **Read:** `04-agents.md` sections 5.3, 8, 9 and 10. `05-retrieval-and-citations.md` section 6.3.
- **Files:** `orchestration/engine.py`, `db/repos/verifications.py`, tests.
- **Signatures:** the engine methods for `RunDraftClaims`, `EmitVerify`, `RunVerify` (mechanical check of every citation, then the verifier turn for claims without a carried verdict), `EmitVerdict`, `EmitRehuddle`, `RunWriteAnswer` (all four modes and the fallback), `EmitContext`, `EmitAnswer` (stores the assistant message, its citations, `message_claims` and `unverified`), `Complete` (totals on the question, `question.completed`).
- **Tests:** engine tests for: one round that passes; fail then pass with a carried verdict; three failures giving a partial answer; a mechanical failure; zero claims; the answer fallback (`test_answer_fallback`).
- **Done when:** `uv run pytest tests/unit/orchestration`.
- **Depends on:** B26.

### B28 `ask` over HTTP: stream, cancel, replay, recovery
- **Goal:** the question operations work end to end through the API.
- **Read:** `03-contract.md` sections 4.2 and 5. `01-architecture.md` section 8.
- **Files:** `services/questions.py`, `http/sse.py`, `http/app.py` (stream routes, engine task registry, recovery in the lifespan), tests.
- **Signatures:** `questions.start(ctx, AskInput) -> str` (validates, rejects a busy session, stores the user message and the question, records `question.asked` with wire `started`); `questions.cancel(ctx, CancelQuestionInput) -> None`; `questions.recover(conn, ctx) -> int` (marks open questions `interrupted`); `sse.stream(broker, conn_factory, question_id, after: int) -> AsyncIterator[bytes]`; `sse.format(event_id: int, event: AgentEvent) -> bytes`; `class Tasks: start(question_id, coro); cancel(question_id)`.
- **Tests:** `test_ask_stream_format`, `test_ask_happy_path`, `test_ask_no_files`, `test_ask_nothing_found`, `test_ask_partial_after_round_limit`, `test_ask_mechanical_fail`, `test_ask_busy_session`, `test_cancel`, `test_disconnect_does_not_cancel`, `test_replay`, `test_crash_recovery`, `test_sessions_and_messages`, `test_delete_conflicts`.
- **Done when:** `uv run pytest tests/integration`.
- **Depends on:** B20, B27.

### B29 Failures and concurrency
- **Goal:** every row of the failure table behaves as written.
- **Read:** `01-architecture.md` sections 7 and 8. `04-agents.md` section 5.4 (last paragraph) and 9.3 (last paragraph).
- **Files:** `orchestration/engine.py` and whatever the tests expose, tests.
- **Tests:** `test_ask_bad_quote_retried`, `test_ask_translator_fails_others_continue`, `test_ask_verifier_unavailable`, `test_concurrent_questions`, `test_weights_reach_agents`, `test_injection_is_inert`, `test_missing_file_left_out_of_question`, `test_file_lost_during_question`, `test_all_files_unusable`.
- **Done when:** `uv run pytest tests/integration`.
- **Depends on:** B28.

### B30 Work outside a question
- **Goal:** direct chat with a translator, the bounded first read, and image descriptions.
- **Read:** `04-agents.md` sections 9.4 and 11 (including "The first read is bounded"). `09-decisions.md` O14. `05-retrieval-and-citations.md` section 2 ("Images").
- **Files:** `services/agents.py` (`ask_translator`), `files/first_read.py`, `files/describe.py`, `http/app.py` (background tasks after upload), tests.
- **Signatures:** `async def ask_translator(ctx, AskTranslatorInput) -> TranslatorReply`; `async def first_read(runner, conn_factory, ctx, file_id: str) -> None` (exactly one turn, given the first `settings.first_read_chunks` chunks, with `chunks_shown` and `chunks_total`; no search, no second turn); `async def describe_image(runner, conn_factory, ctx, file_version_id: str) -> None` (skipped unless the runtime has `vision`; stores an extraction of kind `description`, then chunks and embeds it).
- **Tests:** `test_ask_translator`, `test_first_read`, `test_long_file_stays_bounded`, and a test that an image upload with a vision-capable fake runtime gives a searchable `description` extraction.
- **Done when:** `uv run pytest tests/integration`.
- **Depends on:** B28.

### B31 The queue runtime and the turn operations
- **Goal:** a harness can do the agent work.
- **Read:** `04-agents.md` section 6.3 (`QueueRuntime`). `03-contract.md` section 3 (the three turn rows).
- **Files:** `runtime/queue.py`, `services/turns.py`, tests.
- **Signatures:** `class QueueRuntime` implementing `AgentRuntime` with `capabilities = frozenset({"vision"})`; `turns.claim(ctx, ClaimTurnInput) -> TurnOffer | None` (async, long-polls); `turns.submit(ctx, SubmitTurnInput) -> SubmitResult`; `turns.fail(ctx, FailTurnInput) -> None`; a 10-second watcher that records `runtime.waiting`.
- **Tests:** `test_queue_claim_submit`, `test_queue_long_poll`, `test_queue_lease_expiry`, and an integration test that completes a question by claiming and submitting over HTTP.
- **Done when:** `uv run pytest tests/unit/runtime tests/integration`.
- **Depends on:** B28.

### B32 The command runtime
- **Goal:** a headless CLI can do the agent work.
- **Read:** `04-agents.md` section 6.3 (`CommandRuntime`).
- **Files:** `runtime/command.py`, `tests/fixtures/fake_cli.py` (a script that reads standard input and prints what an environment variable tells it to), tests.
- **Signatures:** `class CommandRuntime(command: list[str])` implementing `AgentRuntime`; `build_prompt(request: TurnRequest) -> str`; `parse_output(stdout: str) -> tuple[dict, Usage]`.
- **Tests:** `test_command_runtime`.
- **Done when:** `uv run pytest tests/unit/runtime/test_command.py`.
- **Depends on:** B22.

---

## Stage 4: MCP, demo and finishing

### B33 The MCP server
- **Goal:** every operation as an MCP tool, plus resources and prompts.
- **Read:** all of `06-mcp.md`. `03-contract.md` section 3.
- **Files:** `mcp/client.py`, `mcp/server.py`, `cli.py` (subcommand `mcp`, flag `--http`), `.mcp.json` at the repository root, tests under `tests/integration/mcp/`, and the `mcp_client` fixture.
- **Signatures:** `async def call(http: httpx.AsyncClient, op: Operation, input: Wire) -> Any`; `build_server(http) -> MCPServer`; `make_tool(op, http) -> Callable`; `register_resources(server, http)`; `register_prompts(server)`; the special tools `upload_file`, `ask` and `get_question_events` as in `06-mcp.md` section 2.
- **Tests:** all eleven tests of `07-test-plan.md` section 4.
- **Done when:** `uv run pytest tests/integration/mcp`.
- **Depends on:** B30, B31.

### B34 The demo: fixtures, seed and scripted run
- **Goal:** the required demo integration test passes.
- **Read:** all of `10-demo-scenario.md`. `07-test-plan.md` section 5.
- **Files:** `backend/scripts/make_demo_files.py`, the six files under `tests/fixtures/demo/`, `tests/fixtures/demo/script.json`, `services/demo.py`, `cli.py` (subcommand `seed-demo`; `serve` flags `--runtime` and `--fake-script`), `tests/integration/test_demo.py`, and the `demo` fixture.
- **Signatures:** `demo.seed(ctx, settings, fixtures: Path) -> None`.
- **Tests:** `test_demo_fixtures_parse`, `test_demo_seed`, `test_demo_question`, `test_demo_recording`.
- **Done when:** `uv run pytest tests/integration/test_demo.py`.
- **Depends on:** B29, B30.

> **OWNER REVIEW 4.** The owner runs `uv run twyf seed-demo`, then `uv run twyf serve --runtime fake --fake-script tests/fixtures/demo/script.json`, asks the demo question with `curl -N`, and reads the stream and the event log.

### B35 Recording tests for every action
- **Goal:** proof that every kind of action is recorded with the right actor, source and versions.
- **Read:** `07-test-plan.md` section 7. `02-data-model.md` sections 3 and 5.
- **Files:** `tests/integration/test_recording.py`, and fixes wherever a case fails.
- **Tests:** `test_action_is_recorded` with every row of the table, and `test_every_event_type_is_tested`.
- **Done when:** `uv run pytest tests/integration/test_recording.py`.
- **Depends on:** B33, B34.

### B36 Logs, the event log command and the evaluation runner
- **Goal:** the tools for looking at what happened and for judging answers.
- **Read:** `01-architecture.md` section 11. `07-test-plan.md` section 8.
- **Files:** `logging_setup.py`, `cli.py` (subcommands `events` with `--workspace --question --type --after --tail`, and `eval` with `--runtime --case`), `evals/cases.json`, `evals/workspaces/`, `evals/runner.py`, tests.
- **Signatures:** `setup_logging(settings) -> None`; `run_case(client, case: EvalCase) -> EvalResult`; `write_report(results, path) -> None`.
- **Tests:** log lines are JSON with `request_id`; `twyf events` prints the filtered rows; `run_case` against the fake runtime with the demo script reports every expectation of the demo case as met.
- **Done when:** `uv run pytest tests/unit/test_cli.py tests/unit/test_evals.py`.
- **Depends on:** B34.

### B37 Docling and fastembed
- **Goal:** the rich parser and the real embedder.
- **Read:** `05-retrieval-and-citations.md` sections 2 and 4. The Docling documentation for converting a document and iterating its items with page and bounding box, and the `fastembed` README, as they are at the time of the task.
- **Files:** `files/parsers/docling.py`, `retrieval/embedder.py` (`FastEmbedEmbedder`), tests marked `models`.
- **Signatures:** `class DoclingParser` implementing `Parser` (PDF, DOCX and images; kind `ocr` for images); `class FastEmbedEmbedder(model_name: str = "BAAI/bge-small-en-v1.5")` implementing `Embedder`.
- **Tests (marker `models`, run by hand with `uv sync --extra rich && uv run pytest -m models`):** the demo PDFs parse with page numbers and every demo quote is found; an image containing text gives an `ocr` extraction with that text; the embedder returns unit vectors of 384 dimensions.
- **Done when:** `uv run pytest -m models`, and the default `uv run pytest` still passes without the extra installed.
- **Depends on:** B34.

### B38 Coverage, CI and the README
- **Goal:** the quality gates and the instructions.
- **Read:** `07-test-plan.md` section 9. `01-architecture.md` sections 5 and 12.
- **Files:** `backend/scripts/check_coverage.py`, `.github/workflows/ci.yml` (all four jobs), `README.md` (how to run the backend, the UI against it, the MCP server and a worker harness), `backend/README.md`.
- **Done when:** `uv run pytest --cov=twyf --cov-branch --cov-report=json --cov-fail-under=90 && uv run python scripts/check_coverage.py`.
- **Depends on:** B35, B36, F8.

---

## Frontend tasks

Run from `frontend/`. Each is done when `npm run build && npm test` passes. Read `03-contract.md` sections 6 and 7 before any of them. Do not restyle or rearrange anything that a task does not name.

### F1 Contract additions and the drift check
- **Goal:** `types.ts` gains the additions, and the compiler guards it against the generated types.
- **Read:** `03-contract.md` sections 1 and 6.
- **Files:** `src/backend/types.ts` (exactly the changes of section 6), `package.json` (dev dependency `json-schema-to-typescript`, script `"gen:contract": "json2ts -i ../contract/schema.json -o src/backend/contract.gen.ts --unreachableDefinitions"`), `src/backend/contract.gen.ts` (generated, committed), `src/backend/contract.check.ts`. Complete the CI `contract` job.
- **Done when:** `npm run gen:contract && git diff --exit-code src/backend/contract.gen.ts && npm run build`.
- **Depends on:** B06.

### F2 Mock additions
- **Goal:** the mock implements the larger interface.
- **Files:** `src/backend/mock.ts`: `createWorkspace`, `renameWorkspace`, `deleteWorkspace` on an in-memory list that starts with `mine` and the demo workspace (the demo workspace cannot be renamed or deleted); `referenceFile` (adds a file named after the last part of the path, with `path` set); `deleteFile`, `renameAgent`, `deleteAgent`, `editNote` (user notes only), `deleteNote`, `renameSession`, `deleteSession`, each changing the in-memory data; a `started` event first in `genericScript`.
- **Done when:** `npm run build && npm test`.
- **Depends on:** F1.

### F3 The HTTP backend
- **Goal:** a second implementation of `Backend`.
- **Read:** `03-contract.md` sections 3 and 4.2.
- **Files:** `src/backend/http.ts`, `src/backend/http.test.ts`.
- **Signatures:** `export function httpBackend(baseUrl: string, fetchFn: typeof fetch = fetch): Backend`; `export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncIterable<AgentEvent>`. Every request sends `X-TWYF-Source: ui`. A non-2xx response throws `new Error(body.error.message)`. `uploadFile` sends `multipart/form-data` with part `file` and throws when `data` is missing. `ask` posts, yields each parsed event, remembers the id from `started`, and on abort posts to the cancel path and returns.
- **Tests:** `http.test.ts` as described in `07-test-plan.md` section 6.
- **Done when:** `npm run build && npm test`.
- **Depends on:** F1.

### F4 Choosing the backend
- **Goal:** the app uses the real backend when told to, and the demo always uses the mock.
- **Files:** `src/backend/router.ts` (`export function withDemo(real: Backend, mock: Backend): Backend`), `src/backend/index.ts`, `src/vite-env.d.ts` (type for `VITE_BACKEND_URL`), a test for `withDemo`.
- **Done when:** `npm run build && npm test`. With `VITE_BACKEND_URL` unset the app behaves exactly as before.
- **Depends on:** F2, F3.

### F5 The app: new events, the verifier, workspaces
- **Goal:** the UI shows verification and the new data.
- **Read:** `03-contract.md` section 7 (rows App, Verifier on the stage, Chat, Workspaces, File badge). `src/App.tsx`, `src/Stage.tsx`, `src/Chat.tsx`, `src/styles.css`.
- **Files:** `src/App.tsx` (start on `workspaces[0]`; pass `data: f` on upload; cases for `started`, `verify`, `verdict`, `rehuddle`, `error`, `cancelled`; the three workspace buttons), `src/Stage.tsx` (`Huddle` gains `verifier: null | { state: 'checking' | 'passed' | 'failed' }`, drawn as one figure beside the orchestrator), `src/Chat.tsx` (the "Could not be verified" block and the error text), `src/styles.css` (verifier figure, the block, `.t-image`).
- **Done when:** `npm run build && npm test`, and the demo plays in the browser as before for every existing event.
- **Depends on:** F4.

### F6 Files by path, statuses, renames and deletes
- **Goal:** the UI offers every new operation, with the smallest possible controls.
- **Read:** `03-contract.md` section 7 (rows Files, Renames and deletes). `02-data-model.md` section 7.3. `src/Panels.tsx`.
- **Files:** `src/App.tsx` (handlers that call the new `Backend` methods and refresh the lists; a 2-second refresh of the file list while any file has status `processing`; `nameOf` falls back to a note's `authorName`, `fileName` to a citation's `fileName`), `src/Panels.tsx` (explorer: the path field and a status badge; file card: Delete; agent card: Rename and Delete; session rows: Rename and Delete; each note: Delete, and Edit when its author is `user`), `src/styles.css` (status badges).
- **Rules:** use the browser's `prompt` and `confirm`. No file rename control anywhere. A file whose status is `missing` or `changed` is shown dimmed with that word.
- **Done when:** `npm run build && npm test`.
- **Depends on:** F5.

### F7 The extended demo
- **Goal:** the mock's demo tells the new story and its test checks it.
- **Read:** `10-demo-scenario.md` sections 2, 3, 4 and 6.
- **Files:** `src/demo/scenario.ts`, `src/demo/scenario.test.ts`.
- **Done when:** `npm test`.
- **Depends on:** F6.

> **OWNER REVIEW 5.** The owner plays the demo in the browser and looks at the verifier on the stage, the failed round and the answer.

### F8 The demo against the real backend
- **Goal:** the same test file passes against the real server.
- **Read:** `07-test-plan.md` section 5 (last row). `01-architecture.md` section 12 (job `demo`).
- **Files:** `src/demo/scenario.test.ts` (backend chosen from `TWYF_TEST_BACKEND_URL`), `.github/workflows/ci.yml` (job `demo`), `backend/scripts/run_demo_server.sh` (fresh data folder, `seed-demo`, then `serve --runtime fake --fake-script ...` with `TWYF_FIRST_READ=false TWYF_EMBEDDER=hash TWYF_PARSER=basic`).
- **Done when:** with the script running, `TWYF_TEST_BACKEND_URL=http://127.0.0.1:8321 npm test` passes.
- **Depends on:** F7, B34.

---

## Dependency overview

```
B01 ─ B02 ─ B07 ─ B08 ─ B09 ─ B10 ─ B11 ─┐
  └─ B03 ─ B04 ─ B05 ─ B06 ─ F1          B13 ─ B14 ─ B15 ─┐
  └─ B12 ────────────────────────────────┘    └─ B16 ─────┴─ B17 ─┐
  └─ B24                                       └─ B18, B19 ───────┴─ B20
B04 ─ B21 ─ B22 ─ B23        B25 (B16, B24)
B26 (B17 B18 B19 B22 B25) ─ B27 ─ B28 (B20) ─ B29, B30, B31 ─ B33 ─ B35 ─ B38
B22 ─ B32                    B34 (B29 B30) ─ B36, B37, F8
F1 ─ F2, F3 ─ F4 ─ F5 ─ F6 ─ F7 ─ F8
```
