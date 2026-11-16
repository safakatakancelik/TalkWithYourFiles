# Evaluation set

Questions with expectations, to judge answers from real models. Not part of CI. Run against a running server:

```bash
uv run twyf seed-demo          # most cases use the demo workspace
uv run twyf eval --runtime queue
```

| Item | What it is |
|---|---|
| `cases.json` | The cases: question, facts that must and must not appear, files that must be cited, expected outcome |
| `workspaces/` | Files for cases that do not use the demo workspace |
| `reports/` | One JSON report per run (not kept in git) |
