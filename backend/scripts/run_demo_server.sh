#!/usr/bin/env bash
# Starts the real backend with the demo seeded and the scripted fake runtime, for the frontend's scenario test:
#   backend/scripts/run_demo_server.sh   then, from frontend/:   TWYF_TEST_BACKEND_URL=http://127.0.0.1:8321 npm test
# Each run uses a fresh data folder, because the test changes the demo workspace.
set -euo pipefail
cd "$(dirname "$0")/.."
export TWYF_DATA_DIR="$(mktemp -d -t twyf-demo-XXXXXX)"
export TWYF_FIRST_READ=false TWYF_EMBEDDER=hash TWYF_PARSER=basic
uv run twyf seed-demo
exec uv run twyf serve --runtime fake --fake-script tests/fixtures/demo/script.json
