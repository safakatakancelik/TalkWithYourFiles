# 03 Contract

Part of the revision 2 backend plan. This document defines the wire types, the HTTP API, the event stream, how types are shared between Python and TypeScript, every change to `frontend/src/backend/types.ts`, and the frontend work.

## 1. One source of truth

```
backend/src/twyf/contract/*.py   Pydantic models            (written by hand, the source)
        │  uv run twyf export-contract
        ▼
contract/schema.json             JSON Schema + operation list (generated, committed)
        │  npm run gen:contract   (json-schema-to-typescript)
        ▼
frontend/src/backend/contract.gen.ts                          (generated, committed)
        │  compared by the TypeScript compiler
        ▼
frontend/src/backend/types.ts    the UI's contract            (written by hand, stays readable)
frontend/src/backend/contract.check.ts                        (fails to compile on drift)
```

`types.ts` stays hand-written because it is the file the UI reads and the owner likes it. `contract.check.ts` proves it equals the generated types:

```ts
import type * as H from './types';
import type * as G from './contract.gen';
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
export const checks: true[] = [
  true as Same<H.Workspace, G.Workspace>, true as Same<H.FileItem, G.FileItem>, true as Same<H.Agent, G.Agent>,
  true as Same<H.Note, G.Note>, true as Same<H.Citation, G.Citation>, true as Same<H.Session, G.Session>,
  true as Same<H.ChatMsg, G.ChatMsg>, true as Same<H.ContextMap, G.ContextMap>, true as Same<H.AgentEvent, G.AgentEvent>,
  true as Same<H.Claim, G.Claim>, true as Same<H.Verdict, G.Verdict>, true as Same<H.Unverified, G.Unverified>,
];
```

**Drift is caught three ways:** CI regenerates both generated files and fails on any `git diff`; `tsc` fails on `contract.check.ts`; and the demo scenario test runs the TypeScript client against the real server (`07-test-plan.md` section 5).

### Pydantic conventions

```python
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic.json_schema import SkipJsonSchema

class Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)

type Opt[T] = T | SkipJsonSchema[None]      # an optional field that is omitted, never null
```

- Python uses snake_case. The wire uses camelCase through the alias generator.
- Responses are serialised with `model_dump(mode="json", by_alias=True, exclude_none=True)`.
- An optional field is declared `x: Opt[str] = None`, so the schema says "string, not required" and TypeScript gets `x?: string`.
- Requests are validated with `extra="forbid"`.

## 2. Wire types

Python models in `contract/models.py`. Each has the same name and fields as the TypeScript type in section 6. Fields marked `?` are optional.

| Model | Fields |
|---|---|
| `Workspace` | `id`, `name` |
| `FileItem` | `id`, `name`, `type: FileType`, `size_kb: int`, `uploaded_at`, `status?: 'processing' \| 'ready' \| 'unreadable'`, `version?: int` |
| `Agent` | `id`, `name`, `specialty` |
| `Citation` | `n: int`, `file_id`, `agent_id`, `location`, `passage`, `quote`, `id?`, `extraction_id?`, `start?: int`, `end?: int`, `page?: int` |
| `Note` | `id`, `file_id`, `author_id`, `kind: 'summary' \| 'interpretation' \| 'finding'`, `text`, `citations: list[Citation]`, `created_at`, `weight: Weight` |
| `Session` | `id`, `title`, `updated_at`, `message_count: int` |
| `Unverified` | `text`, `reason` |
| `ChatMsg` | `id`, `role: 'user' \| 'assistant'`, `text`, `citations?`, `pending?`, `status?`, `placeholder?`, `unverified?: list[Unverified]`, `error?: str` |
| `MapNode` | `id`, `label`, `kind: 'file' \| 'entity'` |
| `MapLink` | `from_` (alias `from`), `to` |
| `ContextMap` | `nodes`, `links` |
| `Claim` | `id`, `text`, `kind: 'quoted' \| 'derived'`, `citations: list[int]`, `derived_from?: list[str]`, `calculation?: str` |
| `Verdict` | `claim_id`, `verdict: 'supported' \| 'partly_supported' \| 'unsupported' \| 'mechanical_fail'`, `reason` |
| `TranslatorReply` | `text`, `citations: list[Citation]` |
| `EventRecord` | `id: int`, `occurred_at`, `event_type`, `actor_id`, `source`, `workspace_id?`, `session_id?`, `question_id?`, `round_id?`, `turn_id?`, `cause_event_id?`, `entity_type?`, `entity_id?`, `payload: dict` |
| `ErrorBody` | `error: {code: str, message: str, details?: dict}` |

Mapping rules between the database and the wire:

