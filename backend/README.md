# twyf: the backend

The Python backend of Talk With Your Files. It stores files, agents, notes, sessions and a context map per workspace, answers questions by running a huddle of agents, and verifies every claim before it reaches the user. It has two doors, an HTTP API and an MCP server, both generated from one list of operations (`src/twyf/contract/operations.py`).

The design is in [docs/development/revision-2-backend/](../docs/development/revision-2-backend/); `progress.md` there records how each task was built.

## Commands

Run from this folder.

| Command | What it does |
|---|---|
| `uv run twyf serve` | Migrates the database, loads `.agents`, serves the API on `127.0.0.1:8321`. `--runtime fake --fake-script <file>` plays a script instead of real agents |
| `uv run twyf mcp` | The MCP server on stdio. `--http` serves Streamable HTTP on `127.0.0.1:8322/mcp` |
| `uv run twyf seed-demo` | Creates the demo workspace from `tests/fixtures/demo/` |
| `uv run twyf events` | Prints the event log. Filters: `--workspace --question --type --after`; `--tail` keeps printing |
| `uv run twyf eval` | Runs `evals/cases.json` against a running server and writes `evals/reports/<time>.json` |
| `uv run twyf export-contract` | Writes `../contract/schema.json` |

Settings are environment variables with the prefix `TWYF_` (or a `.env` file here); the full table is in `01-architecture.md` section 6.

## Checks

```bash
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

Coverage, as in CI:

```bash
uv run pytest --cov=twyf --cov-branch --cov-report=json --cov-fail-under=90 && uv run python scripts/check_coverage.py
```

Tests need no network, API key or model: they use the fake runtime, the `hash` embedder and the basic parsers. Tests marked `models` need the rich extra and download models: `uv sync --extra rich && uv run pytest -m models`.

## Layout

| Folder | What is there |
|---|---|
| `src/twyf/contract/` | Pydantic models of every wire type, agent event, turn, and the operation list |
| `src/twyf/services/` | One function per operation. The only place rules live |
| `src/twyf/http/`, `src/twyf/mcp/` | The two doors, generated from the operation list |
| `src/twyf/orchestration/` | The state machine and the engine that runs a question |
| `src/twyf/runtime/` | The boundary to a model: fake, queue and command runtimes, and the turn runner |
| `src/twyf/files/`, `retrieval/`, `citations/`, `contextmap/` | Ingestion, search, citations and the context map |
| `src/twyf/agents/` | Loads `../.agents` and renders prompts |
| `src/twyf/db/`, `recording/` | SQLite, migrations, repositories, and the event log |
| `tests/` | Unit and integration tests; fixtures under `tests/fixtures/` |
| `evals/` | The evaluation cases, their workspaces and reports |
| `scripts/` | Fixture generators, the coverage check and the demo server script |
