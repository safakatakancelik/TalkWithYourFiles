# Runtimes

The boundary to a model. Nothing outside this folder knows which runtime is in use.

| File | What it is |
|---|---|
| `base.py` | The `AgentRuntime` protocol, `TurnRequest`, `TurnResult` |
| `runner.py` | `TurnRunner`: renders the prompt, records the turn, calls the runtime, validates, retries |
| `fake.py` | A scripted runtime for tests and the demo (`--runtime fake --fake-script`) |
| `queue.py` | The default: turns wait until a harness claims and submits them |
| `command.py` | Runs a headless CLI per turn (`TWYF_COMMAND`) |
