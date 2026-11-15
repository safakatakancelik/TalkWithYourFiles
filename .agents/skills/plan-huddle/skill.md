---
id: plan-huddle
name: Plan huddle
description: Choose which translators to ask about a question.
enabled: true
---

Decide whom to ask about the question.

Input:
- `question` and `history`: what the user asked, and the last messages of the conversation.
- `files`: each usable file with its `fileId`, `name`, `type` and weighted `notes`.
- `agents`: each translator with its `agentId`, `name`, `specialty`, `noteCount` and `filesWorked`.
- `namedFileIds` and `namedAgentIds`: files and translators the user named. They must be used.

Output:
- `broadcastText`: your message to the translators you ask.
- `broadcastTo`: the `agentId` of each translator to ask. All, some or none.
- `directCalls`: translators you bring in yourself, each with `agentId`, `fileIds` and a `reason`.

Rules: name translators only, from `agents`. Every agent in `namedAgentIds` is in `broadcastTo` or `directCalls`. Every file id is from `files`.
