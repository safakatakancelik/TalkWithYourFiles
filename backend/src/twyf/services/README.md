# Services

One function per operation, called by both doors. Each validates, changes state through the repositories and records its event in the same transaction.

| File | What it is |
|---|---|
| `workspaces.py`, `agents.py`, `files.py`, `notes.py`, `sessions.py`, `contextmap.py` | The plain data operations; `agents.py` also has `ask_translator` |
| `questions.py` | Starting, streaming, polling and cancelling a question; crash recovery; the task registry |
| `turns.py` | `claim_turn`, `submit_turn`, `fail_turn` for a harness working the queue |
| `events.py` | Reading the event log |
| `demo.py` | `twyf seed-demo` |
| `state.py` | What services need and do not receive as arguments: the settings, a connection, the jobs, the engine |
| `mapping.py` | Database to wire rules (the orchestrator is `orchestrator`, the user `user`, ...) |
| `errors.py` | `ServiceError` and the HTTP status of each code |
