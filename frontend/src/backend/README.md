# Backends

| File | What it is |
|---|---|
| `types.ts` | The `Backend` interface and every type the UI uses. The only thing the UI imports from a backend |
| `mock.ts` | An in-memory backend with a scripted demo and a clock to pause, step and speed it |
| `http.ts` | The real backend over HTTP, with the event-stream reader. Sends `X-TWYF-Source: ui` |
| `router.ts` | `withDemo`: sends the demo workspace to the mock and everything else to the real backend |
| `index.ts` | Chooses the backend from `VITE_BACKEND_URL` |
| `contract.gen.ts` | Generated from `contract/schema.json` (`npm run gen:contract`); do not edit |
| `contract.check.ts` | Fails to compile if `types.ts` drifts from the generated types |
| `*.test.ts` | Tests of the HTTP backend and the router |
