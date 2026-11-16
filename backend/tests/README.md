# Tests

Run from `backend/` with `uv run pytest`. No test needs a network connection, an API key or a model: they use the fake runtime, the `hash` embedder and the basic parsers. Tests marked `models` need the `rich` extra (`uv run pytest -m models`).

| Item | What it is |
|---|---|
| `conftest.py` | Shared fixtures: settings, a database, a workspace, the fake runtime, the app and client, the demo |
| `unit/` | Tests of one module each, mirroring `src/twyf/` |
| `integration/` | Tests through the HTTP API and the MCP server |
| `fixtures/` | Files and scripts the tests use |

Every test is listed with its pass condition in [07-test-plan.md](../../docs/development/revision-2-backend/07-test-plan.md).
