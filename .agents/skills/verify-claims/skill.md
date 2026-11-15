---
id: verify-claims
name: Verify claims
description: Judge each claim against its cited passages.
enabled: true
---

Judge each claim against its cited passages.

Input:
- `claims`: each with `claimId`, `text`, `kind`, its `citations` (each with `citationId`, `passage` and `quote`), and for a derived claim its `inputs` and any `expression` with its `computedResult`.

Output:
- `verdicts`: exactly one per claim, with `claimId`, `verdict`, `reason` (one or two sentences, always given) and `citations`: one entry per citation of that claim, with `citationId` and `supports` (`full`, `partial` or `none`).

How to judge:
- Judge only whether the passages state what the claim states. Do not use outside knowledge. Do not judge whether the claim is useful.
- `supported`: the cited passages, read together, state everything the claim states. For a derived claim: its inputs are the right inputs, the expression matches the wording, and the conclusion follows.
- `partly_supported`: some part of the claim is not in the passages.
- `unsupported`: the passages do not state it, or contradict it.
- A number, date, name or condition in the claim that is not in the passages makes it at most `partly_supported`.
