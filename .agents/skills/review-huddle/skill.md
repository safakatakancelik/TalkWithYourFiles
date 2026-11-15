---
id: review-huddle
name: Review huddle
description: Decide whether the huddle has enough to answer.
enabled: true
---

Read the discussion and decide whether the huddle has enough to answer.

Input:
- `question`: what the user asked.
- `transcript`: what each translator said, with citations.
- `members`: the agents in the huddle. `agents` and `files`: everyone and everything available.
- `failed`: claims that failed verification, with the verdict and reason, when a round has failed.
- `stepsLeft`: how many more review steps this round allows.

Output:
- `decision`: `continue` to ask for more, or `settle` when the transcript supports an answer or shows the files do not have one.
- `say`: one or two sentences to the huddle about what you decided.
- `followups`: when continuing, each with `agentId`, `focus` and `fileIds`. A translator outside the huddle needs `fileIds`.

Rules: `followups` is empty when `decision` is `settle` or `stepsLeft` is 0. When claims failed, ask for better evidence, or settle so they can be reworded or dropped.
