# Repositories

One module of SQL per group of tables. Every function that reads user data takes a workspace id. `versioned.py` handles the tables whose rows keep their history (`valid_from`, `valid_to`).

| File | What it is |
|---|---|
| `workspaces.py` | Workspaces |
| `agents.py` | Agents and their versions |
| `files.py` | Files, versions, availability and status |
| `extractions.py` | Extracted text, blocks and chunks |
| `embeddings.py` | Vectors and embedding models |
| `citations.py` | Citations and their wire form |
| `notes.py` | Notes, their text versions and weights |
| `sessions.py` | Sessions and messages |
| `questions.py` | Questions |
| `huddle.py` | Rounds, members, assignments, statements |
| `turns.py` | Agent turns |
| `claims.py` | Claims |
| `verifications.py` | Verifications and verdicts |
| `entities.py` | Entities and mentions |
| `definitions.py` | Agent definition and skill versions |
| `events.py` | Reading the event log |
| `versioned.py` | Type 2 history for any versioned table |
