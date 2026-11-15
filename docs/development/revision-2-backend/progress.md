# Progress

| Task | Done | Commit | Notes |
|---|---|---|---|
| B01 | 2026-11-15 | d0e47af | Build backend is hatchling; added `asyncio_default_fixture_loop_scope = "function"` to silence a pytest-asyncio warning |
| B02 | 2026-11-15 | db95565 | |
| B03 | 2026-11-15 | 7d958bd | Added `ErrorInfo` (the inner object of `ErrorBody`). `tests/fixtures/samples.json` started here |
| B04 | 2026-11-15 | 5304209 | Turn sub-shapes written as `{...}` in 04-agents section 3 are named models (`HistoryItem`, `FileInfo`, `AgentInfo`, `DirectCall`, `ClaimRef`, ...). Events default their `type` but the schema marks it required |
| B05 | 2026-11-15 | 7aa0403 | Added `FileText` and `SubmitResult` to `models.py` for the two outputs written as `{...}` in 03-contract section 3. Every operation has an input model, including an empty `ListWorkspacesInput` |
| B06 | 2026-11-15 | da706a3 | The export inlines the `Opt_*` alias definitions pydantic creates for `Opt[...]` and drops their `default: null`, so the schema has no alias types. `AgentEvent` is added to `$defs` from a `TypeAdapter`. Each operation's `input`/`output` is a JSON Schema fragment |
| B07 | 2026-11-15 | 75375d6 | `0001_init.sql` was generated from the SQL blocks of 02-data-model sections 4 and 6. Five event codes with an empty "Written when" cell got a short description. `backend/typings/sqlite_vec` is a local type stub. `migrate` backs up only a database that already had migrations |
| B08 | 2026-11-15 | 803298c | Added `services/state.py` (`configure(settings)`, `settings()`, `connect()`): services take only `(ctx, input)`, so this is where they get settings and a connection. `BROKER` in `recording/broker.py` is the process's broker; `transaction()` runs `after_commit` hooks, which is how the recorder publishes after commit |
| B09 | 2026-11-15 | 6c329b7 | `LoadedAgent` also has `content` (the bytes hashed) and `LoadedAgents` an `errors` map. Content that returns to an earlier hash reopens that version row, because the schema allows one row per (definition, hash); the same for skills and config. See the owner note in the session report |
| B10 | 2026-11-15 | | Built-in agents are named Orchestrator, Verifier, Chat, Translator 1, Translator 2. Added `services.errors.require_text` (empty names are `validation`), `state.db()`, `agents_repo.last_name`, and the `synced` fixture (definitions and config snapshotted, used by `ws`). Lists order by creation time, then insertion |
