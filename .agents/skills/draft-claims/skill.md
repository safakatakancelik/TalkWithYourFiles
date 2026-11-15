---
id: draft-claims
name: Draft claims
description: Turn the huddle into checkable claims.
enabled: true
---

Turn the huddle into the claims the answer will rest on.

Input:
- `question`: what the user asked.
- `transcript`: what was said, with citations.
- `earlier`: claims from earlier rounds, each with `ref`, `text`, `verdict` and `reason`.

Output:
- `claims`: each with `ref` (a label unique in this output, such as "k1"), `text` (one sentence, one fact), `kind`, and then:
  - `citationIds` for a `quoted` claim: the citations that state it;
  - `derivedFrom` for a `derived` claim: the refs of the claims it is computed or inferred from, with `expression` and `statedResult` when it is arithmetic.

Rules:
1. A quoted claim has at least one citation id from the transcript, into the current version of its file.
2. A derived claim has at least one `derivedFrom`, every ref exists in this output, and there is no cycle. Its citations are those of its inputs.
3. An `expression` uses numbers, `+ - * / **`, parentheses and `round`, `abs`, `min`, `max` only, and `statedResult` must equal its value. A wrong result fails the claim without a verifier.
4. A claim identical to one already verified keeps its verdict.

Keep verified claims from `earlier`. Reword or drop the ones that failed.

Examples:
- Quoted: `{"ref": "k1", "kind": "quoted", "text": "The price is 29.00 per unit.", "citationIds": ["c_..."]}`
- Derived: `{"ref": "k3", "kind": "derived", "text": "The margin is 52.9%.", "derivedFrom": ["k1", "k2"], "expression": "1 - 13.66 / 29.00", "statedResult": 0.529}`

If nothing in the transcript answers the question, return no claims.
