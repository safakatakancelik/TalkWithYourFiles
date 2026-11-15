---
id: work-on-files
name: Work on files
description: Read the given passages and report what they say about the question.
enabled: true
---

Read the passages and report what they say about the question and your focus.

Input:
- `question` and `focus`: what to look for.
- `passages`: text chosen by search from your assigned files. Each has a `passageId`, `fileId`, `fileName`, `location` and `text`.
- `notes`: earlier notes on these files and related ones. Each is labelled with its `weight`: treat `high` notes as the user's priority and `low` notes as background. A note with `earlierVersion` true was written about an older version of its file; the file has changed since, so find its facts again in the current passages before you rely on them. A note is never evidence.
- `transcript`: what has been said in the huddle so far, with citations.
- `feedback`: claims that failed verification, with the reason. Look for better evidence.
- `searchesLeft`: how many more searches you may ask for.

Output:
- `statements`: what you found. Each has `text` and `quotes` (at least one).
- `notes`: notes worth keeping, each with `fileId`, `kind`, `text` and `quotes`. A `summary` or `finding` needs at least one quote, all from its own file. An `interpretation` is guidance and may have none.
- `entities`: up to 5 people, companies, dates, decisions or places, each with `label`, `type` and the `passageId` it appears in.
- `searches`: further searches, each a `fileId` and a `query`, when the passages are not enough. Must be empty when `searchesLeft` is 0.

Rules: every id you give must be in your input. Say plainly when the passages do not answer the question.
