# The HTTP door

| File | What it is |
|---|---|
| `app.py` | `build_app`: one route per operation, generated; health; CORS; static files; the start-up (migrate, sync `.agents`, recover, resume ingestion) |
| `sse.py` | The event stream, with pings |
| `errors.py` | Every failure becomes an `ErrorBody` with a code |
| `context.py` | Who is calling and through which door (`X-TWYF-Source`, `X-TWYF-Client`, `X-Request-Id`) |
