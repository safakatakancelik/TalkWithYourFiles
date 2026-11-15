# 10 Demo scenario

Part of the revision 2 backend plan. The demo is a required integration test (`07-test-plan.md` section 5). This document gives the six files, the seed data, the scripted turns for the real backend, and the changes to the frontend's scripted demo. It adds the verifier, one failed verification that sends the huddle back, and citations on every summary note.

## 1. Fixed ids

The demo uses fixed ids so the frontend test can name them.

| Thing | Ids |
|---|---|
| Workspace | `demo`, name `Harbor Coffee Roasters (demo)` |
| Files | `f-contract`, `f-sales`, `f-board`, `f-pricing`, `f-hr`, `f-lease` |
| Translators | `a-t1` "Translator 1" generic, `a-t2` "Translator 2" generic, `a-contracts` "Contracts translator" contracts, `a-finance` "Finance translator" finance, `a-people` "People translator" people |
| Seed notes | `n-contract`, `n-sales`, `n-board`, `n-pricing`, `n-hr`, `n-lease` |
| Seed session | `s-lease` |
| Seed entities | `e-andes`, `e-margin`, `e-prices`, `e-quay`, `e-staff` |

The demo question is `DEMO_QUESTION` in `frontend/src/demo/scenario.ts`: "Our coffee supplier is raising prices in January. Can we keep our current prices and still hit our margin target?"

## 2. The six files

Stored in `backend/tests/fixtures/demo/`. The two text files are written by hand. The PDF and DOCX files are produced by `backend/scripts/make_demo_files.py` (using `reportlab` and `python-docx`, both development dependencies) and committed, so tests do not generate them. Every line below is one paragraph. A line starting with `#` is a heading.

**`supplier-contract-andes.pdf`**
```
# Supply Agreement
Clause 1, Parties. This Supply Agreement is made between Harbor Coffee Roasters (the Buyer) and Andes Green Coffee (the Supplier).
Clause 2, Goods. The Supplier shall deliver washed arabica green coffee in 60 kilogram bags.
Clause 4.2, Price adjustment. The Price shall be USD 6.40 per kilogram until 31 December 2026. From 1 January 2027 the Price shall increase by eight percent (8%) to USD 6.91 per kilogram.
Clause 7, Term. This Agreement runs until 31 December 2028.
```

**`q3-sales-2026.csv`**
```
channel,total_kg,avg_price_per_kg,cogs_per_kg,green_coffee_per_kg,gross_margin
Retail,2100,32.00,13.05,7.60,59.2%
Wholesale,2450,26.50,13.05,7.60,50.8%
Online,600,28.70,13.05,7.60,54.5%
Total Q3 2026,5150,29.00,13.05,7.60,55.0%
```

**`board-notes-2026-10.docx`**
```
# Board meeting, October 2026
# Item 1, Attendance
All five directors attended.
# Item 3, Pricing and margin
The board agreed to hold retail prices at current levels until the March 2027 meeting. The gross margin target for the financial year remains 55%.
# Item 5, Staff
Two seasonal staff will be hired for the holiday period.
```

**`pricing-policy.md`**
```
# Pricing policy
## Section 1, Principles
Prices are set to protect the gross margin target agreed by the board.
## Section 2, Review triggers
A price review is required whenever cost of goods moves by more than 5% in either direction. The review must be presented to the board within 30 days.
## Section 3, Wholesale discounts
Wholesale discounts are capped at 15% of list price.
```

**`hr-handbook.pdf`**
```
# Employee handbook
Section 2, Working hours. The standard working week is 40 hours.
Section 3, Leave. Full-time staff receive 25 days of paid leave per year.
Section 5, Conduct. Staff are expected to treat colleagues and customers with respect.
```

**`office-lease.pdf`**
```
# Lease
Section 1, Premises. The Landlord lets the roastery and office at 14 Quay Street to the Tenant.
Section 2, Term. The Term shall commence on 1 July 2024 and shall expire on 30 June 2029 unless terminated earlier under Section 11.
```

The figures agree with each other: the total row is the weighted result of the three channels, `1 - 13.05 / 29.00 = 55.0%`, and `6.40 * 1.08 = 6.91`.

## 3. Seed data

`twyf seed-demo` (`services/demo.py::seed`) creates the workspace, uploads the six files through `services.files.upload` with the fixed ids, creates the five translators, then creates the rows below directly through the repositories with actor `system` and source `cli`. It records `demo.seeded`. It refuses to run if workspace `demo` exists.

