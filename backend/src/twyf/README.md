# The `twyf` package

The backend's code. Each folder has its own README.

| Item | What it is |
|---|---|
| `cli.py` | The `twyf` command: serve, mcp, seed-demo, export-contract, events, eval |
| `config.py` | `Settings`: every `TWYF_*` setting with its default |
| `ids.py`, `clock.py` | New ids (`f_3fa9...`) and the current time, which tests can freeze |
| `logging_setup.py` | JSON logs with the request, question and turn ids |
| `contract/` | Every type and the operation list. Imports nothing else from `twyf` |
| `services/` | One function per operation. The only place rules live |
| `http/`, `mcp/` | The two doors, generated from the operation list |
| `orchestration/` | The state machine and the engine that runs a question |
| `runtime/` | The boundary to a model |
| `agents/` | Loads `.agents` and renders prompts |
| `files/`, `retrieval/`, `citations/`, `contextmap/` | Files, search, citations, the context map |
| `db/`, `recording/` | The database and the event log |
| `evals/` | The evaluation runner |
