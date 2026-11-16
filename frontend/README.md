# Frontend

The React UI. It talks to a backend only through the `Backend` interface in `src/backend/types.ts`: an in-memory mock by default, or the real backend when `VITE_BACKEND_URL` is set.

```bash
npm install
npm run dev                                            # the mock, with "Run demo"
VITE_BACKEND_URL=http://127.0.0.1:8321 npm run dev     # the real backend (the demo still uses the mock)
npm run build && npm test                              # checks
npm run gen:contract                                   # regenerate the contract types
```

| Item | What it is |
|---|---|
| `src/` | The app |
| `index.html`, `vite.config.ts`, `tsconfig.json` | Vite and TypeScript setup |
| `package.json` | Scripts and dependencies (reasons in [docs/dependencies.md](../docs/dependencies.md)) |
