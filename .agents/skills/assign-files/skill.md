---
id: assign-files
name: Assign files
description: Give each translator in the huddle files and a focus.
enabled: true
---

Give each translator in the huddle files to work on and a focus.

Input:
- `question`: what the user asked.
- `volunteers`: translators who offered to help, with `agentId`, `reason` and the `fileIds` they would take.
- `directCalls`: translators you called in.
- `files` and `agents`: as in planning.
- `namedFileIds`: files the user named.

Output:
- `assignments`: one per translator you use, with `agentId`, `fileIds` and `focus` (what to look for). You may give one file to several translators and several files to one translator. A volunteer you give nothing to is left out.

Rules: each assigned agent is a volunteer, a direct call, or a translator you now call in. Every file in `namedFileIds` is assigned to someone. Every id is from your input.
