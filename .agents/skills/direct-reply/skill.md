---
id: direct-reply
name: Direct reply
description: Answer the user directly from the passages of your files.
enabled: true
---

Answer the user, who is asking you directly, from the passages of the files.

Input:
- `question`: what the user asked.
- `passages`: text chosen by search, each with a `passageId`, `fileId`, `fileName`, `location` and `text`.
- `notes`: earlier notes on these files, with their weights.
- `searchesLeft`: how many more searches you may ask for.

Output:
- `statements`: your answer, as statements with `text` and `quotes` (at least one each). They are joined into your reply.
- `notes`: notes worth keeping, each with `fileId`, `kind`, `text` and `quotes`. A `summary` or `finding` needs at least one quote from its own file.
- `searches`: further searches (`fileId`, `query`) when the passages are not enough. Must be empty when `searchesLeft` is 0.

Rules: every id you give must be in your input. If the passages do not answer the question, say so in one statement quoting the closest passage.
