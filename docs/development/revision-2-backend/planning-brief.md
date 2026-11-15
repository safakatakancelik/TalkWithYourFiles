# Backend planning brief

Written 2026-11-15 for a new session that starts with no context. Read this whole file before doing anything.

## Your job

You are planning the backend of Talk With Your Files, revision 2. **You do not implement it.**
A smaller model will implement the backend later, working only from the documents you write. It will not have your reasoning, this conversation or your context, and it has a small token budget per task. Everything it needs must be in your documents.

You produce design documents, an implementation plan and test criteria. The only code you may write is short illustrative snippets inside those documents (a type, a table definition, a function signature).

Where this brief says "decided", do not reopen it. Where it says "your call", reason about it, choose, and record why. Where a choice belongs to the owner and this brief does not settle it, ask the owner before you finalise the documents. Ask in batches, not one question at a time.

## Read first

| Path | Why |
|---|---|
| `README.md` | What the project is |
| `docs/development/revision-2-initialization/design.md` | The product design: concepts, agents, the huddle, the screen, the frontend and backend boundary |
| `docs/development/revision-2-initialization/prompt.md` and the three sketches beside it | The owner's original description |
| `frontend/src/backend/types.ts` | The contract the UI depends on. This is the most important file for you |
| `frontend/src/backend/mock.ts` | The only implementation of that contract today |
| `frontend/src/demo/scenario.ts` and `scenario.test.ts` | The demo scenario and the test that runs it through the contract |
| `frontend/src/App.tsx` | How the UI consumes the event stream |
| `docs/versions/revision-1.md` | The previous app, for history only. Do not reuse its design |

## What the product is

A person uploads files and asks questions about them in a chat. Agents work out the answer together and every claim is cited.

- **Chat agent**: talks with the user. Passes the question to the orchestrator and writes the final answer from the findings.
- **Orchestrator**: one per workspace. Picks translators, gives them files, runs the huddle, gathers findings and returns them to the chat agent.
- **Translator**: reads the files it is given, cites, explains, summarises and stores notes about them.
- **Verifier**: new, not in the frontend yet. See "Verifier" below.
- **Huddle**: the orchestrator broadcasts to translators. Some volunteer, some are called directly. They discuss, read files and reuse earlier notes until the matter is settled.

## Decisions already made

These come from the owner. Treat them as fixed.

### Product
1. **Workspaces** are fully isolated from each other: files, agents, notes, sessions and the context map.
2. **Files are independent of agents.** A file is stored exactly as uploaded and is never changed. Uploading a file creates no agent.
3. **Translators live in a persistent pool per workspace.** The orchestrator pairs translators and files per question: one translator per file, several on one file, or one translator on several files.
4. **Notes are the only link between files and agents.** A note records the file, the author, the kind, the citations, the date and a weight.
5. **Weights** are `off`, `low`, `normal` and `high`. `off` disables a note. A weight can be set on one note or on all of one agent's notes.
6. **Anyone can read earlier notes**: other translators, the orchestrator and the user.
7. **The record that is kept**: raw files as uploaded, every chat history, and notes with their citations.
8. **Parity rule**: anything the system can do must be possible in the UI, and through MCP. Each action is one operation on the contract.
9. **One user, running locally, no sign-in** for the first version. Every row and every event still carries a user and a workspace, so accounts can be added later without redesign.

### Citations
10. **Everything a translator produces must be based on citations**: every note and every statement it makes in the huddle or in a direct chat.
11. **Every claim in a chat answer is cited.** A citation points to a file, a location in it and the exact passage.
12. The demo's older "summary" notes carry no citations. That is a gap in the demo data, not the intended behaviour. Your plan must close it.

### Verifier
13. There is a **verifier agent type**. Verifiers check that what translators said is in fact supported by the citations they gave.
14. Verifiers are **not** used at every step. They are called into the huddle once, at the point the orchestrator thinks it has an answer, before anything is returned to the user.
15. The verifier checks **every piece of information that was shared and used** against the citations used for it.
16. **If even one citation does not fully support its claim, the orchestrator goes back to huddling with the translators.**
17. The loop is limited to a configurable number of rounds, default 3. After the limit, the user receives only the verified claims, with a clear statement of what could not be verified. Nothing unverified is ever presented as fact.

