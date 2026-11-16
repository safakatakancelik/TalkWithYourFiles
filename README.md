# Talk With Your Files

Have a conversation with your files. You add files to a workspace and ask questions about them in a chat. A huddle of agents works out the answer together, a verifier checks every claim against the exact passages it cites, and only verified claims reach you, each with its citations.

Revision 2 has a Python backend (`backend/`), a React UI (`frontend/`) and an MCP server, so any agent harness that speaks MCP (Claude Code, Codex, opencode, ...) can use the app and can also do its agent work.

## Quick start: the UI with its built-in demo

```bash
cd frontend
npm install
npm run dev
```

Open the address it prints and press "Run demo". This plays a scripted story on an in-memory mock; no backend is needed.

## Run the backend

Needs Python 3.13+ and [uv](https://docs.astral.sh/uv/). From `backend/`:

```bash
uv sync
uv run twyf serve
```

The API is on `http://127.0.0.1:8321`. Its interactive documentation is at `http://127.0.0.1:8321/docs`, where every operation can be tried. Data is kept in `~/.twyf` (set `TWYF_DATA_DIR` to change it).

Optional: `uv sync --extra rich` adds Docling (layout-aware PDF and Word reading, OCR for images) and fastembed (search by meaning). Without it the app uses the basic parsers and keyword search. Its first run downloads models from Hugging Face.

## Use the UI with the backend

With the backend running, from `frontend/`:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8321 npm run dev
```

Every workspace then lives in the backend. "Run demo" still plays the mock's scripted story.

## Use the app from an agent harness (MCP)

`twyf mcp` is an MCP server that turns every API operation into a tool. It needs the API server running.

- **Claude Code**: open the repository root. `.mcp.json` registers the server as `twyf`.
- **Other harnesses**: run `uv run --directory backend twyf mcp` as a stdio MCP server, or `uv run twyf mcp --http` for Streamable HTTP on `http://127.0.0.1:8322/mcp`. Set `TWYF_API_URL` if the API is not on `http://127.0.0.1:8321`.

The tools cover workspaces, files (`upload_file` takes a `path` or base64 content), agents, notes, sessions and questions. The `ask_files` prompt shows how to ask and present a cited answer.

## Let a harness do the agent work (queue runtime)

The backend never calls a model itself. With the default runtime, `queue`, every agent turn waits in the database until a worker claims it:

1. Start the API: `uv run twyf serve`.
2. In a harness connected through MCP, use the `work_agent_queue` prompt (argument `worker_name`). It loops: `claim_turn`, do the turn as instructed, `submit_turn`.
3. Ask a question with `ask(..., wait: false)` from the UI, the API or the MCP tools, and read its events with `get_question_events`.

The backend validates every output, checks every quote and verifies every claim, whichever model does the thinking. Run the worker with file, shell and network tools switched off: its job needs none of them, and that keeps an instruction hidden in a file from reaching anything.

Other runtimes: `TWYF_RUNTIME=command` runs a headless CLI per turn (`TWYF_COMMAND`, by default `["claude","-p","--output-format","json"]`), and `fake` plays a script (tests and demos).

## The demo against the real backend

```bash
backend/scripts/run_demo_server.sh
```

Then ask the demo question in workspace `demo` (see `docs/development/revision-2-backend/10-demo-scenario.md`), or run `TWYF_TEST_BACKEND_URL=http://127.0.0.1:8321 npm test` from `frontend/`.

## Documentation

- Backend plan and design: [docs/development/revision-2-backend/](docs/development/revision-2-backend/)
- UI design: [docs/development/revision-2-initialization/design.md](docs/development/revision-2-initialization/design.md)
- Backend commands and tests: [backend/README.md](backend/README.md)
- Every dependency and why it is needed: [docs/dependencies.md](docs/dependencies.md)
- Previous version: [docs/versions/revision-1.md](docs/versions/revision-1.md)

## License
[MIT](LICENSE)
