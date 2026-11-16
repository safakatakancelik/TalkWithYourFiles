# Local type stubs

Type descriptions for two dependencies that ship none, so that pyright's strict mode can check the code that uses them.

| Folder | Package |
|---|---|
| `sqlite_vec/` | `load(conn)`, used to load the vector extension |
| `simpleeval/` | `SimpleEval` and `InvalidExpression`, used by the arithmetic check |
