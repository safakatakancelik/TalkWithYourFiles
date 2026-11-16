# Agent definitions

One folder per definition, each with `agent.md` (frontmatter, then the prompt) and `config.json` (`twyf.kind`, `twyf.extends`, `twyf.specialty`, `twyf.skills`).

| Folder | Agent |
|---|---|
| `translator/` | The base translator: reads passages of its files, quotes them, writes cited notes |
| `translator-contracts/` | A specialised translator for contracts. Extends `translator`; its prompt adds only what is special |
| `translator-finance/` | A specialised translator for figures and financial statements. Extends `translator` |
| `orchestrator/` | Plans the huddle, pairs translators with files, reviews the discussion, drafts the claims |
| `verifier/` | Checks every claim against its cited passages, and nothing else |
| `chat/` | Writes the answer to the user from verified claims only |

A new speciality is a new folder with `"extends": "translator"` and `"specialty": "<name>"`. A translator created with that speciality then uses it.
