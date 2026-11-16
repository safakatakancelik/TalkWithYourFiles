# Recording

Every action that changes state is recorded in `app_events`, in the same transaction, with who did it and through which door.

| File | What it is |
|---|---|
| `recorder.py` | `record(...)`: one event; refuses secret-looking payload keys |
| `broker.py` | Fans a question's events out to its open streams after each commit |
| `context.py` | `RequestContext`: actor, source, user, request id, cause |
