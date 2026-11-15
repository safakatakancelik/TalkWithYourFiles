# Implementation brief

Written 2026-11-15 for a session that starts with no context. Read this whole file before doing anything. It tells you what the project is, where the plan is, how to work, and how to pick up where an earlier session stopped.

## Your job

You are implementing the backend of Talk With Your Files, revision 2, and the small frontend changes that go with it. The design is finished. **You do not redesign it.** You carry out the tasks in `08-implementation-plan.md`, one at a time, in order.

All documents named here are in `docs/development/revision-2-backend/`.

## What the product is

A person adds files to a workspace and asks questions about them in a chat. Agents work out the answer together, and every claim in the answer is cited to an exact passage in a file.

- **Chat agent**: talks with the user and writes the final answer.
- **Orchestrator**: one per workspace. Picks translators, gives them files, runs the discussion (the "huddle") and drafts the claims.
- **Translators**: a pool per workspace. They read passages of the files they are given, quote them, and store notes.
- **Verifier**: checks every claim against its cited passages before anything reaches the user. If one claim fails, the huddle goes back to work. After a set number of rounds, only verified claims are given to the user.

Three ideas run through the whole design. Keep them in mind in every task:

1. **Nothing unverified is presented as fact.** A citation can only be created from a quote that is found, character for character, in the file's text.
2. **Everything is recorded and nothing is removed.** Every action writes an event with who did it and through which door. Every delete is soft. The app keeps its own copy of every file and every version of it, and never changes or removes a copy.
3. **One list of operations feeds both doors.** The HTTP API and the MCP server are generated from the same registry. You never write a route or an MCP tool by hand.

## Where things stand

- `frontend/` holds a working React UI on a mock backend with a scripted demo. It must keep working at every step.
- `backend/` does not exist yet. Task B01 creates it.
- `.agents/` does not exist yet. Task B09 creates it.
- Branch: `revision-2`. Work on it. Do not create other branches.

**Find out what is already done before you start:**

1. Read `progress.md` in this folder if it exists. It lists each finished task.
2. Run `git log --oneline -30` and look for task ids in the commit messages.
3. If `backend/` exists, run the full check from `backend/` (see "The full check" below). It must pass before you start a new task. If it fails, fix that first and say so.

Then continue with the first task that is not done.

## The documents

Do not read them all at once. Each task lists the sections it needs under **Read**. Read those, and this file.

| File | What it holds | Read it when |
|---|---|---|
| `08-implementation-plan.md` | The ordered tasks B01 to B38 and F1 to F8, and the rules for doing them | Always. Its "How to use this plan" section first, then your task |
| `01-architecture.md` | Components, technology, project layout, settings, concurrency, failure handling, security | A task names a section |
| `02-data-model.md` | The full SQLite schema, the event log, versioning, file copies and versions, delete rules | A task names a section |
| `03-contract.md` | Wire types, the operation list, the event stream, every change to `types.ts` | A task names a section |
| `04-agents.md` | The `.agents` folder, turns, the state machine, the verifier, the runtime boundary | A task names a section |
| `05-retrieval-and-citations.md` | Ingestion, parsing, chunking, search, citations and their mechanical check, note weights | A task names a section |
| `06-mcp.md` | The MCP server | Task B33 |
| `07-test-plan.md` | Every test and its pass condition | Every task: look up each test the task names |
| `10-demo-scenario.md` | The demo files, seed data and scripted run | Tasks B34, F7, F8 |
| `09-decisions.md` | Why each choice was made, and section 3: what is deliberately not in version 1 | When you wonder why, or whether to build something |
| `planning-brief.md` | The owner's original instructions to the planner | Only if you need the background |

There are no open questions in these documents. Where a document says something is not in version 1, that is a decision. Do not build it and do not ask about it.

## How to do one task

1. Read the task in `08-implementation-plan.md`, then the sections under **Read**.
2. Look up each test named under **Tests** in `07-test-plan.md` and write those tests first, from their pass conditions.
3. Write the code. Use the names, signatures and file paths the task gives, exactly.
4. Run the task's **Done when** command, then the full check.
5. Add a row to `progress.md` (format below).
6. Commit with a message that starts with the task id, for example `B07 Add the database schema and migrations`. End the message with the attribution line your harness tells you to use.
7. If the next line in the plan is an **OWNER REVIEW**, stop and tell the owner what to look at. Otherwise go on to the next task.

### The full check

From `backend/`:

