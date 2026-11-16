# Skills

One folder per skill, each with `skill.md`: frontmatter, then the instructions for one kind of turn. A turn's instructions are its skill, with `cite-passages` first when the turn quotes files. Each skill names every field of its turn's input and output; a test checks that.

| Folder | Turn |
|---|---|
| `cite-passages/` | How to quote: exactly, with the passage id, 8 to 600 characters. Used by every turn that quotes |
| `volunteer/` | A translator decides whether to join the huddle |
| `work-on-files/` | A translator reports what its passages say, with quotes, notes, entities and further searches |
| `direct-reply/` | A translator answers the user directly (`ask_translator`) |
| `first-read/` | A translator summarises the opening of a newly added file |
| `describe-image/` | A translator describes an image in words |
| `plan-huddle/` | The orchestrator chooses whom to ask |
| `assign-files/` | The orchestrator gives files and a focus to each translator in the huddle |
| `review-huddle/` | The orchestrator continues the discussion or settles |
| `draft-claims/` | The orchestrator turns the discussion into checkable claims |
| `verify-claims/` | The verifier judges each claim against its passages |
| `write-answer/` | The chat agent writes the answer from verified claims |
