# Integration tests

Through the HTTP API with the fake runtime.

| File | What it is |
|---|---|
| `test_api.py` | Every operation has a route; workspaces, uploads, notes, renames, deletes, errors, headers |
| `test_ask.py` | Asking: the stream, answers, partial answers, cancel, replay, crash recovery, conflicts |
| `test_failures.py` | Every failure case: bad quotes, failing agents, missing files, concurrency, injection |
| `test_outside_question.py` | Direct chat, the bounded first read, image descriptions |
| `test_worker.py` | A question completed by claiming and submitting turns over HTTP |
| `test_demo.py` | The demo: fixtures, seed, the full question, and its event log |
| `test_recording.py` | Every kind of action is recorded with the right actor, source and links |
| `helpers.py`, `conftest.py` | Shared helpers and fixtures |
| `mcp/` | Tests through the MCP server |
