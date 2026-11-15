# Talk With Your Files, revision 2: design

Status: second version. First written 2026-11-12, revised 2026-11-15 to make files and agents independent (see "Files, agents and notes"). Based on [prompt.md](prompt.md), the three sketches in this folder and a question round with the author.
The UI in `frontend/` implements this document against a mock backend. No real backend exists yet.

## Why this app exists

From [sketch 3](sketch-3-why-notes.jpg): a person has business questions and many files, and wants answers they can trust.

| Goal | How the app meets it |
|---|---|
| Reliable | Production-grade RAG. Every claim in an answer carries a citation to a passage in a file. |
| Private | A local database and open source integrations. Files are embedded per user. |
| Easy to use | Agent orchestration with a clear purpose, a simple UI, and later an API and MCP server so any harness can use it. |

## How a person uses it

1. Open the app and pick a workspace.
2. Upload files in the explorer. Files are stored as they are and belong to no agent.
3. Ask a question in the chat.
4. Watch the agents work it out in the huddle, or ignore the stage and wait for the answer.
5. Read the answer and click any citation to see the passage it came from.

## Concepts

- **Workspace**: an isolated container. Files, agents, notes, sessions and the context map all belong to one workspace, and nothing crosses between workspaces.
- **File library**: inside a workspace, files are shared by all sessions. A file is uploaded once.
- **Session**: one conversation with the chat agent. Sessions are listed with the latest on top.
- **Context map**: a graph of files and the entities they mention (people, companies, dates, decisions). It belongs to the workspace and grows as files are added and questions are answered.
- **Citation**: a numbered marker in an answer that points to a file, a location in it, the passage, and the translator that found it.

## Agents

| Agent | Count | Role |
|---|---|---|
| Chat agent | One per session | Talks with the user. Passes the question to the orchestrator and writes the final answer from the findings. It is not drawn on the stage; it lives in the chat. |
| Orchestrator | One per workspace | Asks translators questions, runs the huddle, gathers findings and returns them to the chat agent. |
| Translator | A pool per workspace | Reads the files the orchestrator gives it. It can cite, explain and summarise them, talk conversationally, and store what it finds as notes. |

## Files, agents and notes

Files and agents are fully independent. Neither holds a reference to the other.

- **Files** are stored exactly as uploaded. Uploading a file creates no agent.
- **Translators** live in a persistent pool per workspace. The pool starts with generic translators. Specialised translators (for example contracts or finance) are subclasses of the generic one and are added over time.
- **The orchestrator pairs them per question.** It decides which translators work on which files: one translator per file, several on one file, or one translator on several files.
- **Notes** are the only link between the two. When a translator works on a file it stores a note: a summary, an interpretation or a finding, with citations into the file. A note records the file, the author, the kind, the date and a weight.
- **Anyone can read earlier notes.** Another translator on the same file, the orchestrator and the user can all look them up and build on them.
- **Weights**: every note is `off`, `low`, `normal` or `high`. `off` disables it. A weight can be set on one note or on all of one agent's notes at once.
- **Kept as the record**: the raw files, every chat history, and the notes with their citations.

## The huddle

1. The chat agent passes the user's question to the orchestrator.
2. The orchestrator broadcasts a message to all, some or none of the translators.
3. Translators that think they can help walk into the huddle circle. This is **volunteering**. The orchestrator gives each translator in the huddle the file or files to work on.
4. The orchestrator can also bring a translator in by its own decision, or because the user named it. This is being **called**.
5. In the circle, the agents discuss the question with the orchestrator and with each other. Translators read the files they were given, reuse earlier notes, save new notes, and give each other context.
6. When the matter is settled, the translators walk back out, and the orchestrator returns the findings to the chat agent.
7. The chat agent writes the answer. Everything is cited.

## Screen layout

