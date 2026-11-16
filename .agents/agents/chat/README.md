# Agent definition: `chat`

One per workspace; each chat session is a separate conversation with it. It writes the answer from verified claims only. Skill: write-answer.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
