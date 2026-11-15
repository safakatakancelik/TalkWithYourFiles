---
id: cite-passages
name: Cite passages
description: How to quote a passage so that the quote can be checked.
enabled: true
---

Every fact you state must carry a quote from a passage.

- Copy each quote exactly, character for character, from the `text` of one passage in your input. Do not fix spelling, change numbers, shorten words or join pieces from different places.
- Give the `passageId` of the passage you copied it from, as `{"passageId": "...", "quote": "..."}`.
- A quote is at least 8 and at most 600 characters. Quote the shortest part that states the fact.
- To rely on a citation already made in this question, give `{"citationId": "..."}` from the transcript instead of quoting again. Only citations into a file's current version can be reused; a note marked `earlierVersion` is about an older version and its facts must be found again in the current passages.
- A quote that is not found in its passage is rejected and you will be asked again.
