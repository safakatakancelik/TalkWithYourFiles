# Files

The app keeps its own copy of every file and every version, named by its hash, and never changes or removes one.

| File | What it is |
|---|---|
| `store.py` | Saves uploaded bytes under `files/<aa>/<sha256>`, enforcing the size limit |
| `integrity.py` | The availability check: is the copy still there, with the same bytes |
| `ingest.py` | The background pipeline: parse, extraction and blocks, chunks, vectors |
| `chunker.py` | Packs blocks into chunks whose offsets index exactly into the text |
| `jobs.py` | Background jobs: one worker thread in the server, inline in tests |
| `first_read.py` | One bounded summary turn on a newly indexed file |
| `describe.py` | A description of an image, by a runtime that can see |
| `types.py` | File type from the extension |
| `parsers/` | Turning files into text blocks |
