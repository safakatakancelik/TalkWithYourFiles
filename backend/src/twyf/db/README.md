# Database

SQLite, through the standard library. No ORM.

| File | What it is |
|---|---|
| `connection.py` | `connect` (WAL, foreign keys, sqlite-vec) and `transaction` |
| `migrate.py` | Applies `migrations/` in order, backing up the database first |
| `migrations/` | The SQL migrations |
| `repos/` | One module of SQL per group of tables |
