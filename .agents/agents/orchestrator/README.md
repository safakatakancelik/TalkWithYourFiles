# Agent definition: `orchestrator`

One per workspace. It plans who to ask, gives files and a focus to the translators in the huddle, reviews the discussion and drafts the claims. Skills: plan-huddle, assign-files, review-huddle, draft-claims.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