```
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

From `frontend/`, after any frontend task:

```
npm run build && npm test
```

### progress.md

Create it in this folder with the first task and keep it up to date. One row per finished task:

```
| Task | Done | Commit | Notes |
|---|---|---|---|
| B01 | 2026-11-16 | a1b2c3d | |
| B02 | 2026-11-16 | d4e5f6a | Added one helper not in the plan: ids.is_id(), used by tests |
```

Use **Notes** for anything the next session must know: a name that differs from the plan and why, a test you could not write as described, a dependency version you had to pin. Keep it to one line. If there is nothing to say, leave it empty.

## Rules

- **Follow the plan.** If a task and a design document disagree, or a task cannot be done as written, stop and ask the owner. Say which file and section, and what the conflict is. Do not pick one and carry on.
- **Build only what is named.** No extra options, abstractions, endpoints, fields or configuration. `09-decisions.md` section 3 lists what is left out on purpose.
- **Tests come first and stay honest.** Do not weaken a test's pass condition to make it pass. Do not skip or delete a test. No test may need a network connection, an API key or a model download: use the fake runtime, the `hash` embedder and the `basic` parser.
- **Types everywhere.** Pydantic models for anything that crosses a boundary, type hints on every function, `pyright` strict with no ignores unless a comment says why.
- **The backend never imports from `frontend/`.** The frontend talks only to the `Backend` interface in `frontend/src/backend/types.ts`.
- **Never write a route or an MCP tool by hand.** Add an operation to `contract/operations.py` and both doors get it.
- **Never open stored file content for writing, and never remove it.** Every version of every file stays in the data folder.
- **Everything refers to a specific file version.** Notes, citations, extractions and assignments carry a `file_version_id`. Never move one to a newer version.
- **Every service function that changes something records its event in the same transaction.**
- **Do not call a model.** All agent work goes through `runtime/`. In tests that is always `FakeRuntime`.
- **Frontend changes are small.** Change only what a frontend task names. Do not restyle, rename or rearrange.
- **Do not edit the design documents** (`01` to `10`, the briefs). If you believe one is wrong, tell the owner.
- **Git.** Commit after every task on `revision-2`. Do not push unless the owner asks. Do not amend or rewrite earlier commits.

## Facts that were checked, and facts that were not

Checked by running them on Python 3.13 and 3.14 when the plan was written:

- These install together: `mcp` 2.3.0, `pydantic` 2.14.3, `uvicorn` 0.54.0, `sqlite-vec` 0.1.9, `fastembed` 0.9.1, `pypdf` 7.1.0, `python-docx` 1.2.0, `httpx` 0.28.1, `reportlab` 5.1.0.
- `sqlite-vec` loads into the standard `sqlite3` module with `sqlite_vec.load(conn)`, and SQLite has FTS5.
- The MCP SDK: `from mcp.server.mcpserver import MCPServer`; `server.add_tool(fn, name=..., description=...)`; `@server.resource("scheme://{param}/x")`; `@server.prompt()`; `server.run(transport="stdio" | "streamable-http")`; and in tests `from mcp import Client`, then `async with Client(server) as client:` with `client.list_tools()`, `client.call_tool(name, arguments)`, `client.list_resource_templates()`. A tool that returns a Pydantic model gives `structured_content` on the result.

Not run, so check them against their documentation when the task comes:

- **FastAPI**: adding routes with `app.add_api_route`, streaming responses, lifespan, serving static files.
- **Docling** (task B37 only): converting a document and reading each item's page number and bounding box.
- **`json-schema-to-typescript`** (task F1): the exact command-line flags. The check that matters is that `contract.check.ts` compiles.
- **`fastembed`** model loading (task B37 only).

If one of these behaves differently from what a task assumes, do the smallest thing that meets the task's tests, and write one line about it in `progress.md`.

## When to stop and ask the owner

- At every **OWNER REVIEW** line in the plan. There are five.
- When a task and a document disagree, or something a task needs does not exist.
- When a test in `07-test-plan.md` cannot pass without changing the design.
- When the full check fails for a reason outside your task and you cannot fix it in a few minutes.
- Before any action outside this repository, and before pushing.

When you ask, give the file and section, what you found, and what you suggest. Then wait.

## What to tell the owner at the end of a session

1. Which tasks you finished, with their commits.
2. Whether the full check passes. If it does not, show the failing output.
3. Anything you did differently from the plan, and why.
4. The next task, and whether an owner review comes before it.
