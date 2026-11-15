-- 0001 init: the schema of 02-data-model.md section 4, in order, then the seed rows of section 6.

-- 4.1 Lookup tables

CREATE TABLE sources        (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE actor_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE agent_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL, creatable INTEGER NOT NULL DEFAULT 0);
CREATE TABLE note_kinds     (code TEXT PRIMARY KEY, description TEXT NOT NULL, needs_citation INTEGER NOT NULL);
CREATE TABLE weights        (code TEXT PRIMARY KEY, rank INTEGER NOT NULL UNIQUE, factor REAL NOT NULL);
CREATE TABLE file_types     (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE location_kinds (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE availability_states (code TEXT PRIMARY KEY, usable INTEGER NOT NULL);
CREATE TABLE extraction_kinds (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE claim_kinds    (code TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE verdict_kinds  (code TEXT PRIMARY KEY, description TEXT NOT NULL, passes INTEGER NOT NULL);
CREATE TABLE question_states (code TEXT PRIMARY KEY, final INTEGER NOT NULL);
CREATE TABLE turn_states    (code TEXT PRIMARY KEY, final INTEGER NOT NULL);
CREATE TABLE turn_types     (code TEXT PRIMARY KEY, agent_kind TEXT NOT NULL REFERENCES agent_kinds(code));
CREATE TABLE event_types    (code TEXT PRIMARY KEY, category TEXT NOT NULL, description TEXT NOT NULL);

-- 4.2 Users, workspaces, actors

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

-- 4.3 Files

-- The app keeps a copy of every uploaded file and never changes or removes it. See section 7.2.
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
  content_sha256 TEXT NOT NULL,             -- the identity of the content
  name TEXT NOT NULL,                       -- the name this version was uploaded with. Never changed
  file_type TEXT NOT NULL REFERENCES file_types(code),
  size_bytes INTEGER NOT NULL,
  location_kind TEXT NOT NULL REFERENCES location_kinds(code),   -- always 'store' in version 1
  location TEXT NOT NULL,                   -- files/ab/abcdef... under the data dir
  mtime_ns INTEGER NOT NULL,                -- modification time seen when the hash was last confirmed
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (file_id, version));
CREATE UNIQUE INDEX file_versions_current ON file_versions(file_id) WHERE valid_to IS NULL;
CREATE INDEX file_versions_lookup ON file_versions(workspace_id, name, content_sha256);

CREATE TABLE file_availability (
  id INTEGER PRIMARY KEY,
  file_version_id TEXT NOT NULL REFERENCES file_versions(id),
  state TEXT NOT NULL REFERENCES availability_states(code),      -- ok | missing | changed
  valid_from TEXT NOT NULL,
  valid_to TEXT);
CREATE UNIQUE INDEX file_availability_current ON file_availability(file_version_id) WHERE valid_to IS NULL;

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

-- 4.4 Agent definitions, skills, config

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

-- 4.5 Agents

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

-- 4.6 Notes and citations

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
  question_id TEXT,
  turn_id TEXT,
  created_at TEXT NOT NULL,
  deleted_at TEXT);
CREATE INDEX notes_file ON notes(workspace_id, file_id);
CREATE INDEX notes_author ON notes(workspace_id, author_id);

CREATE TABLE note_versions (                -- the text. An agent's note has exactly one version
  id INTEGER PRIMARY KEY,
  note_id TEXT NOT NULL REFERENCES notes(id),
  version INTEGER NOT NULL,
  text TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  UNIQUE (note_id, version));
CREATE UNIQUE INDEX note_versions_current ON note_versions(note_id) WHERE valid_to IS NULL;

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

-- A cache of each note's current text. The service layer replaces a note's row when its text changes.
CREATE VIRTUAL TABLE notes_fts USING fts5(note_id UNINDEXED, text, tokenize='unicode61');

CREATE TABLE note_embeddings (
  note_id TEXT NOT NULL REFERENCES notes(id),
  embedding_model_id INTEGER NOT NULL REFERENCES embedding_models(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  vector BLOB NOT NULL,
  PRIMARY KEY (note_id, embedding_model_id));

-- 4.7 Sessions, messages, questions

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

-- 4.8 Huddle, turns, claims, verification

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

-- 4.9 Context map

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

-- 4.10 The event log

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

-- 4.11 Views for current state

CREATE VIEW v_workspaces AS
  SELECT w.id, w.user_id, v.name, w.created_at
  FROM workspaces w JOIN workspace_versions v ON v.workspace_id = w.id AND v.valid_to IS NULL
  WHERE w.deleted_at IS NULL;

CREATE VIEW v_files AS
  SELECT f.id, f.workspace_id, v.id AS file_version_id, v.version, v.name, v.file_type,
         v.size_bytes, v.content_sha256, v.location_kind, v.location, v.mtime_ns,
         a.state AS availability, f.created_at
  FROM files f
  JOIN file_versions v ON v.file_id = f.id AND v.valid_to IS NULL
  JOIN file_availability a ON a.file_version_id = v.id AND a.valid_to IS NULL
  WHERE f.deleted_at IS NULL;

-- Files that agents may work on: live, and their content is where it should be.
CREATE VIEW v_usable_files AS SELECT * FROM v_files WHERE availability = 'ok';

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
  SELECT n.id, n.workspace_id, n.file_id, n.file_version_id, fv.version AS file_version,
         n.author_id, n.kind, t.text, n.created_at, w.weight
  FROM notes n
  JOIN file_versions fv ON fv.id = n.file_version_id
  JOIN note_versions t ON t.note_id = n.id AND t.valid_to IS NULL
  JOIN note_weights w ON w.note_id = n.id AND w.valid_to IS NULL
  JOIN files f ON f.id = n.file_id AND f.deleted_at IS NULL
  WHERE n.deleted_at IS NULL;

-- 6 Seed rows

INSERT INTO sources VALUES ('ui','Browser UI'),('api','HTTP API'),('mcp','MCP server'),('cli','Command line'),('internal','The backend itself');
INSERT INTO actor_kinds VALUES ('user','A person'),('agent','An agent'),('system','The backend');
INSERT INTO agent_kinds VALUES ('translator','Reads files',1),('verifier','Checks claims',0),('orchestrator','Runs the huddle',0),('chat','Talks with the user',0);
INSERT INTO note_kinds VALUES ('summary','What a file says',1),('finding','A fact found in a file',1),('interpretation','Subjective guidance or reasoning',0);
INSERT INTO weights VALUES ('off',0,0.0),('low',1,0.5),('normal',2,1.0),('high',3,2.0);
INSERT INTO file_types VALUES ('pdf','PDF'),('docx','Word'),('csv','CSV'),('md','Markdown'),('txt','Text'),('image','Image'),('other','Other');
INSERT INTO location_kinds VALUES ('store','A copy kept in the app''s data folder'),('path','A file read where it lies on this machine. Reserved, not used in version 1'),('remote','A file on another server. Reserved, not used in version 1');
INSERT INTO availability_states VALUES ('ok',1),('missing',0),('changed',0);
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
INSERT INTO event_types VALUES
  ('server.started','system','The server starts'),
  ('definition.loaded','versioning','A new agent definition version is snapshotted'),
  ('skill.loaded','versioning','A new skill version is snapshotted'),
  ('config.changed','versioning','A new config version is snapshotted'),
  ('workspace.created','workspace','The matching operation'),
  ('workspace.renamed','workspace','The matching operation'),
  ('workspace.deleted','workspace','The matching operation'),
  ('file.uploaded','file','upload_file adds a new file'),
  ('file.version_added','file','add_file_version adds a version to an existing file'),
  ('file.upload_duplicate','file','The bytes equal what is already there (see section 7.2)'),
  ('file.ingest_started','file','The background job starts on a file version'),
  ('file.extraction_completed','file','A parser finishes'),
  ('file.extraction_failed','file','A parser finishes'),
  ('file.indexed','file','Chunks and embeddings are written'),
  ('file.missing','file','The content is no longer at its location'),
  ('file.changed','file','The content at the location has a different hash'),
  ('file.restored','file','A missing or changed file is found again with the recorded hash'),
  ('file.deleted','file','delete_file'),
  ('agent.created','agent','An agent row is created, by a user or with a workspace'),
  ('agent.renamed','agent','The matching operation'),
  ('agent.deleted','agent','The matching operation'),
  ('note.created','note','Any note, by anyone'),
  ('note.edited','note','The matching operation'),
  ('note.deleted','note','The matching operation'),
  ('note.weight_set','note','One event per note whose weight changes'),
  ('session.created','session','The matching operation'),
  ('session.renamed','session','The matching operation'),
  ('session.deleted','session','The matching operation'),
  ('message.created','session','A user or assistant message is stored'),
  ('question.asked','question','ask is called'),
  ('question.status','question','A progress line for the UI'),
  ('question.state_changed','question','Every state machine transition. Payload {from, to}'),
  ('huddle.round_started','huddle','A round begins'),
  ('huddle.broadcast','huddle','The orchestrator messages translators'),
  ('huddle.member_joined','huddle','An agent joins the huddle'),
  ('huddle.file_assigned','huddle','Also written for first reads and direct chats'),
  ('huddle.reading','huddle','A work turn starts'),
  ('retrieval.searched','huddle','A search ran. Payload: query, mode, chunk ids returned'),
  ('citation.created','citation','A quote passed the mechanical check'),
  ('citation.rejected','citation','A quote failed it. Payload: quote, reason'),
  ('huddle.statement','huddle','An agent speaks'),
  ('claims.drafted','verification','The orchestrator drafts claims'),
  ('verification.started','verification','The verifier starts checking the round''s claims'),
  ('verification.completed','verification','Payload: every verdict'),
  ('huddle.reopened','verification','Verification failed and rounds remain'),
  ('huddle.member_left','huddle','Agents leave the huddle'),
  ('context.extended','context','New entities or links'),
  ('answer.written','question','The assistant message is stored'),
  ('question.completed','question','Final state answered or answered_partial. Payload: token and time totals'),
  ('question.failed','question','The question ends with an error'),
  ('question.cancelled','question','The question is cancelled'),
  ('question.interrupted','question','Crash recovery'),
  ('turn.queued','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('turn.claimed','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('turn.completed','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('turn.failed','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('turn.timed_out','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('turn.cancelled','turn','Each change of a turn''s state. .completed carries tokens, model, duration'),
  ('runtime.waiting','turn','A queued turn has waited 10 seconds with no worker'),
  ('translator.asked','direct','ask_translator'),
  ('translator.replied','direct','ask_translator'),
  ('demo.seeded','system','twyf seed-demo');