- `Note.author_id` and `Citation.agent_id` and `say.agent_id`: the workspace's orchestrator agent is sent as the constant `orchestrator`, its verifier as `verifier`, the user as `user`. Any other actor is sent as its id.
- `list_agents` returns translators only. The orchestrator, verifier and chat agent are never in the list.
- `FileItem.size_kb = max(1, round(size_bytes / 1024))`. `uploaded_at` is the creation time of the current file version.
- `FileItem.status`: `processing` until ingestion ends, then `ready`, or `unreadable` when no extraction succeeded.
- `Citation.n` is unique within the list that carries it. Inside a question every distinct citation gets a number in order of creation, and `say`, `note` and `verify` events use that number. The `answer` event and stored messages renumber from 1 in order of first appearance in the text. Notes written outside a question number from 1.
- `Citation.passage` always contains `Citation.quote`.

## 3. Operations

`contract/operations.py` holds `OPERATIONS: list[Operation]`. This list is the whole surface of the system.

```python
class Operation(BaseModel):
    name: str                      # snake_case. Also the MCP tool name
    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str                      # under /api/v1, for example "/workspaces/{ws}/files"
    input: type[Wire] | None       # path, query and body fields in one model
    output: Any                    # a Wire model, list[Wire] or None
    handler: str                   # "twyf.services.files:upload". A string, so contract/ imports nothing
    kind: Literal["json", "upload", "stream"] = "json"
    backend_method: str | None     # the method on the TypeScript Backend interface, when there is one
    description: str               # shown as the MCP tool description
```

Binding rule: an input field whose name appears in `path` comes from the path. For `GET` the other fields come from the query string. For other methods they come from the JSON body. `upload` operations read `multipart/form-data` with one part named `file`.

| name | Method and path | Other input fields | Output | Backend method |
|---|---|---|---|---|
| `list_workspaces` | GET `/workspaces` | | `list[Workspace]` | `listWorkspaces` |
| `create_workspace` | POST `/workspaces` | `name` | `Workspace` | `createWorkspace` |
| `rename_workspace` | PATCH `/workspaces/{ws}` | `name` | `Workspace` | `renameWorkspace` |
| `delete_workspace` | DELETE `/workspaces/{ws}` | | none | `deleteWorkspace` |
| `list_files` | GET `/workspaces/{ws}/files` | | `list[FileItem]` | `listFiles` |
| `upload_file` | POST `/workspaces/{ws}/files` (upload) | the file part | `FileItem` | `uploadFile` |
| `get_file_text` | GET `/workspaces/{ws}/files/{file_id}/text` | `start?`, `end?` | `{text, start, end, total}` | |
| `list_agents` | GET `/workspaces/{ws}/agents` | | `list[Agent]` | `listAgents` |
| `create_agent` | POST `/workspaces/{ws}/agents` | `name`, `specialty` | `Agent` | `createAgent` |
| `list_notes` | GET `/workspaces/{ws}/notes` | | `list[Note]` | `listNotes` |
| `add_note` | POST `/workspaces/{ws}/notes` | `file_id`, `text` | `Note` | `addNote` |
| `set_note_weight` | POST `/workspaces/{ws}/notes/weight` | `note_ids`, `weight` | none | `setNoteWeight` |
| `list_sessions` | GET `/workspaces/{ws}/sessions` | | `list[Session]`, latest first | `listSessions` |
| `create_session` | POST `/workspaces/{ws}/sessions` | `title` | `Session` | `createSession` |
| `get_messages` | GET `/workspaces/{ws}/sessions/{session_id}/messages` | | `list[ChatMsg]` | `getMessages` |
| `get_context_map` | GET `/workspaces/{ws}/context-map` | | `ContextMap` | `getContextMap` |
| `ask` | POST `/workspaces/{ws}/sessions/{session_id}/questions` (stream) | `question` | stream of `AgentEvent` | `ask` |
| `get_question_events` | GET `/workspaces/{ws}/questions/{question_id}/events` (stream) | `after?: int` | stream of `AgentEvent` | |
| `cancel_question` | POST `/workspaces/{ws}/questions/{question_id}/cancel` | | none | `ask` (through its `AbortSignal`) |
| `ask_translator` | POST `/workspaces/{ws}/agents/{agent_id}/ask` | `question` | `TranslatorReply` | `askTranslator` |
| `list_events` | GET `/events` | `workspace?`, `question?`, `type?`, `after?: int`, `limit?: int = 200` | `list[EventRecord]` | |
| `claim_turn` | POST `/runtime/turns/claim` | `worker`, `wait_s?: int = 25` | `TurnOffer` or none | |
| `submit_turn` | POST `/runtime/turns/{turn_id}/submit` | `lease_token`, `output: dict`, `usage?` | `{accepted: bool, errors?: list[str]}` | |
| `fail_turn` | POST `/runtime/turns/{turn_id}/fail` | `lease_token`, `reason` | none | |