### Agents
18. Agent definitions follow the **dotagents `.agents` folder protocol**, in a `.agents` folder at the repository root or the backend root. Look up the current specification of this protocol and cite your source. Do not invent its details. If the specification leaves something open, say so and propose a convention.
19. **Translator is the base agent type.** It is defined once and used as the baseline.
20. When a user creates an agent today, they create a translator. Customised translators can have their own folders in `.agents`. The design must allow other creatable agent types later without rework.
21. Specialised translators (for example contracts, finance) are subtypes of the base translator.

### Technology
22. **Python backend.** It must stay compatible with TypeScript: the frontend is TypeScript and the two must share one contract without drifting apart.
23. **SQLite** for now.
24. **Provider-agnostic models.** For now the owner will run agents through agent harnesses such as Claude Code. Design a runtime boundary so a harness, a direct model API or a local model can sit behind it. Do not tie the design to one provider.
25. **An MCP server** is required. Any agent harness or application must be able to use this app through it.
26. **The backend is agnostic of the frontend.** It must not import, assume or depend on anything in `frontend/`.
27. **The frontend's features must keep working as they are, including the demo.** The frontend talks only to the `Backend` interface in `frontend/src/backend/types.ts`. The mock backend and the demo stay.

### Recording everything
28. **Every action is recorded**: every created agent, every uploaded file, every association of an agent with a file even when no note results, every action a user takes, every action the orchestrator or any agent takes. Each record has its **source**: who or what did it, and through which door (UI, API, MCP, internal).
29. **Everything is versioned**: agents, their definitions, skills, prompts and anything else that shapes behaviour. Store the values in the database with version numbers, so any past action can be tied to the exact versions that produced it.
30. **Slowly changing dimensions matter.** Use lookup tables, linking tables and normalised entities. History must be queryable: what was true at a given time.

### Quality
31. **Types are central.** Design around types. This is a strong preference and not a hard rule: where another approach is clearly better, choose it and explain.
32. **Tests must cover everything**, with both unit tests and integration tests.

## What you must reason about

The owner has said they are not an expert in several of these and wants your judgement. For each, choose, justify briefly, and note what you rejected.

### Contract and types
- One source of truth for types across Python and TypeScript. For example Python models that generate a schema and TypeScript types, or a schema that generates both. Include a check that fails when the two drift.
- The transport between frontend and backend, including how the agent event stream is delivered (for example server-sent events or WebSocket), and how a running question is cancelled.
- The exact additions the contract needs: the verifier (new agent kind, new events for verification and its verdicts, going back to the huddle), citations on every note, errors as events, and anything else you find. List every change to `types.ts`. Prefer additions over changes.
- The frontend work that follows: an HTTP implementation of `Backend` beside the mock, how the app chooses between them, and how verifiers are shown. Plan this as tasks too, but keep it minimal. The owner likes the current design.

### Data model
- A full SQLite schema: tables, keys, constraints and indexes.
- How to record every action. The owner suggested an `app_events` table. Decide between an append-only event log beside current-state tables, full event sourcing, or another standard approach, and say why. Define the event taxonomy, the actor and source model, and the identifiers that tie events together (session, question, huddle round, cause).
- How versioning works for agents, skills and prompts when their source of truth is files in `.agents`. For example, snapshot each definition into the database by content hash when it is loaded or changed.
- Which slowly-changing-dimension technique applies to which entity.
- How raw files are stored and identified (for example by content hash), and how duplicates and re-uploads behave.
- What "delete" means in a system that records everything.
- Migrations.

### Files and retrieval
- Parsing per file type, chunking, embeddings, and where vectors live while the database is SQLite.
- How a citation is located precisely enough to be checked: file version, position, exact quote.
- A mechanical citation check (the quoted text exists at that position in that file version) that runs before the verifier's judgement.
- How note weights affect retrieval and answers.
- The context map: how entities and links are extracted and stored.

