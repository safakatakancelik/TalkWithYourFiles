# Parsers

Each parser turns a file into blocks of text with a label ("Page 3", "Row 4", a heading). `pick_parser` in `__init__.py` chooses one from `TWYF_PARSER`.

| File | What it is |
|---|---|
| `base.py` | `ParsedBlock`, `ParsedDocument`, the `Parser` protocol |
| `text.py` | Text and Markdown |
| `csv.py` | CSV: one block per row |
| `pdf_basic.py` | PDF with `pypdf` |
| `docx_basic.py` | Word with `python-docx` |
| `docling.py` | PDF, Word and images with Docling (the `rich` extra) |
