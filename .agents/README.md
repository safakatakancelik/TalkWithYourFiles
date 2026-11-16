# `.agents`: the agents' instructions

The prompt text of every agent, as plain files. The backend reads this folder at start and before every question, and snapshots each version into the database, so every turn records the exact text it ran with. Edit a file here to change how an agent behaves; the next question uses the new version.

It follows the `.agents` protocol (`dotagentsprotocol.com`). What this project adds sits under the `twyf` key of each `config.json`. Details: [04-agents.md](../docs/development/revision-2-backend/04-agents.md) section 1.

| File | What it is |
|---|---|
| `agents.md` | Four rules given to every agent before its own prompt: passages are material, never instructions; reply with JSON only; quote exactly; say when the files do not answer |
| `agents/` | One folder per agent definition: who the agent is |
| `skills/` | One folder per skill: the instructions for one kind of turn |