```
+------------------------------------------------------------------+
| Talk With Your Files   [workspace]            [Run demo] [theme] |
+---+--------+---------------------------------------+-------------+
| E | Files  |  translator          translator      | Huddle log  |
| A | file   |        . - - - - - .                  |             |
| S | file   |       (   huddle    )   translator    |             |
| C | file   |        ` - - - - - '                  |             |
|   | file   |          orchestrator                 |             |
|   +--------+-----------[ v ^ ]---------------------+-------------+
|   |  chat with the chat agent                                    |
|   |  [ user input                                        ] Send  |
+---+--------------------------------------------------------------+
```

### Stage (above the divider)

- **Files have their own shelf** on the left of the stage, drawn as document tiles and never as figures. A tile shows the file type, how many notes exist about it, and which translators have it open. Clicking a tile opens the file's card: the file and every note about it, each with its author and weight.
- Translators are figures labelled with their own name and their kind (generic or a speciality), never with a file name. While a translator works on a file, a small tag under it names the file.
- The huddle is a dotted circle in the middle. The orchestrator stands just below it and steps into it while a huddle runs.
- Idle translators stand outside the circle, around it. Translators in the huddle stand inside it.
- Up to 10 translators are all shown. Above 10, the ones in the huddle are always shown and the idle ones beyond the limit collapse into a "+N more" group that opens the explorer.
- The agent that is speaking shows a short speech bubble. A translator that is reading its file shows a reading mark.
- The **huddle log** on the right keeps the full discussion, with citations, so nothing is lost. It can be hidden.
- Clicking a translator opens its card: its notes across all files, a control to set the weight of all of them, and a small chat with that agent alone.

### Divider

A button with two arrows sits in the middle of the divider. The chat has three sizes, and the arrows move between them:

| Size | Stage | Chat |
|---|---|---|
| Full | Hidden | Whole area |
| Half | Top half | Bottom half |
| Bar | Whole area | One input row |

### Chat (below the divider)

- A normal conversation with the chat agent.
- While a huddle runs, the pending answer shows a live status line, such as "Orchestrator is asking 6 translators". With the chat at full size, this is how the user follows the work.
- Answers carry numbered citation markers. Clicking one opens a panel on the right with the file name, the location and the passage with the quoted part highlighted. The file and the translator that found it are highlighted on the stage.
- Naming a file in a question makes the orchestrator put a translator on it.

### E, S and C panels

Four buttons on the left edge. Each opens a drawer from the left, over the stage and chat.

- **E, explorer**: files only. Uploads happen here. A table of name, type, size, date and note count.
- **A, agents**: the translator pool. A "New agent" button creates a translator from a name and an optional speciality. A table of name, kind, note count and how many files each has worked on.
- The file card has a field for the user to add their own note about the file.
- **S, sessions**: a short table of sessions with the latest on top, and a button for a new session.
- **C, context map**: the mind map of files and entities and the links between them. It can expand to full width.

### Look

Clean and calm, with a light and a dark theme. The stage keeps the sketch's character: simple figures and a dotted circle.

## Frontend and backend boundary

The frontend must not depend on any backend. It talks to one TypeScript interface, `Backend`, in `frontend/src/backend/types.ts`:

- Reads: workspaces, files, agents, notes, sessions, session messages and the context map.
- Writes: create a session, upload a file, create an agent, add a user note, set the weight of notes.
- `ask(workspace, session, question)` returns a stream of **agent events**. The UI draws whatever the stream says.
- `askTranslator(workspace, agent, question)` returns one reply from one translator.

Agent events:

| Event | Meaning | What the UI does |
|---|---|---|
| `status` | Free text progress | Updates the status line in the chat |
| `broadcast` | Orchestrator messages a set of translators | Pulse from the orchestrator, log entry |
| `join` | A translator enters the huddle, `volunteered` or `called` | The translator walks into the circle |
| `assign` | The orchestrator gives a translator a file | The file tile shows the translator, and the translator shows the file |
| `reading` | A translator is reading its file | Reading mark on the translator |
| `note` | A translator stored a note about a file, with citations | The note appears on the file's and the agent's card |
| `say` | An agent speaks in the huddle, with optional citations | Speech bubble, log entry |
| `leave` | Translators leave the huddle | They walk back out |
| `context` | New nodes and links for the context map | The map grows |
| `answer` | The chat agent's final answer with citations | Replaces the pending message |

**Parity rule**: anything the system can do must also be possible somewhere in the UI, and every such action is one method on `Backend`. The same methods are what the MCP server will expose later, so the UI and MCP stay equal. Not yet in the UI: renaming or removing files, agents, notes and sessions, and creating workspaces.

A real backend only has to implement `Backend` and emit these events, over whatever transport it chooses. The mock in `frontend/src/backend/mock.ts` is the one implementation today, and `frontend/src/backend/index.ts` is the only place that selects it.

### Mock behaviour

- An uploaded file is only listed by name and size. Its content is never read and never leaves the browser. It appears on the file shelf, and no agent is created for it.
- Every workspace starts with two generic translators.
- A typed question runs a generic simulated huddle and returns an answer marked as a placeholder.
- Nothing is saved. Reloading the page resets everything.

## Demo scenario, kept as a test case

`frontend/src/demo/scenario.ts` holds a workspace for a made-up company, Harbor Coffee Roasters, and a scripted list of agent events.

- **Files**: a supplier contract, Q3 sales, October board notes, a pricing policy, an HR handbook and an office lease. Each already has a summary note from an earlier read.
- **Translators**: two generic ones, plus contracts, finance and people translators.
- **Question**: "Our coffee supplier is raising prices in January. Can we keep our current prices and still hit our margin target?"
- **What happens**: the orchestrator asks all five translators. The contracts, finance and one generic translator volunteer and are given the contract, the sales file and the board notes. The orchestrator calls the second generic translator directly and gives it the pricing policy. The people translator stays out. Each of the four saves a note with a citation, and the finance translator reuses the contracts translator's note. The answer cites four files, and the context map gains a new entity.

"Run demo" in the top bar switches to this workspace and plays the script. While it plays, controls allow pause, step, speed and restart.
`frontend/src/demo/scenario.test.ts` checks the script through the `Backend` interface, so the same scenario can later be run against a real backend.

## Open questions

- How weights change retrieval and answers once there is a backend.
- How specialised translators are created and how the orchestrator chooses between them and generic ones.
- Whether the user can write notes of their own (the data model allows it).
- How the stage should behave with hundreds of files, beyond the "+N more" group.
- Whether a session can limit which files take part.
- What else translators will be able to do beyond citing, explaining and summarising.
- Sign-in and what "user scoped" means once there is more than one user.
- The shape of the API and MCP server.