### Agents and orchestration
- The orchestrator's loop as an explicit state machine, including the verifier step, the return to the huddle and the round limit.
- What exactly a verifier receives and returns. A claim-by-claim verdict structure.
- How claims are extracted from an answer so each can be checked.
- How translators volunteer, and how the orchestrator decides whom to call.
- The runtime boundary of decision 24, and a scripted fake runtime for tests.
- The layout of `.agents`: the base translator, the verifier, the orchestrator, the chat agent, customised translators, and skills.

### MCP server
- Tools, resources and prompts to expose, following the parity rule.
- The HTTP API and the MCP server must be thin layers over one shared service layer, so they cannot diverge.
- Transport and how it is run beside or inside the backend.

### Things the owner did not mention
Consider each and include what belongs:
- **Untrusted content.** File contents are data, never instructions. Plan defences against prompt injection from uploaded files, and against path traversal and oversized uploads.
- **Privacy.** Everything local by default. State exactly what leaves the machine with each runtime choice.
- **Failure handling.** Model errors, timeouts, partial huddles, cancelled questions, crashes mid-question, and what the event log shows in each case.
- **Concurrency.** Several questions or uploads at once on SQLite.
- **Cost and performance.** Token and time tracking per action, recorded as events.
- **Observability.** Logs, and how the event log is inspected.
- **Configuration and secrets.**
- **Answer quality evaluation.** A small evaluation set beyond the tests, starting from the demo scenario.
- **Project layout, dependency management, linting, type checking and CI.**

## Tests

Plan tests before tasks. The smaller model will write code to pass them.

- **Unit tests** for every module, including the state machine, the citation check, versioning, and each repository.
- **Integration tests** through the HTTP API and through the MCP server, on a temporary database, with the scripted fake runtime. No test may need a network connection or an API key.
- **The demo scenario is a required integration test.** Load the six demo files and run the demo question against the real backend with a scripted runtime. `frontend/src/demo/scenario.test.ts` already runs through the `Backend` interface so that it can be pointed at a real backend. Extend the scenario to include the verifier step, one failed verification that sends the huddle back, and citations on every note.
- **Contract tests** that prove the Python and TypeScript types agree.
- **Recording tests** that prove each kind of action writes its event with the right actor, source and versions.
- State the coverage expectation and how it is measured.

## What you deliver

Write these into `docs/development/revision-2-backend/`. Adjust the split if you have a better one, but keep one topic per file.

| File | Content |
|---|---|
| `01-architecture.md` | Components, boundaries, technology choices with reasons, project layout |
| `02-data-model.md` | Full schema, event taxonomy, versioning, slowly changing dimensions, migrations |
| `03-contract.md` | Types, API, event stream, type generation, every change to `types.ts`, frontend tasks |
| `04-agents.md` | `.agents` layout, agent types, orchestration state machine, verifier, runtime boundary |
| `05-retrieval-and-citations.md` | Ingestion, retrieval, citation format, mechanical check, weights, context map |
| `06-mcp.md` | Tools, resources, transport, parity with the API |
| `07-test-plan.md` | Every test, grouped by level, with its pass condition |
| `08-implementation-plan.md` | Ordered tasks for the smaller model |
| `09-decisions.md` | Each decision you made, the alternatives and why. Open questions for the owner |

### Rules for the implementation plan

The implementer is a smaller model with no context and a small budget per task.

- Each task is small enough to finish in one sitting and stands alone.
- Each task states: its goal, the documents and sections to read, the files to create or change, the exact types or signatures involved, the tests to write or make pass, the command that proves it is done, and which tasks it depends on.
- Order the tasks so the project runs and its tests pass after every task.
- Put the contract, the types and the schema first. Put the fake runtime before anything that calls a model.
- Never write "as discussed" or "see above". Name the file and section.
- Mark the points where the owner should review before work continues.

## How to work

1. Read the files in "Read first".
2. Research what you need to verify: the dotagents `.agents` protocol, the current MCP specification and Python SDK, and the options for vectors in SQLite. Cite sources in `09-decisions.md`.
3. Send the owner your questions in one batch.
4. Write the documents.
5. Check them against this brief: every numbered decision is honoured, and every item under "What you must reason about" has an answer.
6. Commit the documents on the `revision-2` branch. Push only if the owner asks.
