# Dependencies

Every package this project depends on directly, why it is needed, and where it is used. Versions are the ones locked in `backend/uv.lock` and `frontend/package-lock.json` on 2026-11-16. Everything is free and open source, and nothing needs an account.

When you add, remove or upgrade a dependency, update this file in the same change.

## Backend: always installed

Declared in `backend/pyproject.toml` under `[project] dependencies`. Installed by `uv sync`.

| Package | Version | Why it is needed | Used in |
|---|---|---|---|
| `fastapi` | 0.163.1 | The HTTP API. Routes are generated from the operation list; it also serves the `/docs` page and the event streams | `src/twyf/http/` |
| `uvicorn` | 0.54.0 | The web server that runs the FastAPI app (`twyf serve`) | `src/twyf/cli.py` |
| `pydantic` | 2.14.3 | Every type that crosses a boundary: wire models, agent events, turn inputs and outputs. The JSON Schema in `contract/schema.json` is generated from it | `src/twyf/contract/`, everywhere |
| `pydantic-settings` | 2.16.3 | Reads the `TWYF_*` settings from the environment or a `.env` file | `src/twyf/config.py` |
| `httpx` | 0.28.1 | The MCP server calls the HTTP API with it; the evaluation runner and the tests do too | `src/twyf/mcp/`, `src/twyf/evals/` |
| `mcp` | 2.3.0 | The official Model Context Protocol SDK. Turns every operation into an MCP tool, plus resources and prompts, so harnesses can use the app | `src/twyf/mcp/server.py` |
| `sqlite-vec` | 0.1.9 | A SQLite extension that computes vector distance inside the database, for search by meaning. If it cannot load, a numpy fallback is used | `src/twyf/retrieval/vector_index.py` |
| `numpy` | 2.5.4 | The fallback vector search, and the similarity of note vectors | `src/twyf/retrieval/` |
| `pypdf` | 7.1.0 | The basic PDF reader: the text of each page | `src/twyf/files/parsers/pdf_basic.py` |
| `python-docx` | 1.2.0 | The basic Word reader: paragraphs, headings and table rows | `src/twyf/files/parsers/docx_basic.py` |
| `simpleeval` | 1.0.8 | Evaluates the arithmetic of derived claims (for example `1 - 13.05 / 29.00`) safely, without `eval` | `src/twyf/orchestration/arithmetic.py` |
| `python-multipart` | 0.0.33 | Lets FastAPI read file uploads (`multipart/form-data`) | `src/twyf/http/app.py` |

The standard library covers the rest: `sqlite3` (the database, with FTS5 for keyword search), `csv`, `json`, `hashlib`, `asyncio`.

## Backend: the optional `rich` extra

Declared under `[project.optional-dependencies] rich`. Installed only by `uv sync --extra rich`. Without it the app uses the basic parsers and searches by keyword only.

| Package | Version | Why it is needed | Used in |
|---|---|---|---|
| `docling-slim[standard]` | 2.150.1 | Layout-aware reading of PDF and Word (reading order, headings, tables, page numbers and positions), and OCR for images and scanned pages. The `standard` part holds the converters; the plain `docling` package has none | `src/twyf/files/parsers/docling.py` |
| `fastembed` | 0.9.1 | Turns text into vectors on this machine (model `BAAI/bge-small-en-v1.5`, 384 dimensions), for search by meaning | `src/twyf/retrieval/embedder.py` |
| `torch` | 2.15.0+cpu | Runs Docling's layout and table models. Taken from PyTorch's CPU-only index | needed by Docling |
| `torchvision` | 0.29.2+cpu | Image handling for those models. Also from the CPU-only index | needed by Docling |

**Why the CPU-only builds.** Torch's default Linux build includes NVIDIA GPU libraries, which make the extra about 3.4 GB to download. This project does not use a GPU. `[tool.uv.sources]` in `pyproject.toml` takes `torch` and `torchvision` from `https://download.pytorch.org/whl/cpu`, which makes the whole extra about 450 MB to download. They are named in the extra only so that this source applies: uv honours sources for packages the project names itself.

The largest packages the extra brings in with it:

| Package | Download | Brought in by, for |
|---|---|---|
| `torch` (CPU) | 210 MB | Docling's models |
| `opencv-python-headless` | 61 MB | Docling, image processing for OCR |
| `scipy` | 38 MB | Docling, layout processing |
| `onnxruntime` | 28 MB | fastembed, runs its model |
| `rapidocr` | 27 MB | Docling, reads text from images |
| `transformers`, `tokenizers` | 24 MB | Docling and fastembed, load models |
| `pandas` | 13 MB | Docling, table export |
| `docling-parse` | 11 MB | Docling, the PDF text layer |

**Models.** The first run downloads models from Hugging Face into `~/.cache/huggingface` (about 720 MB: Docling's layout, table and OCR models, and the embedding model). After that nothing leaves the machine.

## Backend: development only

Declared under `[dependency-groups] dev`. Installed by `uv sync`, not needed to run the app.

| Package | Version | Why it is needed |
|---|---|---|
| `pytest` | 9.2.0 | Runs the tests |
| `pytest-asyncio` | 1.5.0 | Lets tests be `async` (the engine, streams, MCP) |
| `pytest-cov` | 7.1.0 | Measures coverage (`--cov`), checked by `scripts/check_coverage.py` |
| `ruff` | 0.17.5 | Lint and format |
| `pyright` | 1.1.414 | Strict type checking of `src/` |
| `jsonschema` | 4.26.0 | Checks the samples in `tests/fixtures/samples.json` against `contract/schema.json` |
| `reportlab` | 5.1.0 | Writes the PDF test fixtures (`scripts/make_parsing_fixtures.py`, `scripts/make_demo_files.py`) |

Two local type stubs in `backend/typings/` describe `sqlite_vec` and `simpleeval`, which ship no type information.

## Frontend

From `frontend/package.json`. Installed by `npm install`.

| Package | Version | Kind | Why it is needed |
|---|---|---|---|
| `react` | 19.3.1 | runtime | The UI |
| `react-dom` | 19.3.1 | runtime | Renders the UI in the browser |
| `vite` | 8.3.8 | dev | Dev server and production build |
| `@vitejs/plugin-react` | 6.3.0 | dev | JSX and fast refresh for Vite |
| `typescript` | 7.0.2 | dev | Type checking; `npm run build` runs `tsc` first |
| `@types/react`, `@types/react-dom` | 19.3.0 | dev | Types for React |
| `vitest` | 5.1.0 | dev | Runs the frontend tests (`npm test`) |
| `json-schema-to-typescript` | 16.0.0 | dev | Generates `src/backend/contract.gen.ts` from `contract/schema.json` (`npm run gen:contract`), so the compiler catches drift between the UI's types and the backend's |

## CI

`.github/workflows/ci.yml` uses three published actions: `actions/checkout`, `astral-sh/setup-uv` and `actions/setup-node`.