`GET /api/v1/health` returns `{status: "ok", version, runtime}`. It is not an operation.

`TurnOffer` and the turn operations are defined in `04-agents.md` section 6.3. They are the door for a harness that does agent work. They are not user actions, so the parity rule does not require them in the UI.

`list_events`, `get_file_text` and `get_question_events` have no UI yet. This is a known gap in the parity rule (`09-decisions.md` section 3).

### Errors

Every failed request returns `ErrorBody` with one of these codes:

| HTTP | code | When |
|---|---|---|
| 400 | `validation` | The input does not match the model, or a rule in `02-data-model.md` section 7 is broken |
| 404 | `not_found` | Unknown or deleted workspace, file, agent, session, question or turn. Also an id from another workspace |
| 409 | `conflict` | The session already has a running question. A turn lease is stale |
| 413 | `too_large` | Upload above `TWYF_MAX_UPLOAD_MB` |
| 500 | `internal` | Anything else. The message is generic. Details go to the log |

Services raise `twyf.services.errors.ServiceError(code, message, details)`. `http/errors.py` maps it. The MCP server passes the code and message through as a tool error.

### Request headers

| Header | Meaning |
|---|---|
| `X-TWYF-Source` | `ui` or `mcp`. Anything else, or absent, is recorded as `api` |
| `X-TWYF-Client` | Free text name of the client, recorded in `app_events.client` |
| `X-Request-Id` | Optional. Generated when absent. Returned on the response |

## 4. The agent event stream

### 4.1 Events

`contract/events.py` defines `AgentEvent` as a Pydantic union discriminated on `type`. Existing events are unchanged. New ones are marked.

| type | Fields | Meaning |
|---|---|---|
| `started` (new) | `question_id` | Always first. Gives the id needed to cancel or replay |
| `status` | `text` | Progress line |
| `broadcast` | `text`, `to: list[str]` | Orchestrator messages translators |
| `join` | `agent_id`, `how: 'volunteered' \| 'called'` | |
| `assign` | `agent_id`, `file_id` | |
| `reading` | `agent_id` | |
| `note` | `note: Note` | |
| `say` | `agent_id`, `text`, `citations?` | Only the orchestrator and translators in the huddle speak |
| `verify` (new) | `round: int`, `claims: list[Claim]`, `citations: list[Citation]` | The verifier steps into the huddle and checks these claims. `Claim.citations` holds `n` values from this event's `citations` |
| `verdict` (new) | `round: int`, `passed: bool`, `verdicts: list[Verdict]` | One verdict per claim |
| `rehuddle` (new) | `round: int`, `reason`, `claim_ids: list[str]` | Verification failed. `round` is the round that now starts |
| `leave` | `agent_ids` | |
| `context` | `nodes`, `links` | |
| `answer` | `text`, `citations`, `placeholder?`, `unverified?: list[Unverified]` | Always last on success |
| `error` (new) | `code`, `message` | Always last on failure |
| `cancelled` (new) | | Always last after a cancel |

Order guarantees: `started` is first. Exactly one of `answer`, `error`, `cancelled` is last. `verdict` follows its `verify`. `rehuddle` follows a `verdict` with `passed: false`. `leave` comes after the last `verdict`. Every agent that joined has left before `answer`.

### 4.2 Transport: server-sent events

`ask` and `get_question_events` respond with `Content-Type: text/event-stream`. Each event is:

```
id: 1042
event: join
data: {"type":"join","agentId":"a_...","how":"volunteered"}

```

- `id` is the `app_events.id` of the event.
- A comment line `: ping` is sent every 15 seconds.
- The server closes the response after the final event.
- **Replay.** `get_question_events?after=<id>` sends the stored events of that question with a higher id, then keeps streaming if the question is still running. Because events are stored (`02-data-model.md` section 3), a reloaded page can pick a running question up.
- **Polling.** `get_question_events` with header `Accept: application/json` returns `{events: list[AgentEvent], lastId: int, done: bool}` at once instead of a stream. The MCP server uses this.
- **Cancel.** `cancel_question` is the only thing that cancels. Closing the connection does not, so a dropped connection or a closed tab does not lose the answer. The TypeScript client calls `cancel_question` when its `AbortSignal` fires.

Implementation, in `http/sse.py`: an in-process `EventBroker` with one `asyncio.Queue` per subscriber per question. `Recorder` publishes to it after its transaction commits. The stream handler first sends stored events with id above `after`, then live ones, skipping any id it has already sent.

Server-sent events were chosen over WebSocket: the stream is one-way, it is plain HTTP, and ids give replay for free (`09-decisions.md` D5).

## 5. Statements the engine makes about `ask`

