---
id: first-read
name: First read
description: Write a first summary of a newly added file from its opening passages.
enabled: true
---

Write a first summary of a file that has just been added, so the team knows what it is about.

Input:
- `fileName`: the file.
- `passages`: the opening of the file, in order, each with a `passageId` and `text`.
- `chunksShown` and `chunksTotal`: how many pieces of the file you see, and how many it has.

Output:
- `summary`: one note with `fileId`, `kind` set to `summary`, `text` and `quotes`. The summary says what kind of document this is and what it covers. It needs at least one quote.
- `entities`: up to 5 people, companies, dates, decisions or places, each with `label`, `type` and `passageId`.

Rules: when `chunksShown` is less than `chunksTotal`, begin the summary with "From the opening of the file:" and describe only what the passages show. Do not guess at the rest.
