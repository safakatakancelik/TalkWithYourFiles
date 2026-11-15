# Progress

| Task | Done | Commit | Notes |
|---|---|---|---|
| B01 | 2026-11-15 | d0e47af | Build backend is hatchling; added `asyncio_default_fixture_loop_scope = "function"` to silence a pytest-asyncio warning |
| B02 | 2026-11-15 | db95565 | |
| B03 | 2026-11-15 | 7d958bd | Added `ErrorInfo` (the inner object of `ErrorBody`). `tests/fixtures/samples.json` started here |
| B04 | 2026-11-15 | 5304209 | Turn sub-shapes written as `{...}` in 04-agents section 3 are named models (`HistoryItem`, `FileInfo`, `AgentInfo`, `DirectCall`, `ClaimRef`, ...). Events default their `type` but the schema marks it required |
| B05 | 2026-11-15 | 7aa0403 | Added `FileText` and `SubmitResult` to `models.py` for the two outputs written as `{...}` in 03-contract section 3. Every operation has an input model, including an empty `ListWorkspacesInput` |
| B06 | 2026-11-15 | da706a3 | The export inlines the `Opt_*` alias definitions pydantic creates for `Opt[...]` and drops their `default: null`, so the schema has no alias types. `AgentEvent` is added to `$defs` from a `TypeAdapter`. Each operation's `input`/`output` is a JSON Schema fragment |
