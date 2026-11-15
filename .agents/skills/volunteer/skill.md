---
id: volunteer
name: Volunteer
description: Decide whether to take part in a question.
enabled: true
---

Decide whether to join the huddle for this question.

Input:
- `question`: what the user asked.
- `broadcastText`: the orchestrator's message to the translators.
- `files`: each file with its `fileId`, `name`, `type` and the `notes` written about it so far, with their weights.

Output:
- `volunteer`: true when you can help, false otherwise.
- `reason`: one or two sentences on why, based on your speciality and on what the notes say the files contain.
- `fileIds`: the files you would take. Empty when `volunteer` is false.

Rules: every id in `fileIds` must be a `fileId` from `files`. Say no when nothing in your speciality or the notes suggests you can add something.
