# The contract

`schema.json` is the JSON Schema of every type that crosses between the backend and its clients, plus the list of operations (name, method, path, input, output). It is generated from the backend's Pydantic models; do not edit it by hand.

```bash
cd backend && uv run twyf export-contract     # writes schema.json
cd frontend && npm run gen:contract           # writes src/backend/contract.gen.ts from it
```

The frontend's `contract.check.ts` fails to compile when its hand-written types drift from these. Details: [03-contract.md](../docs/development/revision-2-backend/03-contract.md).
