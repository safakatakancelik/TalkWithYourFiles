# Speed: where a question's time goes, and how to cut it

Notes for future work, written 2026-11-17 from the timings of real questions in `~/.twyf/twyf.db` (table `agent_turns`, column `duration_ms`). Nothing here is built yet.

## What was measured

A question takes 64 to 208 seconds. The latest one took 104 s: 13 agent turns in 11 steps, each step waiting for the one before.

| Step | Turns | Started at | Took |
|---|---|---|---|
| Orchestrator plans | 1 | 0 s | 9 s |
| Translators volunteer | 2, in parallel | 9 s | 9 s |
| Orchestrator assigns files | 1 | 18 s | 7 s |
| Translators work on their files | 2, in parallel | 26 s | 13 s |
| Orchestrator reviews | 1 | 38 s | 7 s |
| Orchestrator drafts claims | 1 | 46 s | 8 s |
| Verifier checks the claims | 1 | 53 s | 10 s |
| Round 2: review, draft claims, verify | 3 | 63 s | 29 s |
| Orchestrator writes the answer | 1 | 93 s | 11 s |

Averages over all turns: `work` 16.6 s, `draft_claims` 10.7 s, `verify` 9.9 s, `write_answer` 7.7 s, `assign` 7.4 s, `plan` 7.3 s, `review` 6.1 s, `volunteer` 6.0 s.

A trivial `claude -p` call with Haiku (`Reply with {"ok":true}`) took 5.8 s from start to exit, of which 1.2 s was the API call. About 4.6 s per turn is fixed cost: starting Claude Code, and Claude Code sending its own system prompt (about 5,000 tokens, written to the cache again on every call).

## Why it is slow, most important first

1. **A new Claude Code process for every turn: about 50 s of the 104 s.** The `command` runtime (`backend/src/twyf/runtime/command.py`) runs `claude -p` once per turn, with an API key (`--bare`) and with a subscription alike. No agent is kept alive across turns or across a session. The `queue` runtime (`./start.sh --queue`) is the one exception: a harness session connected through MCP claims the turns one by one, so there is no process per turn, but the turns of one question then run one after another, parallel steps included.
2. **Steps run one after another.** 11 steps, so even a fast model pays 11 round trips. Only volunteering and file work run in parallel today.
3. **A second verification round almost every time: about 29 s.** 4 of the last 4 answered questions needed one. Each time, one claim of many was `partly_supported`, and the whole huddle went back through review, drafting and verification.
4. **Long outputs.** A `work` turn writes 1,000 to 3,000 tokens; a `draft_claims` turn about 1,600. Output tokens are the slow part of a model call.

## Suggestions

### Now, with settings only

- **`TWYF_MAX_VERIFY_ROUNDS`** (default 2 since 2026-11-17, was 3: at most one second round). With 1, claims that fail are shown under "Could not be verified" in the answer instead of starting another round; saves about 29 s on most questions. Try 1 or 2 and raise it if answers lose too much.
- **`--model haiku`** for every turn, to compare speed and answer quality against `sonnet` on the same questions.

### Fewer steps

- **Plan, volunteer and assign in one orchestrator turn.** The orchestrator already has each translator's specialty and the file list; it can pick the team and hand out files at once. Saves 2 steps, about 16 s. The volunteer step could stay as an option for workspaces with many translators.
- **Review and draft claims in one turn.** Both are orchestrator turns, back to back, on the same input. Saves 1 step per round, about 7 s.
- **Re-check only what failed.** When a few claims fail, send just those back to the translator who made them (or drop them into "Could not be verified") instead of a full round of review, drafting and verification.
- **Skip the verifier for exact quotes.** The code already checks every quote against the file text. A claim that is only a quoted passage needs no model to confirm it; send the verifier only claims that interpret or combine passages.
- **Answer from notes first.** When saved notes already cover the question (same files, unchanged versions, high weight), skip the file reading and draft from the notes.

### Cheaper turns

- **A runtime that calls the Anthropic API directly** (for API keys): no process start, the agent system prompts cached between turns (prompt caching), and the answer streamed. Removes most of the 4.6 s per turn, about 40 to 50 s per question.
- **Start the next `claude -p` before it is needed** (for subscriptions, which must go through Claude Code): keep one or two processes started and waiting on stdin, so their start-up overlaps the previous step. Needs a check that Claude Code does its start-up work before it reads stdin.
- **A model per turn type.** `.agents/agents/*/config.json` has a `modelConfig` that nothing reads today. Small decisions (`volunteer`, `assign`, `review`) could run on Haiku, reading and writing (`work`, `write_answer`) on Sonnet.
- **Shorter outputs.** Tighten the output schemas and skill instructions of `work` and `draft_claims` (fewer, shorter notes and statements per turn), and turn off or lower extended thinking for the small turns if the CLI allows it.

### Feeling faster

- **Stream the answer.** The `write_answer` turn arrives all at once; with the API runtime its text could stream into the chat as it is written.
- **A quick-answer mode.** One turn answers from the search results straight away, the way a chat agent does; the huddle and the verifier then run in the background and mark the answer verified or add a "Could not be verified" block when done.

## Also found

- **Input tokens are recorded wrong.** `agent_turns.input_tokens` holds 2 to 4 per turn because `parse_output` reads only `usage.input_tokens` and ignores `cache_creation_input_tokens` and `cache_read_input_tokens`, which hold almost all of the input. Cost and usage figures are too low until this is fixed.
- **Measure start-up separately.** Claude Code's JSON output has `duration_ms` and `duration_api_ms`; recording both per turn would show the start-up cost of every turn, and would show what each change above saves.
