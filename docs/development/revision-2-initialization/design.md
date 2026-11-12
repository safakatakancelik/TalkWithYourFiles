# Talk With Your Files, revision 2: design

Status: first version, written 2026-11-12 from [prompt.md](prompt.md), the three sketches in this folder and a question round with the author.
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
2. Upload files in the explorer. Each file gets a translator agent.
3. Ask a question in the chat.
4. Watch the agents work it out in the huddle, or ignore the stage and wait for the answer.
5. Read the answer and click any citation to see the passage it came from.

## Concepts

- **Workspace**: an isolated container. Files, agents, sessions and the context map all belong to one workspace, and nothing crosses between workspaces.
- **File library**: inside a workspace, files are shared by all sessions. A file is uploaded once.
- **Session**: one conversation with the chat agent. Sessions are listed with the latest on top.
- **Context map**: a graph of files and the entities they mention (people, companies, dates, decisions). It belongs to the workspace and grows as files are added and questions are answered.
- **Citation**: a numbered marker in an answer that points to a file, a location in it, the passage, and the translator that supplied it.

## Agents

| Agent | Count | Role |
|---|---|---|
| Chat agent | One per session | Talks with the user. Passes the question to the orchestrator and writes the final answer from the findings. It is not drawn on the stage; it lives in the chat. |
| Orchestrator | One per workspace | Asks translators questions, runs the huddle, gathers findings and returns them to the chat agent. |
| Translator | One per file today | Represents its files. It knows their content and embeddings, and can cite, explain and summarise them and talk conversationally. |

A translator holds a list of files. Today that list always has one file. The data model already allows zero or many, because a translator will later be able to represent several files.
A translator is labelled with its file name and a file type badge. With several files it will need its own name and a file count.

## The huddle

1. The chat agent passes the user's question to the orchestrator.
2. The orchestrator broadcasts a message to all, some or none of the translators.
3. Translators that think they can help walk into the huddle circle. This is **volunteering**.
4. The orchestrator can also bring a translator in by its own decision, or because the user named it. This is being **called**.
5. In the circle, the agents discuss the question with the orchestrator and with each other. Translators read their files as needed and give each other context.
6. When the matter is settled, the translators walk back out, and the orchestrator returns the findings to the chat agent.
7. The chat agent writes the answer. Everything is cited.

## Screen layout

```
+--------------------------------------------------------------+
| Talk With Your Files   [workspace]        [Run demo] [theme] |
+---+----------------------------------------------------------+
| E |   translator    translator     translator   | Huddle log |
| S |         . - - - - - .                       |            |
| C |        (   huddle    )   translator         |            |
|   |         ` - - - - - '                       |            |
|   |           orchestrator                      |            |
|   +-------------------[ v ^ ]--------------------------------+
|   |  chat with the chat agent                                |
|   |  [ user input                                    ] Send  |
+---+----------------------------------------------------------+
```

### Stage (above the divider)

- The huddle is a dotted circle in the middle. The orchestrator stands just below it and steps into it while a huddle runs.
- Idle translators stand outside the circle, around it. Translators in the huddle stand inside it.
- Up to 10 translators are all shown. Above 10, the ones in the huddle are always shown and the idle ones beyond the limit collapse into a "+N more" group that opens the explorer.
- The agent that is speaking shows a short speech bubble. A translator that is reading its file shows a reading mark.
- The **huddle log** on the right keeps the full discussion, with citations, so nothing is lost. It can be hidden.
- Clicking a translator opens its card: its files, a summary, and a small chat with that agent alone.

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
- Answers carry numbered citation markers. Clicking one opens a panel on the right with the file name, the location and the passage with the quoted part highlighted. The translator that supplied it is highlighted on the stage.
- Naming a file or translator in a question makes the orchestrator call it directly.

### E, S and C panels

Three buttons on the left edge. Each opens a drawer from the left, over the stage and chat.

- **E, explorer**: uploads happen here. Two table views of the same library: grouped by file (name, type, size, translator) and grouped by agent (translator, its files).
- **S, sessions**: a short table of sessions with the latest on top, and a button for a new session.
- **C, context map**: the mind map of files and entities and the links between them. It can expand to full width.

### Look

Clean and calm, with a light and a dark theme. The stage keeps the sketch's character: simple figures and a dotted circle.

## Frontend and backend boundary

The frontend must not depend on any backend. It talks to one TypeScript interface, `Backend`, in `frontend/src/backend/types.ts`:

- Reads: workspaces, files, agents, sessions, session messages and the context map.
- Writes: create a session, upload a file.
- `ask(workspace, session, question)` returns a stream of **agent events**. The UI draws whatever the stream says.
- `askTranslator(workspace, agent, question)` returns one reply from one translator.

Agent events:

| Event | Meaning | What the UI does |
|---|---|---|
| `status` | Free text progress | Updates the status line in the chat |
| `broadcast` | Orchestrator messages a set of translators | Pulse from the orchestrator, log entry |
| `join` | A translator enters the huddle, `volunteered` or `called` | The translator walks into the circle |
| `reading` | A translator is reading its files | Reading mark on the translator |
| `say` | An agent speaks in the huddle, with optional citations | Speech bubble, log entry |
| `leave` | Translators leave the huddle | They walk back out |
| `context` | New nodes and links for the context map | The map grows |
| `answer` | The chat agent's final answer with citations | Replaces the pending message |

A real backend only has to implement `Backend` and emit these events, over whatever transport it chooses. The mock in `frontend/src/backend/mock.ts` is the one implementation today, and `frontend/src/backend/index.ts` is the only place that selects it.

### Mock behaviour

- An uploaded file is only listed by name and size. Its content is never read and never leaves the browser. It gets a translator on the stage.
- A typed question runs a generic simulated huddle and returns an answer marked as a placeholder.
- Nothing is saved. Reloading the page resets everything.

## Demo scenario, kept as a test case

`frontend/src/demo/scenario.ts` holds a workspace for a made-up company, Harbor Coffee Roasters, and a scripted list of agent events.

- **Files**: a supplier contract, Q3 sales, October board notes, a pricing policy, an HR handbook and an office lease.
- **Question**: "Our coffee supplier is raising prices in January. Can we keep our current prices and still hit our margin target?"
- **What happens**: the orchestrator asks all six translators. The contract, sales and board notes translators volunteer. The orchestrator calls the pricing policy translator directly. The HR handbook and lease translators stay out. The answer cites four files, and the context map gains a new entity.

"Run demo" in the top bar switches to this workspace and plays the script. While it plays, controls allow pause, step, speed and restart.
`frontend/src/demo/scenario.test.ts` checks the script through the `Backend` interface, so the same scenario can later be run against a real backend.

## Open questions

- How a translator with several files is named and drawn.
- How the stage should behave with hundreds of files, beyond the "+N more" group.
- Whether a session can limit which files take part.
- What else translators will be able to do beyond citing, explaining and summarising.
- Sign-in and what "user scoped" means once there is more than one user.
- The shape of the API and MCP server.
