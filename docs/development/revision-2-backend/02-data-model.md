# 02 Data model

Part of the revision 2 backend plan. The schema below is complete. Migration `0001_init.sql` contains exactly these statements, in this order, followed by the seed rows in section 6.

## 1. Rules that apply to every table

1. **Nothing is ever deleted or overwritten**, except the caches named in rule 6. "Delete" means setting `deleted_at` on the identity row and recording an event. Reads through the views in section 4.11 hide deleted rows.
2. **Ids** are text: a prefix, an underscore and 32 hex characters from `uuid.uuid4().hex` (`ids.new_id("f")` gives `f_3fa9...`). Prefixes: `u` user, `ws` workspace, `f` file, `fv` file version, `x` extraction, `a` agent, `n` note, `c` citation, `s` session, `m` message, `q` question, `r` round, `t` turn, `k` claim, `v` verification, `e` entity. Seeded and demo rows may use any text id (for example `demo`, `a-t1`).
3. **Times** are UTC ISO 8601 text with milliseconds and a `Z`, from `clock.now()`.
4. **Every table that holds user data has `workspace_id`**, and every repository function takes `workspace_id` and filters on it. This is how workspaces stay isolated (decision 1). The user is reached through `workspaces.user_id`.
5. **Slowly changing attributes live in a `_versions` table** (type 2: a new row per change, `valid_from`, `valid_to`, `valid_to IS NULL` for the current row). The identity table holds only what never changes.
6. **Caches** that may be rebuilt: `chunks_fts`, `notes_fts`, and rows of `chunk_embeddings` / `note_embeddings` for a retired embedding model.

## 2. Which technique applies to which entity

| Entity | Technique | Detail |
|---|---|---|
| Workspace name | Type 2 | `workspace_versions` |
| File name, content | Type 2 | `file_versions`. A new upload of different content under the same name is a new version |
| Agent name, speciality, definition | Type 2 | `agent_versions` |
| Session title | Type 2 | `session_versions` |
| Note weight | Type 2 | `note_weights` |
| Agent definition, skill, config | Type 2, keyed by content hash | `agent_definition_versions`, `skill_versions`, `config_versions` |
| Note text, citation, message, claim, verdict, turn, assignment, extraction, blob | Type 0 (immutable) | Written once. A correction is a new row |
| Question state, turn state | Type 1 on the row, with every change in `app_events` | The row shows the current state. History is in the log |
| Lookup tables | Type 1 | Codes are never removed |

"What was true at time T" for a type 2 entity: `WHERE valid_from <= :t AND (valid_to IS NULL OR valid_to > :t)`.

## 3. How actions are recorded

**Choice: an append-only event log (`app_events`) beside current-state tables.** Each service function changes its tables and appends its event in the same transaction. Full event sourcing was rejected (`09-decisions.md` D7).

- Triggers make `app_events` append-only.
- Every event has an **actor** (who) and a **source** (which door).
- Events are tied together by `session_id`, `question_id`, `round_id`, `turn_id`, `request_id` and `cause_event_id`.
- Events that the UI must see while a question runs also carry `wire_json`: the exact `AgentEvent` sent on the stream. The stream of a question is `SELECT wire_json FROM app_events WHERE question_id = ? AND wire_json IS NOT NULL ORDER BY id`. There is no second copy.
- Events record the versions in force: `agent_definition_version_id` on agent actions, `config_version_id` on questions.
- Reads are not recorded. Only actions that change state or call an agent are.

### Actor and source

| Actor kind | `actors.id` | Used for |
|---|---|---|
| `user` | the user id | Anything the person does |
| `agent` | the agent id | Anything an agent does, including the orchestrator, verifier and chat agent |
| `system` | `system` | Ingestion, crash recovery, seeding |

| Source | Meaning |
|---|---|
| `ui` | The browser UI (header `X-TWYF-Source: ui`) |
| `api` | Any other HTTP client (no header) |
| `mcp` | The MCP server (header `X-TWYF-Source: mcp`) |
| `cli` | A `twyf` command |
| `internal` | The backend itself: the engine, ingestion, recovery |

An agent action inside a question has actor = the agent and source = `internal`. Its `cause_event_id` chain leads back to the user's `question.asked` event, which has the door the question came through.

## 4. Schema

### 4.1 Lookup tables

