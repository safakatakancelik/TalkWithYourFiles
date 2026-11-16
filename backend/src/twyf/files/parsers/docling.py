"""The rich parser: Docling, for PDF (layout, tables, OCR of pages without text), DOCX and images (OCR).

Optional: installed with `uv sync --extra rich`. Docling is loaded with importlib so the module imports, and the
type check passes, without it. Its models are downloaded from Hugging Face the first time it runs."""

import importlib
import importlib.metadata
from functools import cache
from pathlib import Path
from typing import Any

from twyf.files.parsers.base import ParsedBlock, ParsedDocument

HEADINGS = {"section_header", "title"}
TEXT = {"text", "paragraph", "list_item", "caption", "footnote", "code", "formula", "reference", "handwritten_text"}


@cache
def _converter() -> Any:
    """One converter per process: building it loads the layout and OCR models."""
    return importlib.import_module("docling.document_converter").DocumentConverter()


def _page_and_box(item: Any) -> tuple[int | None, tuple[float, float, float, float] | None]:
    provenance = list(getattr(item, "prov", None) or [])
    if not provenance:
        return None, None
    box = provenance[0].bbox
    return int(provenance[0].page_no), (float(box.l), float(box.t), float(box.r), float(box.b))


class DoclingParser:
    name = "docling"

    def __init__(self) -> None:
        self.version = importlib.metadata.version("docling-slim")

    def supports(self, file_type: str) -> bool:
        return file_type in ("pdf", "docx", "image")

    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
        document = _converter().convert(path).document
        image = file_type == "image"
        blocks: list[ParsedBlock] = []
        heading: str | None = None
        n = 0

        def label(page: int | None) -> str:
            if image:
                return "Image text"
            if page is not None:
                return f"Page {page}, {heading}" if heading else f"Page {page}"
            return heading or f"Paragraph {n}"

        for item, _ in document.iterate_items():
            kind = str(getattr(getattr(item, "label", ""), "value", getattr(item, "label", "")))
            page, box = _page_and_box(item)
            if kind in HEADINGS and getattr(item, "text", ""):
                heading = str(item.text).strip()
                blocks.append(ParsedBlock("heading", heading, heading, page, box))
            elif kind in TEXT and getattr(item, "text", ""):
                n += 1
                blocks.append(ParsedBlock("paragraph", label(page), str(item.text), page, box))
            elif kind == "table":
                frame = item.export_to_dataframe(doc=document)
                for _, row in frame.iterrows():
                    n += 1
                    text = ", ".join(f"{col}={value}" for col, value in row.items())
                    blocks.append(ParsedBlock("row", label(page), text, page, box))
        return [ParsedDocument("ocr" if image else "text", blocks)]
