# Revision 2: the backend plan

The complete plan the backend was built from, and the record of building it. Read `implementation-brief.md` first.

| File | What it is |
|---|---|
| `implementation-brief.md` | How to work through the plan |
| `planning-brief.md` | The owner's instructions to the planner |
| `01-architecture.md` | Components, technology, layout, settings, concurrency, failures, security |
| `02-data-model.md` | The SQLite schema, the event log, versions, file copies, delete rules |
| `03-contract.md` | Wire types, operations, the event stream, the frontend changes |
| `04-agents.md` | The `.agents` folder, turns, the state machine, the verifier, runtimes |
| `05-retrieval-and-citations.md` | Ingestion, parsing, chunking, search, citations, note weights, the context map |
| `06-mcp.md` | The MCP server |
| `07-test-plan.md` | Every test and its pass condition |
| `08-implementation-plan.md` | The ordered tasks B01 to B38 and F1 to F8 |
| `09-decisions.md` | Why each choice was made, and what is deliberately left out |
| `10-demo-scenario.md` | The demo files, seed data and scripted run |
| `progress.md` | One row per finished task: commit and notes on anything done differently |
