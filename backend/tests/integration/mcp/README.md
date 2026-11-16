# MCP tests

Through the MCP server, which calls the app over HTTP.

| File | What it is |
|---|---|
| `test_mcp.py` | Parity with the HTTP routes, tool schemas, uploads, `ask` with and without waiting, a worker loop, resources, prompts, errors |
| `streaming.py` | A streaming ASGI transport, so `ask` with `wait: false` returns before the question ends |
| `conftest.py` | A client that opens a fresh MCP session per call |
