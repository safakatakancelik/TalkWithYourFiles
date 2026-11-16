# Agent definition: `translator`

The base translator. Every translator in a workspace uses this definition unless a specialised one matches its speciality. Skills: cite-passages, volunteer, work-on-files, direct-reply, first-read, describe-image.

| File | What it is |
|---|---|
| `agent.md` | Frontmatter (`id`, `name`, `description`, `role`, `enabled`, `connection-type`), then the prompt |
| `config.json` | No tools (`enabledBuiltinTools: []`), and this project's `twyf` block: kind, parent, speciality, skills |
