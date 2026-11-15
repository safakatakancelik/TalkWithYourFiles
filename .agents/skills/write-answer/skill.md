---
id: write-answer
name: Write answer
description: Write the answer from verified claims.
enabled: true
---

Write the answer to the user from the claims you are given.

Input:
- `question` and `history`: what the user asked, and the conversation so far.
- `mode`: `full` (all claims passed), `partial` (only the claims given passed), `nothing_found` (the files do not answer the question) or `no_files` (there are no files yet).
- `claims`: the verified claims, each with `claimId` and `text`.
- `unverified`: claims that could not be verified, with reasons. The user sees these separately.

Output:
- `segments`: the answer in order, each with `text`, `claimIds` (the claims the segment states) and `newParagraph` (true to start a new paragraph).

Rules:
1. Every `claimId` is one of the claims given.
2. A segment with no `claimIds` is connective text and contains no digits.
3. Every number in a segment with `claimIds` appears in the text of one of those claims.
4. At least one segment has `claimIds`, unless the mode is `no_files` or `nothing_found`.

Do not write markers like [1]; they are added for you. Never state anything from `unverified` as fact.
