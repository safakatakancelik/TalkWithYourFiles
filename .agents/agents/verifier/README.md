# Agent definition: `verifier`

One per workspace. It sees only the claims and their cited passages, never the question or the discussion, and judges whether the passages state each claim. Skill: verify-claims.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
