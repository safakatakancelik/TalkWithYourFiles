# Scripts

| File | What it is |
|---|---|
| `run_demo_server.sh` | Starts the backend with a fresh data folder, the demo seeded and the scripted fake runtime, for the frontend's demo test |
| `check_coverage.py` | Fails unless the modules that guard correctness are 100% covered (run after `pytest --cov ... --cov-report=json`) |
| `make_demo_files.py` | Writes the demo's PDF and DOCX files into `tests/fixtures/demo/` |
| `make_parsing_fixtures.py` | Writes the PDF and DOCX parser fixtures into `tests/fixtures/parsing/` |
