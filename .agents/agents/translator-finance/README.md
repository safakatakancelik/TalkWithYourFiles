# Agent definition: `translator-finance`

A translator for figures, budgets and financial statements. It extends `translator`. Chosen for translators created with speciality `finance`.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
