# The MCP door

A separate process (`twyf mcp`) that calls the HTTP API; it never opens the database.

| File | What it is |
|---|---|
| `server.py` | One tool per operation, generated; `upload_file` by path or base64; `ask` with `wait`; resources; the `ask_files` and `work_agent_queue` prompts |
| `client.py` | Turns one operation call into one HTTP request |
