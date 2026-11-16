#!/usr/bin/env bash
# Starts the whole app: the backend, the UI and the agents. Ctrl+C stops everything.
#   ./start.sh                 agents run through Claude Code (`claude -p`), one process per turn
#   ./start.sh --model opus    the model for every turn (an alias or a full name; default: sonnet, or $TWYF_MODEL)
#   ./start.sh --queue         no agents started here: a harness connected through MCP does the turns
#   ./start.sh --no-browser    do not open the browser
#   ./start.sh --backend-only  no UI: the API (and its /docs page) with the agents
# With ANTHROPIC_API_KEY set, turns are billed to that key (`claude --bare`); otherwise to your Claude Code login.
# The API listens on $TWYF_PORT (default 8321) and the UI on $TWYF_UI_PORT (default 5173).
set -euo pipefail
cd "$(dirname "$0")"

model="${TWYF_MODEL:-sonnet}"
runtime=command
open=--open
ui=yes
while [ $# -gt 0 ]; do
  case "$1" in
    --model) model="$2"; shift 2 ;;
    --queue) runtime=queue; shift ;;
    --no-browser) open=; shift ;;
    --backend-only) ui=; shift ;;
    -h|--help) sed -n 2,9p "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see ./start.sh --help)" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null || { echo "$1 is not installed: $2" >&2; exit 1; }; }
need uv "https://docs.astral.sh/uv/"
need npm "https://nodejs.org/"
need curl "your package manager"
port="${TWYF_PORT:-8321}"
api="http://127.0.0.1:$port"
ui_port="${TWYF_UI_PORT:-5173}"
if curl -sf "$api/api/v1/health" >/dev/null; then
  echo "A backend is already running on port $port. Stop it, or pick another port with TWYF_PORT." >&2
  exit 1
fi

export TWYF_RUNTIME="$runtime"
export TWYF_CORS_ORIGINS="${TWYF_CORS_ORIGINS:-[\"http://localhost:$ui_port\"]}"
if [ "$runtime" = command ]; then
  need claude "https://docs.claude.com/en/docs/claude-code"
  # No tools, no MCP servers, no saved sessions: a turn only reads its input and returns JSON.
  flags='"claude","-p","--output-format","json","--model","'"$model"'","--tools","","--strict-mcp-config","--no-session-persistence"'
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    flags="$flags"',"--bare"'
    echo "Agents: Claude Code, model $model, billed to ANTHROPIC_API_KEY."
  else
    echo "Agents: Claude Code, model $model, on your Claude Code login."
  fi
  export TWYF_COMMAND="[$flags]"
else
  echo "Agents: none started here. In a harness connected through MCP, run the work_agent_queue prompt."
fi

[ -z "$ui" ] || [ -d frontend/node_modules ] || (cd frontend && npm install)

# Stops the backend and the UI with everything they started, however this script ends.
stop_tree() { local child; for child in $(pgrep -P "$1"); do stop_tree "$child"; done; kill "$1" 2>/dev/null || true; }
trap 'for job in $(jobs -p); do stop_tree "$job"; done' EXIT
trap 'exit 130' INT TERM

uv run --directory backend twyf serve &
backend=$!
for _ in $(seq 120); do
  curl -sf "$api/api/v1/health" >/dev/null && break
  kill -0 $backend 2>/dev/null || { echo "The backend did not start." >&2; exit 1; }
  sleep 0.5
done
curl -sf "$api/api/v1/health" >/dev/null || { echo "The backend did not answer on $api." >&2; exit 1; }

if [ -z "$ui" ]; then
  echo "API on $api, its documentation on $api/docs. Ctrl+C stops it."
  wait $backend
  exit
fi
(cd frontend && VITE_BACKEND_URL="$api" exec npm run dev -- --port "$ui_port" --strictPort $open) &
wait $!
