# Contract

The single source of truth for types. `schema.json` at the repository root is exported from these models.

| File | What it is |
|---|---|
| `base.py` | `Wire` (camelCase on the wire, no extra fields) and `Opt` (an optional field that is omitted, never null) |
| `models.py` | Wire types: workspace, file, agent, note, citation, session, message, map, claim, verdict, event record, error |
| `events.py` | `AgentEvent`: the 16 events streamed while a question runs |
| `turns.py` | Every agent turn's input and output, and `TURN_MODELS` (turn type to models and skills) |
| `operations.py` | `OPERATIONS`: all 32 operations, with an input model each. Routes and MCP tools are generated from it |
| `export.py` | Writes `contract/schema.json` |
