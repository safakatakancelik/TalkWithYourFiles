# Agent definition: `translator-contracts`

A translator for contracts and legal documents. It extends `translator`, so its prompt is the base prompt followed by `agent.md` here, and it has the same skills. Chosen for translators created with speciality `contracts`.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