```sql
CREATE TABLE sources        (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE actor_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE agent_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL, creatable INTEGER NOT NULL DEFAULT 0);
CREATE TABLE note_kinds     (code TEXT PRIMARY KEY, description TEXT NOT NULL, needs_citation INTEGER NOT NULL);
CREATE TABLE weights        (code TEXT PRIMARY KEY, rank INTEGER NOT NULL UNIQUE, factor REAL NOT NULL);
CREATE TABLE file_types     (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE extraction_kinds (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE claim_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE verdict_kinds  (code TEXT PRIMARY KEY, description TEXT NOT NULL, passes INTEGER NOT NULL);
CREATE TABLE question_states (code TEXT PRIMARY KEY, final INTEGER NOT NULL);
CREATE TABLE turn_states    (code TEXT PRIMARY KEY, final INTEGER NOT NULL);
CREATE TABLE turn_types     (code TEXT PRIMARY KEY, agent_kind TEXT NOT NULL REFERENCES agent_kinds(code));
CREATE TABLE event_types    (code TEXT PRIMARY KEY, category TEXT NOT NULL, description TEXT NOT NULL);
```

### 4.2 Users, workspaces, actors

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TABLE workspaces (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  deleted_at TEXT);
CREATE INDEX workspaces_user ON workspaces(user_id);

CREATE TABLE workspace_versions (
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  version INTEGER NOT NULL,
  name TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (workspace_id, version));
CREATE UNIQUE INDEX workspace_versions_current ON workspace_versions(workspace_id) WHERE valid_to IS NULL;

CREATE TABLE actors (
  id TEXT PRIMARY KEY,                      -- a user id, an agent id, or 'system'
  actor_kind TEXT NOT NULL REFERENCES actor_kinds(code),
  workspace_id TEXT REFERENCES workspaces(id),   -- set for agents only
  created_at TEXT NOT NULL);
```

### 4.3 Files

```sql
CREATE TABLE blobs (
  sha256 TEXT PRIMARY KEY,
  size_bytes INTEGER NOT NULL,
  stored_path TEXT NOT NULL,                -- relative to the data dir: blobs/ab/abcdef...
  created_at TEXT NOT NULL);

CREATE TABLE files (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  created_at TEXT NOT NULL,
  deleted_at TEXT);
CREATE INDEX files_workspace ON files(workspace_id);

CREATE TABLE file_versions (
  id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL REFERENCES files(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  version INTEGER NOT NULL,
  blob_sha256 TEXT NOT NULL REFERENCES blobs(sha256),
  name TEXT NOT NULL,
  file_type TEXT NOT NULL REFERENCES file_types(code),
  size_bytes INTEGER NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (file_id, version));
CREATE UNIQUE INDEX file_versions_current ON file_versions(file_id) WHERE valid_to IS NULL;
CREATE INDEX file_versions_lookup ON file_versions(workspace_id, name, blob_sha256);

CREATE TABLE extractions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  file_version_id TEXT NOT NULL REFERENCES file_versions(id),
  kind TEXT NOT NULL REFERENCES extraction_kinds(code),   -- text | ocr | description
  parser TEXT NOT NULL,                     -- 'text', 'csv', 'pdf_basic', 'docx_basic', 'docling', 'vision'
  parser_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok','failed')),
  error TEXT,
  text TEXT NOT NULL DEFAULT '',            -- the canonical text. Citations index into it
  text_sha256 TEXT NOT NULL DEFAULT '',
  turn_id TEXT,                             -- set when a model produced it (kind 'description')
  created_at TEXT NOT NULL,
  UNIQUE (file_version_id, kind, parser, parser_version));

CREATE TABLE blocks (                       -- the structure of an extraction: page, paragraph, row
  id INTEGER PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extractions(id),
  ordinal INTEGER NOT NULL,
  kind TEXT NOT NULL,                       -- 'page', 'heading', 'paragraph', 'row', 'table', 'image'
  label TEXT NOT NULL,                      -- shown to people: 'Page 3', 'Row 12', 'Section 2, Term'
  page INTEGER,
  bbox TEXT,                                -- JSON [x0,y0,x1,y1] when the parser gives one
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  UNIQUE (extraction_id, ordinal));

CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  extraction_id TEXT NOT NULL REFERENCES extractions(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  ordinal INTEGER NOT NULL,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  text TEXT NOT NULL,
  UNIQUE (extraction_id, ordinal));
CREATE INDEX chunks_file ON chunks(workspace_id, file_id);

CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id', tokenize='unicode61');

CREATE TABLE embedding_models (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL, version TEXT NOT NULL, dim INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (name, version));