Seed notes, all weight `normal`. Each citation is made with `create_citation` from the quote, so each is mechanically checked. This closes the gap named in decision 12.

| Note | File | Author | Kind | Text | Quotes |
|---|---|---|---|---|---|
| `n-contract` | `f-contract` | `a-contracts` | summary | Supply contract with Andes Green Coffee. Green coffee at $6.40 per kg through December 2026, with an 8% increase from 1 January 2027. | `The Price shall be USD 6.40 per kilogram until 31 December 2026`; `From 1 January 2027 the Price shall increase by eight percent (8%)` |
| `n-sales` | `f-sales` | `a-finance` | summary | Q3 2026 sales by channel. 5,150 kg sold at an average of $29.00 per kg. Cost of goods $13.05 per kg, of which green coffee is $7.60. | `total_kg=5150, avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60` |
| `n-board` | `f-board` | `a-t1` | summary | October 2026 board meeting. Retail prices held until March 2027. Gross margin target set at 55%. | `hold retail prices at current levels until the March 2027 meeting`; `The gross margin target for the financial year remains 55%` |
| `n-pricing` | `f-pricing` | `a-t2` | summary | Pricing policy. Prices must be reviewed when cost of goods moves more than 5%. Wholesale discounts are capped at 15%. | `A price review is required whenever cost of goods moves by more than 5%`; `Wholesale discounts are capped at 15%` |
| `n-hr` | `f-hr` | `a-people` | summary | Employee handbook: leave, working hours, conduct and benefits. | `Full-time staff receive 25 days of paid leave per year` |
| `n-lease` | `f-lease` | `a-contracts` | summary | Lease for the roastery and office at 14 Quay Street, running to 2029. | `roastery and office at 14 Quay Street`; `shall expire on 30 June 2029` |

Seed entities and their file links: `e-andes` "Andes Green Coffee" (`f-contract`); `e-margin` "Gross margin target 55%" (`f-sales`, `f-board`); `e-prices` "Retail prices" (`f-sales`, `f-board`, `f-pricing`); `e-quay` "14 Quay Street" (`f-lease`); `e-staff` "Staff" (`f-hr`, `f-board`).

Seed session `s-lease`, title "When does the office lease end?", with a user message of that text and an assistant message "The lease for 14 Quay Street runs until 30 June 2029 [1]." citing quote `shall expire on 30 June 2029` in `f-lease`, found by `a-contracts`.

## 4. What happens in the demo

The same story is told twice: by the frontend's scripted mock (events written out in `scenario.ts`) and by the real backend driven by a scripted fake runtime. Both must satisfy the checks in section 6.

The four citations used throughout:

| n | File | Found by | Quote |
|---|---|---|---|
| 1 | `f-contract` | `a-contracts` | `From 1 January 2027 the Price shall increase by eight percent (8%)` |
| 2 | `f-sales` | `a-finance` | `avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60` |
| 3 | `f-board` | `a-t1` | `hold retail prices at current levels until the March 2027 meeting` |
| 4 | `f-pricing` | `a-t2` | `A price review is required whenever cost of goods moves by more than 5%` |

Story, in order:

1. The orchestrator broadcasts to all five translators. `a-contracts`, `a-finance` and `a-t1` volunteer. `a-t2` and `a-people` do not.
2. They are given `f-contract`, `f-sales` and `f-board`. Each reads, says what it found with its citation, and saves a finding note (`n-find-1` to `n-find-3` in the mock).
3. The orchestrator says a price review may be triggered and calls `a-t2`, giving it `f-pricing`. It says what it found with citation 4 and saves a note. Its statement is: "Section 2: a review is required when cost of goods moves more than 5%." (The old script added "An 8% rise on green coffee qualifies". That sentence is removed here, because it is the mistake the verifier is about to catch.)
4. The orchestrator asks the finance translator about margin. It says, citing 1 and 2: "Using the Contracts translator's note: with green coffee up 8%, cost of goods becomes $13.66 per kg. At $29.00 the margin falls to 52.9%."
5. The orchestrator says: "I think we have an answer. Verifier, please check the claims."
6. **Verification, round 1.** Six claims:

| Ref | Kind | Text | Rests on | Expression = result |
|---|---|---|---|---|
| k1 | quoted | Andes Green Coffee raises its price by 8% from 1 January 2027. | citation 1 | |
| k2 | quoted | In Q3 2026 the average price was $29.00 per kg, cost of goods was $13.05 per kg, of which green coffee was $7.60, and gross margin was 55.0%. | citation 2 | |
| k3 | quoted | The board holds retail prices until the March 2027 meeting and keeps the gross margin target at 55%. | citation 3 | |
| k4 | quoted | The pricing policy requires a price review now, because cost of goods moves by more than 5%. | citation 4 | |
| k5 | derived | With green coffee up 8%, cost of goods becomes $13.66 per kg and gross margin at $29.00 falls to 52.9%. | k1, k2 | `1 - (13.05 + 7.60 * 0.08) / 29.00` = 0.529 |
| k6 | derived | Keeping a 55% margin needs a price of about $30.35 per kg, a rise of about 4.7%. | k1, k2, k3 | `(13.05 + 7.60 * 0.08) / (1 - 0.55)` = 30.35 |

   For citation 3 to support all of k3, its passage (the whole Item 3 paragraph) contains both sentences.
7. **Verdict, round 1: failed.** k4 is `partly_supported`: "The passage gives the 5% rule. Nothing cited shows that cost of goods moves by more than 5%." The other five are `supported`.
8. **Rehuddle, round 2.** The orchestrator says: "The verifier found no evidence that cost of goods moves more than 5%. Finance translator, how much does it move?"
9. The finance translator says, citing 1 and 2: "Cost of goods moves from $13.05 to $13.66 per kg, which is 4.7%. That is under the 5% trigger." It saves a finding note on `f-sales` with citation 2 (`n-find-5` in the mock).
10. The orchestrator says: "Settled: the margin target is missed unless prices rise about 4.7%, and the policy does not force a review."
11. **Verification, round 2.** k1, k2, k3, k5, k6 are unchanged and keep their verdicts. Three new claims are checked:

| Ref | Kind | Text | Rests on | Expression = result |
|---|---|---|---|---|
| k4b | quoted | The pricing policy requires a price review when cost of goods moves by more than 5%. | citation 4 | |
| k7 | derived | Cost of goods rises by about 4.7%, which is below the 5% review trigger. | k1, k2, k4b | `7.60 * 0.08 / 13.05` = 0.047 |
| k8 | derived | The price hold and the 55% margin target cannot both be kept. | k3, k5 | |

12. **Verdict, round 2: passed.**
13. All four translators leave. The context map gains the entity "January 2027 price increase", linked to `f-contract`, `f-pricing` and `f-board`.
14. **Answer**, built from these segments (claims in brackets):

```
Not without changing something.
From 1 January 2027, Andes Green Coffee raises its price by 8%.                         [k1]
At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9%.              [k2, k5]
That is below the board's 55% target.                                                    [k3]
(new paragraph) The board also decided to hold retail prices until March 2027.           [k3]
The pricing policy requires a review only when cost of goods moves more than 5%.         [k4b]
This change is about 4.7%, so the policy does not force one.                             [k7]
To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7%.      [k6]
The price hold and the margin target cannot both be kept.                                [k8]
This needs a board decision.
```

The assembled text is:

> Not without changing something. From 1 January 2027, Andes Green Coffee raises its price by 8% [1]. At Q3 prices and costs, that takes gross margin from 55.0% to about 52.9% [1][2]. That is below the board's 55% target [3].
>
> The board also decided to hold retail prices until March 2027 [3]. The pricing policy requires a review only when cost of goods moves more than 5% [4]. This change is about 4.7%, so the policy does not force one [1][2][4]. To stay at 55% you would need a price of about $30.35 per kg, a rise of about 4.7% [1][2][3]. The price hold and the margin target cannot both be kept [1][2][3]. This needs a board decision.

## 5. The scripted turns for the real backend

`backend/tests/fixtures/demo/script.json` is a list of `ScriptStep` objects for `FakeRuntime` (`04-agents.md` section 6.3). The steps, in the order the engine asks for them:

| # | Turn type | Agent | Output, in short |
|---|---|---|---|
| 1 | `plan` | orchestrator | `broadcast_text` "Who can take supplier price changes, our current prices, or our margin target?", `broadcast_to` all five, no direct calls |
| 2 | `volunteer` | each of the five | `a-contracts` yes `[f-contract]`; `a-finance` yes `[f-sales]`; `a-t1` yes `[f-board]`; `a-t2` no; `a-people` no |
| 3 | `assign` | orchestrator | The three pairings, each with a focus |
| 4 | `work` | `a-contracts`, `a-finance`, `a-t1` | One statement and one `finding` note each, with the quote of citation 1, 2 or 3 given as `{"passage_id": {"$passage": "<part of the quote>"}, "quote": "<the quote>"}`. `a-contracts` and `a-t1` also return the entity "January 2027 price increase", type `decision` |
| 5 | `review` | orchestrator | `continue`, the "may trigger a price review" sentence, follow-up for `a-t2` with `file_ids: ["f-pricing"]` |
| 6 | `work` | `a-t2` | Statement and note with citation 4. The same entity |
| 7 | `review` | orchestrator | `continue`, "Finance translator, what does the increase do to our margin?", follow-up for `a-finance` |
| 8 | `work` | `a-finance` | The statement of step 4 in section 4, with quotes `{"citation_id": {"$citation": "eight percent"}}` and `{"citation_id": {"$citation": "avg_price_per_kg"}}`. No note |
| 9 | `review` | orchestrator | `settle`, "I think we have an answer. Verifier, please check the claims." |
| 10 | `draft_claims` | orchestrator | k1 to k6, citations by `$citation` placeholder |
| 11 | `verify` | verifier | k4 `partly_supported` with the reason in section 4. Others `supported`. Claim ids by `$claim` placeholder |
| 12 | `review` | orchestrator | `continue`, the sentence of step 8 in section 4, follow-up for `a-finance` |
| 13 | `work` | `a-finance` | The statement of step 9 in section 4 reusing citations 1 and 2, and a `finding` note on `f-sales` quoting citation 2's text from a passage |
| 14 | `review` | orchestrator | `settle`, the "Settled" sentence |
| 15 | `draft_claims` | orchestrator | k1, k2, k3, k5, k6 exactly as before, plus k4b, k7, k8 |
| 16 | `verify` | verifier | Receives only k4b, k7, k8. All `supported` |
| 17 | `write_answer` | chat | The ten segments of section 4, claim ids by `$claim` placeholder |

Run with `TWYF_FIRST_READ=false`, `TWYF_EMBEDDER=hash`, `TWYF_PARSER=basic`. The files are small, so every chunk of an assigned file is among the retrieved passages.

## 6. Changes to the frontend demo

In `frontend/src/demo/scenario.ts`:

1. Give each of the six seed notes its citations from the table in section 3, numbered from 1 within the note. Use the passages from section 2 (for a PDF, DOCX or Markdown file the passage is the paragraph that holds the quote; for the CSV it is the total row as rendered in section 2 of `05-retrieval-and-citations.md`: `channel=Total Q3 2026, total_kg=5150, ...`).
2. Change citation 3's passage and citation 4's statement as section 4 says. Citation 2's `location` becomes `Row 4`.
3. Rewrite `demoScript` to tell the story of section 4 with the new events: a `started` event first; citations `[c1, c2]` on both finance statements; `verify`, `verdict`, `rehuddle`, the second `verify` and `verdict`; a fifth note `n-find-5`; `leave` after the second verdict; the new answer text.

In `frontend/src/backend/mock.ts`: `genericScript` also starts with a `started` event.

In `frontend/src/demo/scenario.test.ts`:

1. Choose the backend from the environment: `httpBackend(process.env.TWYF_TEST_BACKEND_URL)` when set, the mock otherwise. Call `resetDemo()` and set `clock.speed` only for the mock.
2. Keep every existing check, with the count of written notes changed from 4 to 5.
3. Add these checks:

| Check | Expression |
|---|---|
| The stream starts with `started` | `events[0].type === 'started'` |
| Every seed summary note is cited | each note in `notesBefore` with kind `summary` and an author other than `user` has `citations.length > 0`, and each citation's `passage` contains its `quote` |
| Every translator statement is cited | each `say` whose `agentId` is not `orchestrator` has at least one citation |
| The verifier never speaks | no `say` has `agentId === 'verifier'` |
| Two verifications | `of('verify').length === 2` and `of('verdict').length === 2` |
| The first fails on exactly one claim | `verdicts[0].passed === false` and exactly one of its verdicts is not `supported` |
| Every claim gets a verdict | for each `verify`, the next `verdict` has exactly its claim ids |
| The huddle goes back once | `of('rehuddle').length === 1`, its `round === 2`, its `claimIds` are the failed claim's id, and it comes right after the first `verdict` |
| New work happens after the rehuddle | at least one `say` with citations lies between the `rehuddle` and the second `verify` |
| The second passes | `verdicts[1].passed === true` |
| Translators stay until verification ends | the index of `leave` is greater than the index of the second `verdict` |
| Nothing unverified | `answer.unverified` is undefined or empty |