1. `ask` validates, stores the user message, inserts the question, records `question.asked` and starts the engine task. Then it streams.
2. If the workspace has no ready files, the engine skips the huddle and answers "There are no files in this workspace yet." with no citations. `placeholder` is never set by the real backend.
3. When the question ends, the assistant message is stored with its citations and `unverified` list, and `sessions.updated_at` is set.

## 6. Every change to `frontend/src/backend/types.ts`

All are additions. No existing field, type or method is removed or changed in meaning.

```ts
// 1. FileType gains 'image'.
export type FileType = 'pdf' | 'docx' | 'csv' | 'md' | 'txt' | 'image' | 'other';

// 2. FileItem gains two optional fields.
  status?: 'processing' | 'ready' | 'unreadable';
  version?: number;

// 3. Citation gains five optional fields.
  id?: string;
  extractionId?: string;
  /** Character offsets of the quote in the file's extracted text. */
  start?: number;
  end?: number;
  page?: number;

// 4. New types.
export interface Unverified { text: string; reason: string }
export interface Claim {
  id: string;
  text: string;
  kind: 'quoted' | 'derived';
  /** The `n` of each citation that supports this claim. */
  citations: number[];
  derivedFrom?: string[];
  calculation?: string;
}
export interface Verdict {
  claimId: string;
  verdict: 'supported' | 'partly_supported' | 'unsupported' | 'mechanical_fail';
  reason: string;
}

// 5. ChatMsg gains two optional fields.
  unverified?: Unverified[];
  error?: string;

// 6. New constant beside ORCHESTRATOR.
export const VERIFIER = 'verifier';

// 7. AgentEvent gains six members, and `answer` gains one optional field.
  | { type: 'started'; questionId: string }
  | { type: 'verify'; round: number; claims: Claim[]; citations: Citation[] }
  | { type: 'verdict'; round: number; passed: boolean; verdicts: Verdict[] }
  | { type: 'rehuddle'; round: number; reason: string; claimIds: string[] }
  | { type: 'error'; code: string; message: string }
  | { type: 'cancelled' }
  | { type: 'answer'; text: string; citations: Citation[]; placeholder?: boolean; unverified?: Unverified[] }

// 8. Backend gains three methods, and uploadFile's argument gains one optional field.
  createWorkspace(name: string): Promise<Workspace>;
  renameWorkspace(ws: string, name: string): Promise<Workspace>;
  deleteWorkspace(ws: string): Promise<void>;
  uploadFile(ws: string, file: { name: string; size: number; data?: Blob }): Promise<void>;
```

The comment on `Note.authorId` becomes "An agent id, ORCHESTRATOR, VERIFIER or 'user'." The comment on `Note.citations` gains: "Required for a summary or finding written by an agent. An interpretation is guidance and may have none."

`uploadFile` is the one place where the old shape was not enough: a real backend needs the bytes. `data` is optional, so the mock keeps working unchanged.

## 7. Frontend work

Kept minimal. The tasks are F1 to F7 in `08-implementation-plan.md`. Summary:

| Area | Change |
|---|---|
| Types | Apply section 6. Add `contract.gen.ts`, `contract.check.ts` and the script `gen:contract` |
| Mock | Implement `createWorkspace`, `renameWorkspace`, `deleteWorkspace` in memory |
| HTTP backend | New `frontend/src/backend/http.ts`: `httpBackend(baseUrl): Backend`. Sends `X-TWYF-Source: ui`. `ask` reads the POST response as server-sent events with `fetch` and a stream reader, yields each event, and calls `cancel_question` when the signal aborts |
| Choosing | `frontend/src/backend/index.ts` reads `import.meta.env.VITE_BACKEND_URL`. Unset: the mock, as today. Set: `withDemo(httpBackend(url), mockBackend)` from new `router.ts`, which sends every call for workspace id `demo` to the mock and adds the demo workspace to `listWorkspaces`. "Run demo" therefore always plays the mock |
| App | Start on the first workspace from `listWorkspaces` in place of the fixed id `mine`. Pass `data: f` in `upload`. Handle the six new events in `apply` |
| Verifier on the stage | One figure labelled "Verifier" beside the orchestrator. It steps into the circle on `verify`, shows a check mark or a cross on `verdict`, and steps out on `leave`. The huddle log gets one line per `verify`, one per failed verdict with its reason, and one per `rehuddle` ("Round 2 of 3") |
| Chat | An answer with `unverified` shows a block under it: "Could not be verified" and the list. A message with `error` shows the error text in place of the pending status |
| Workspaces | Three small buttons beside the workspace select: New, Rename, Delete, using the browser's `prompt` and `confirm` |
| File badge | A style for the `image` type |
| Demo | Extend `scenario.ts` and `scenario.test.ts` as `10-demo-scenario.md` section 4 says |

Stage, layout, theme and every existing interaction stay as they are.