CREATE TABLE chunk_embeddings (
  chunk_id INTEGER NOT NULL REFERENCES chunks(id),
  embedding_model_id INTEGER NOT NULL REFERENCES embedding_models(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  vector BLOB NOT NULL,                     -- float32 little-endian, length dim*4, unit length
  PRIMARY KEY (chunk_id, embedding_model_id));
CREATE INDEX chunk_embeddings_ws ON chunk_embeddings(workspace_id, embedding_model_id);
```

### 4.4 Agent definitions, skills, config

```sql
CREATE TABLE agent_definitions (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,                -- the folder name in .agents/agents
  agent_kind TEXT NOT NULL REFERENCES agent_kinds(code));

CREATE TABLE agent_definition_versions (
  id INTEGER PRIMARY KEY,
  definition_id INTEGER NOT NULL REFERENCES agent_definitions(id),
  version INTEGER NOT NULL,
  content_sha256 TEXT NOT NULL,             -- hash of agent.md + config.json + parent hash + skill hashes
  frontmatter TEXT NOT NULL,                -- JSON
  body TEXT NOT NULL,                       -- this definition's own prompt text
  config TEXT NOT NULL,                     -- JSON of config.json
  resolved_prompt TEXT NOT NULL,            -- parent prompt + own body, what is actually sent
  parent_version_id INTEGER REFERENCES agent_definition_versions(id),
  source_path TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (definition_id, version),
  UNIQUE (definition_id, content_sha256));
CREATE UNIQUE INDEX adv_current ON agent_definition_versions(definition_id) WHERE valid_to IS NULL;

CREATE TABLE skills (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE);

CREATE TABLE skill_versions (
  id INTEGER PRIMARY KEY,
  skill_id INTEGER NOT NULL REFERENCES skills(id),
  version INTEGER NOT NULL,
  content_sha256 TEXT NOT NULL,
  frontmatter TEXT NOT NULL,
  body TEXT NOT NULL,
  source_path TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (skill_id, version),
  UNIQUE (skill_id, content_sha256));
CREATE UNIQUE INDEX skill_versions_current ON skill_versions(skill_id) WHERE valid_to IS NULL;

CREATE TABLE agent_definition_version_skills (
  definition_version_id INTEGER NOT NULL REFERENCES agent_definition_versions(id),
  skill_version_id INTEGER NOT NULL REFERENCES skill_versions(id),
  PRIMARY KEY (definition_version_id, skill_version_id));

CREATE TABLE config_versions (
  id INTEGER PRIMARY KEY,
  content_sha256 TEXT NOT NULL UNIQUE,
  config TEXT NOT NULL,                     -- JSON of the non-secret settings
  valid_from TEXT NOT NULL,
  valid_to TEXT);
```

### 4.5 Agents

```sql
CREATE TABLE agents (
  id TEXT PRIMARY KEY REFERENCES actors(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  agent_kind TEXT NOT NULL REFERENCES agent_kinds(code),
  created_at TEXT NOT NULL,
  deleted_at TEXT);
CREATE INDEX agents_workspace ON agents(workspace_id, agent_kind);

CREATE TABLE agent_versions (
  id INTEGER PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  version INTEGER NOT NULL,
  name TEXT NOT NULL,
  specialty TEXT NOT NULL,                  -- 'generic' or a speciality. '' for non-translators
  definition_id INTEGER NOT NULL REFERENCES agent_definitions(id),
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (agent_id, version));
CREATE UNIQUE INDEX agent_versions_current ON agent_versions(agent_id) WHERE valid_to IS NULL;
```

Each workspace has exactly one agent of kind `orchestrator`, one `verifier` and one `chat`, created with the workspace. The chat agent is one row per workspace; each session is a separate conversation with it.

### 4.6 Notes and citations

```sql
CREATE TABLE citations (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  file_version_id TEXT NOT NULL REFERENCES file_versions(id),
  extraction_id TEXT NOT NULL REFERENCES extractions(id),
  char_start INTEGER NOT NULL,              -- of the quote, in extractions.text
  char_end INTEGER NOT NULL,
  quote TEXT NOT NULL,                      -- equals substr(extractions.text, char_start, char_end)
  passage_start INTEGER NOT NULL,
  passage_end INTEGER NOT NULL,
  passage TEXT NOT NULL,
  location TEXT NOT NULL,                   -- the label of the containing block
  found_by_agent_id TEXT NOT NULL REFERENCES agents(id),
  turn_id TEXT,
  created_at TEXT NOT NULL,
  CHECK (char_start >= passage_start AND char_end <= passage_end AND char_start < char_end));
CREATE INDEX citations_file ON citations(workspace_id, file_id);

CREATE TABLE notes (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  file_version_id TEXT NOT NULL REFERENCES file_versions(id),
  author_id TEXT NOT NULL REFERENCES actors(id),
  kind TEXT NOT NULL REFERENCES note_kinds(code),
  text TEXT NOT NULL,
  question_id TEXT,
  turn_id TEXT,
  created_at TEXT NOT NULL,
  deleted_at TEXT);
CREATE INDEX notes_file ON notes(workspace_id, file_id);
CREATE INDEX notes_author ON notes(workspace_id, author_id);

CREATE TABLE note_citations (
  note_id TEXT NOT NULL REFERENCES notes(id),
  citation_id TEXT NOT NULL REFERENCES citations(id),
  n INTEGER NOT NULL,                       -- the marker number inside this note, from 1
  PRIMARY KEY (note_id, n));

CREATE TABLE note_weights (
  id INTEGER PRIMARY KEY,
  note_id TEXT NOT NULL REFERENCES notes(id),
  weight TEXT NOT NULL REFERENCES weights(code),
  set_by TEXT NOT NULL REFERENCES actors(id),
  valid_from TEXT NOT NULL,
  valid_to TEXT);
CREATE UNIQUE INDEX note_weights_current ON note_weights(note_id) WHERE valid_to IS NULL;

CREATE VIRTUAL TABLE notes_fts USING fts5(text, content='notes', content_rowid='rowid', tokenize='unicode61');

CREATE TABLE note_embeddings (
  note_id TEXT NOT NULL REFERENCES notes(id),
  embedding_model_id INTEGER NOT NULL REFERENCES embedding_models(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  vector BLOB NOT NULL,
  PRIMARY KEY (note_id, embedding_model_id));
```

The citation rule of section 7.1 is checked by the service layer and not by a trigger, because a note's citations are inserted after the note in the same transaction.

### 4.7 Sessions, messages, questions

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,                 -- time of the last message. Type 1, for sorting only
  deleted_at TEXT);
CREATE INDEX sessions_workspace ON sessions(workspace_id, updated_at DESC);

CREATE TABLE session_versions (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  version INTEGER NOT NULL,
  title TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (session_id, version));
CREATE UNIQUE INDEX session_versions_current ON session_versions(session_id) WHERE valid_to IS NULL;

CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  state TEXT NOT NULL REFERENCES question_states(code),
  max_rounds INTEGER NOT NULL,
  rounds_used INTEGER NOT NULL DEFAULT 0,
  config_version_id INTEGER NOT NULL REFERENCES config_versions(id),
  runtime TEXT NOT NULL,
  error_code TEXT,
  error_message TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT);
CREATE INDEX questions_session ON questions(session_id);
CREATE INDEX questions_open ON questions(state) WHERE finished_at IS NULL;

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  question_id TEXT REFERENCES questions(id),
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  text TEXT NOT NULL,
  unverified TEXT,                          -- JSON list of {text, reason}, assistant messages only
  created_at TEXT NOT NULL);
CREATE INDEX messages_session ON messages(session_id, created_at);

CREATE TABLE message_citations (
  message_id TEXT NOT NULL REFERENCES messages(id),
  citation_id TEXT NOT NULL REFERENCES citations(id),
  n INTEGER NOT NULL,
  PRIMARY KEY (message_id, n));
```

### 4.8 Huddle, turns, claims, verification

```sql
CREATE TABLE huddle_rounds (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT NOT NULL REFERENCES questions(id),
  round_no INTEGER NOT NULL,                -- 1 = first huddle. n+1 = after the n-th failed verification
  reason TEXT NOT NULL,                     -- 'initial' or 'verification_failed'
  started_at TEXT NOT NULL,
  ended_at TEXT,
  UNIQUE (question_id, round_no));

CREATE TABLE huddle_members (
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT NOT NULL REFERENCES questions(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  how TEXT NOT NULL CHECK (how IN ('volunteered','called')),
  joined_at TEXT NOT NULL,
  left_at TEXT,
  left_reason TEXT,                         -- 'settled', 'failed', 'cancelled'
  UNIQUE (question_id, agent_id));

CREATE TABLE assignments (                  -- every pairing of an agent with a file, note or no note
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT REFERENCES questions(id),     -- NULL for first reads and direct chats
  round_id TEXT REFERENCES huddle_rounds(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  file_version_id TEXT NOT NULL REFERENCES file_versions(id),
  purpose TEXT NOT NULL CHECK (purpose IN ('huddle','first_read','direct')),
  created_at TEXT NOT NULL);
CREATE INDEX assignments_agent ON assignments(workspace_id, agent_id);
CREATE INDEX assignments_file ON assignments(workspace_id, file_id);

CREATE TABLE agent_turns (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT REFERENCES questions(id),
  round_id TEXT REFERENCES huddle_rounds(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  agent_version_id INTEGER NOT NULL REFERENCES agent_versions(id),
  definition_version_id INTEGER NOT NULL REFERENCES agent_definition_versions(id),
  turn_type TEXT NOT NULL REFERENCES turn_types(code),
  attempt INTEGER NOT NULL DEFAULT 1,
  retry_of TEXT REFERENCES agent_turns(id),
  state TEXT NOT NULL REFERENCES turn_states(code),
  runtime TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  input TEXT NOT NULL,                      -- JSON
  output TEXT,                              -- JSON, once done
  error TEXT,
  model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  duration_ms INTEGER,
  claimed_by TEXT,                          -- worker name, queue runtime only
  lease_token TEXT,
  lease_expires_at TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT);
CREATE INDEX agent_turns_queue ON agent_turns(state, created_at) WHERE state IN ('queued','claimed');
CREATE INDEX agent_turns_question ON agent_turns(question_id);

CREATE TABLE statements (                   -- what an agent said in a huddle or a direct chat
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT REFERENCES questions(id),
  round_id TEXT REFERENCES huddle_rounds(id),
  turn_id TEXT NOT NULL REFERENCES agent_turns(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  text TEXT NOT NULL,
  created_at TEXT NOT NULL);

CREATE TABLE statement_citations (
  statement_id INTEGER NOT NULL REFERENCES statements(id),
  citation_id TEXT NOT NULL REFERENCES citations(id),
  n INTEGER NOT NULL,
  PRIMARY KEY (statement_id, n));

CREATE TABLE claims (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT NOT NULL REFERENCES questions(id),
  round_id TEXT NOT NULL REFERENCES huddle_rounds(id),   -- the round that drafted it
  ordinal INTEGER NOT NULL,
  kind TEXT NOT NULL REFERENCES claim_kinds(code),       -- quoted | derived
  text TEXT NOT NULL,
  expression TEXT,                          -- derived claims with arithmetic
  stated_result REAL,
  computed_result REAL,
  content_sha256 TEXT NOT NULL,             -- text + kind + sorted citation ids + input hashes + expression
  turn_id TEXT NOT NULL REFERENCES agent_turns(id),
  created_at TEXT NOT NULL);
CREATE INDEX claims_question ON claims(question_id);

CREATE TABLE claim_citations (
  claim_id TEXT NOT NULL REFERENCES claims(id),
  citation_id TEXT NOT NULL REFERENCES citations(id),
  PRIMARY KEY (claim_id, citation_id));

CREATE TABLE claim_inputs (                 -- a derived claim and the claims it is computed from
  claim_id TEXT NOT NULL REFERENCES claims(id),
  input_claim_id TEXT NOT NULL REFERENCES claims(id),
  PRIMARY KEY (claim_id, input_claim_id));

CREATE TABLE verifications (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  question_id TEXT NOT NULL REFERENCES questions(id),
  round_id TEXT NOT NULL REFERENCES huddle_rounds(id),
  turn_id TEXT REFERENCES agent_turns(id),  -- NULL when every verdict was carried over
  passed INTEGER NOT NULL,
  created_at TEXT NOT NULL);

CREATE TABLE verdicts (
  id INTEGER PRIMARY KEY,
  verification_id TEXT NOT NULL REFERENCES verifications(id),
  claim_id TEXT NOT NULL REFERENCES claims(id),
  verdict TEXT NOT NULL REFERENCES verdict_kinds(code),
  reason TEXT NOT NULL,
  carried_from INTEGER REFERENCES verdicts(id),  -- set when an identical claim was verified earlier
  UNIQUE (verification_id, claim_id));

CREATE TABLE citation_verdicts (
  verdict_id INTEGER NOT NULL REFERENCES verdicts(id),
  citation_id TEXT NOT NULL REFERENCES citations(id),
  supports TEXT NOT NULL CHECK (supports IN ('full','partial','none')),
  PRIMARY KEY (verdict_id, citation_id));

CREATE TABLE message_claims (               -- the verified claims an answer was written from
  message_id TEXT NOT NULL REFERENCES messages(id),
  claim_id TEXT NOT NULL REFERENCES claims(id),
  PRIMARY KEY (message_id, claim_id));
```

### 4.9 Context map

```sql
CREATE TABLE entities (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  label TEXT NOT NULL,
  norm_label TEXT NOT NULL,                 -- lower case, whitespace collapsed
  entity_type TEXT NOT NULL,                -- 'person','company','date','decision','place','other'
  created_at TEXT NOT NULL,
  deleted_at TEXT,
  UNIQUE (workspace_id, norm_label));

CREATE TABLE entity_mentions (              -- a file mentions an entity. The map link file -> entity
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  entity_id TEXT NOT NULL REFERENCES entities(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  citation_id TEXT REFERENCES citations(id),
  question_id TEXT REFERENCES questions(id),
  created_by TEXT NOT NULL REFERENCES actors(id),
  created_at TEXT NOT NULL,
  UNIQUE (entity_id, file_id));

CREATE TABLE entity_relations (             -- entity to entity. Reserved for graph retrieval. Not written in version 1
  id INTEGER PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  from_entity_id TEXT NOT NULL REFERENCES entities(id),
  to_entity_id TEXT NOT NULL REFERENCES entities(id),
  relation TEXT NOT NULL,
  citation_id TEXT REFERENCES citations(id),
  created_at TEXT NOT NULL);
```

### 4.10 The event log

```sql
CREATE TABLE app_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL REFERENCES event_types(code),
  actor_id TEXT NOT NULL REFERENCES actors(id),
  source TEXT NOT NULL REFERENCES sources(code),
  client TEXT,                              -- header X-TWYF-Client, for example 'claude-code'
  user_id TEXT NOT NULL REFERENCES users(id),
  workspace_id TEXT REFERENCES workspaces(id),   -- NULL only for server-wide events
  session_id TEXT,
  question_id TEXT,
  round_id TEXT,
  turn_id TEXT,
  request_id TEXT,                          -- one per HTTP request or CLI command
  cause_event_id INTEGER REFERENCES app_events(id),
  entity_type TEXT,                         -- 'file', 'note', 'agent', ...
  entity_id TEXT,
  agent_definition_version_id INTEGER REFERENCES agent_definition_versions(id),
  config_version_id INTEGER REFERENCES config_versions(id),
  payload TEXT NOT NULL DEFAULT '{}',       -- JSON
  wire_json TEXT);                          -- the AgentEvent sent on the stream, when there is one
CREATE INDEX app_events_ws ON app_events(workspace_id, id);
CREATE INDEX app_events_question ON app_events(question_id, id) WHERE question_id IS NOT NULL;
CREATE INDEX app_events_type ON app_events(event_type, id);
CREATE INDEX app_events_entity ON app_events(entity_type, entity_id);

CREATE TRIGGER app_events_no_update BEFORE UPDATE ON app_events
BEGIN SELECT RAISE(ABORT, 'app_events is append-only'); END;
CREATE TRIGGER app_events_no_delete BEFORE DELETE ON app_events
BEGIN SELECT RAISE(ABORT, 'app_events is append-only'); END;

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);
```

### 4.11 Views for current state

```sql
CREATE VIEW v_workspaces AS
  SELECT w.id, w.user_id, v.name, w.created_at
  FROM workspaces w JOIN workspace_versions v ON v.workspace_id = w.id AND v.valid_to IS NULL
  WHERE w.deleted_at IS NULL;

CREATE VIEW v_files AS
  SELECT f.id, f.workspace_id, v.id AS file_version_id, v.version, v.name, v.file_type,
         v.size_bytes, v.blob_sha256, f.created_at
  FROM files f JOIN file_versions v ON v.file_id = f.id AND v.valid_to IS NULL
  WHERE f.deleted_at IS NULL;

CREATE VIEW v_agents AS
  SELECT a.id, a.workspace_id, a.agent_kind, v.id AS agent_version_id, v.name, v.specialty,
         v.definition_id, a.created_at
  FROM agents a JOIN agent_versions v ON v.agent_id = a.id AND v.valid_to IS NULL
  WHERE a.deleted_at IS NULL;

CREATE VIEW v_sessions AS
  SELECT s.id, s.workspace_id, v.title, s.updated_at,
         (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
  FROM sessions s JOIN session_versions v ON v.session_id = s.id AND v.valid_to IS NULL
  WHERE s.deleted_at IS NULL;

CREATE VIEW v_notes AS
  SELECT n.id, n.workspace_id, n.file_id, n.author_id, n.kind, n.text, n.created_at, w.weight
  FROM notes n JOIN note_weights w ON w.note_id = n.id AND w.valid_to IS NULL
  WHERE n.deleted_at IS NULL;
```

## 5. Event taxonomy

`event_types` is seeded with these rows. `wire` names the `AgentEvent` type stored in `wire_json` (`03-contract.md` section 4).

| Code | Category | Written when | wire |
|---|---|---|---|
| `server.started` | system | The server starts | |
| `definition.loaded` | versioning | A new agent definition version is snapshotted | |
| `skill.loaded` | versioning | A new skill version is snapshotted | |
| `config.changed` | versioning | A new config version is snapshotted | |
| `workspace.created` / `.renamed` / `.deleted` | workspace | The matching operation | |
| `file.uploaded` | file | A new file is stored | |
| `file.version_added` | file | Different content arrives under an existing name | |
| `file.upload_duplicate` | file | The same name and content arrive again | |
| `file.extraction_completed` / `.extraction_failed` | file | A parser finishes | |
| `file.indexed` | file | Chunks and embeddings are written | |
| `agent.created` | agent | An agent row is created, by a user or with a workspace | |
| `note.created` | note | Any note, by anyone | `note` when inside a question |
| `note.weight_set` | note | One event per note whose weight changes | |
| `session.created` | session | | |
| `message.created` | session | A user or assistant message is stored | |
| `question.asked` | question | `ask` is called | `started` |
| `question.status` | question | A progress line for the UI | `status` |
| `question.state_changed` | question | Every state machine transition. Payload `{from, to}` | |
| `huddle.round_started` | huddle | A round begins | |
| `huddle.broadcast` | huddle | The orchestrator messages translators | `broadcast` |
| `huddle.member_joined` | huddle | | `join` |
| `huddle.file_assigned` | huddle | Also written for first reads and direct chats | `assign` when inside a question |
| `huddle.reading` | huddle | A work turn starts | `reading` |
| `retrieval.searched` | huddle | A search ran. Payload: query, mode, chunk ids returned | |
| `citation.created` | citation | A quote passed the mechanical check | |
| `citation.rejected` | citation | A quote failed it. Payload: quote, reason | |
| `huddle.statement` | huddle | An agent speaks | `say` |
| `claims.drafted` | verification | The orchestrator drafts claims | |
| `verification.started` | verification | | `verify` |
| `verification.completed` | verification | Payload: every verdict | `verdict` |
| `huddle.reopened` | verification | Verification failed and rounds remain | `rehuddle` |
| `huddle.member_left` | huddle | | `leave` |
| `context.extended` | context | New entities or links | `context` when inside a question |
| `answer.written` | question | The assistant message is stored | `answer` |
| `question.completed` | question | Final state `answered` or `answered_partial`. Payload: token and time totals | |
| `question.failed` | question | | `error` |
| `question.cancelled` | question | | `cancelled` |
| `question.interrupted` | question | Crash recovery | |
| `turn.queued` / `.claimed` / `.completed` / `.failed` / `.timed_out` / `.cancelled` | turn | Each change of a turn's state. `.completed` carries tokens, model, duration | |
| `runtime.waiting` | turn | A queued turn has waited 10 seconds with no worker | `status` |
| `translator.asked` / `translator.replied` | direct | `ask_translator` | |
| `demo.seeded` | system | `twyf seed-demo` | |

## 6. Seed rows

```sql
INSERT INTO sources VALUES ('ui','Browser UI'),('api','HTTP API'),('mcp','MCP server'),('cli','Command line'),('internal','The backend itself');
INSERT INTO actor_kinds VALUES ('user','A person'),('agent','An agent'),('system','The backend');
INSERT INTO agent_kinds VALUES ('translator','Reads files',1),('verifier','Checks claims',0),('orchestrator','Runs the huddle',0),('chat','Talks with the user',0);
INSERT INTO note_kinds VALUES ('summary','What a file says',1),('finding','A fact found in a file',1),('interpretation','Subjective guidance or reasoning',0);
INSERT INTO weights VALUES ('off',0,0.0),('low',1,0.5),('normal',2,1.0),('high',3,2.0);
INSERT INTO file_types VALUES ('pdf','PDF'),('docx','Word'),('csv','CSV'),('md','Markdown'),('txt','Text'),('image','Image'),('other','Other');
INSERT INTO extraction_kinds VALUES ('text','Text taken from the file'),('ocr','Text read from pixels'),('description','A model''s description of an image');
INSERT INTO claim_kinds VALUES ('quoted','Stated by the cited passages'),('derived','Computed or inferred from other claims');
INSERT INTO verdict_kinds VALUES ('supported','Fully supported',1),('partly_supported','Only part is supported',0),('unsupported','Not supported',0),('mechanical_fail','Failed a mechanical check',0);
INSERT INTO question_states VALUES ('received',0),('planning',0),('broadcasting',0),('assigning',0),('working',0),('reviewing',0),('drafting',0),('verifying',0),('writing',0),('answered',1),('answered_partial',1),('failed',1),('cancelled',1),('interrupted',1);
INSERT INTO turn_states VALUES ('queued',0),('claimed',0),('done',1),('failed',1),('timed_out',1),('cancelled',1);
INSERT INTO turn_types VALUES ('plan','orchestrator'),('assign','orchestrator'),('review','orchestrator'),('draft_claims','orchestrator'),
  ('volunteer','translator'),('work','translator'),('direct_reply','translator'),('first_read','translator'),('describe_image','translator'),
  ('verify','verifier'),('write_answer','chat');
INSERT INTO users VALUES ('u_local','Local user', :now);
INSERT INTO actors VALUES ('u_local','user',NULL,:now),('system','system',NULL,:now);
-- event_types: one row per code in section 5.
```

At first start, when no workspace exists, the server creates one named "My workspace" through `services.workspaces.create` (source `internal`), which also creates its orchestrator, verifier, chat agent and two generic translators named "Translator 1" and "Translator 2".

## 7. Rules enforced by the service layer

### 7.1 Notes and citations

- A note of kind `summary` or `finding` written by an agent must have at least one citation, and every citation must point into the note's own file. Otherwise `ValidationError`.
- A note of kind `interpretation` needs no citation. It is guidance, never evidence. Notes written by the user are always `interpretation`.
- A citation row is only ever inserted by `citations.locate.create_citation`, which runs the mechanical check first (`05-retrieval-and-citations.md` section 6). There is no other insert path.
- A new note gets a `note_weights` row with weight `normal`.

### 7.2 Files: identity, duplicates, re-uploads

On upload, compute the SHA-256 of the bytes while streaming to a temporary file, then:

| Case | Result | Event |
|---|---|---|
| Blob not seen before | Move the temporary file to `blobs/<aa>/<sha256>`, insert `blobs` | |
| Blob already stored | Delete the temporary file. The existing blob is shared | |
| A live file in this workspace has the same name and the same blob | Nothing new. Return the existing file | `file.upload_duplicate` |
| A live file in this workspace has the same name and a different blob | Close its current version, insert a new `file_versions` row with `version` + 1, ingest it | `file.version_added` |
| Otherwise | Insert `files` and `file_versions` version 1, ingest it | `file.uploaded` |

Notes and citations keep pointing at the `file_version_id` they were written against. A citation is always checked against its own extraction, so it stays valid after a newer version arrives. The same content under a different name is a separate file sharing one blob.

### 7.3 Delete

- `delete_workspace` sets `workspaces.deleted_at`. Its rows remain. It disappears from every listing, and every operation on it returns `not_found`. Running questions in it are cancelled first.
- No other delete operation exists in version 1. The `deleted_at` columns on files, agents, notes, sessions and entities are there so those operations can be added without a schema change.
- Blobs are never removed, even when no live file refers to them.
- A true erase for privacy is an open question (`09-decisions.md` section 3).

### 7.4 Versioning of `.agents`

Files in `.agents` are the source of truth. The database holds snapshots.

1. At server start, and before each question starts, `agents.definitions.sync()` reads `.agents`.
2. For each skill it computes `sha256(skill.md bytes)`. If the current `skill_versions` row has a different hash, it closes that row and inserts a new one with `version` + 1 and records `skill.loaded`.
3. For each agent it computes `sha256(agent.md bytes + config.json bytes + parent content hash + sorted skill hashes)`. A change in a parent or a skill therefore makes a new version of every child. On a new hash it closes the current row, inserts the next version with its `resolved_prompt`, links its skills, and records `definition.loaded`.
4. Every `agent_turns` row stores `definition_version_id` and `agent_version_id`. Any past action can therefore be tied to the exact prompt text that produced it.
5. A definition that disappears from `.agents` has its current version closed. Agents that used it fall back to their kind's base definition at the next sync, as a new `agent_versions` row.
6. A definition that fails to parse keeps its last good version, and the error is logged and recorded as `definition.loaded` with `payload.error`.

`config_versions` works the same way: hash of the JSON of the non-secret settings, snapshotted at start, `config.changed` on a new hash.

## 8. Migrations

- Files `db/migrations/NNNN_name.sql`, applied in order by `db/migrate.py` at server start, each in one transaction, recorded in `schema_migrations`.
- Forward only. A migration never edits an earlier one. No down migrations: restore from a copy of the data folder.
- A migration may not drop a column or table that holds recorded data. To retire a column, stop using it.
- Before applying any migration to an existing database, `migrate.py` copies `twyf.db` to `twyf.db.bak-<version>`.
- Alembic was rejected because it needs SQLAlchemy (`09-decisions.md` D9).
