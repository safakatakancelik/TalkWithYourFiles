# CI

`ci.yml` runs on every push and pull request.

| Job | What it checks |
|---|---|
| `backend` | On Python 3.13 and 3.14: lint, format, strict types, all tests with at least 90% coverage, and 100% on the modules that guard correctness |
| `frontend` | The UI builds and its tests pass |
| `contract` | Regenerating `contract/schema.json` and `frontend/src/backend/contract.gen.ts` changes nothing |
| `demo` | The frontend's demo test passes against the real backend running the scripted demo |

No job needs a model, an API key or a model download.
