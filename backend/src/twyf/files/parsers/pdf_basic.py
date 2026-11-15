from pathlib import Path

from pypdf import PdfReader

from twyf.files.parsers.base import ParsedBlock, ParsedDocument, paragraphs


class PdfBasicParser:
    """pypdf: each page's text split into paragraphs on blank lines, labelled Page N.

    Layout mode is used because it keeps the blank lines between paragraphs."""

    name = "pdf_basic"
    version = "1"

    def supports(self, file_type: str) -> bool:
        return file_type == "pdf"

    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
        reader = PdfReader(path)
        blocks: list[ParsedBlock] = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text(extraction_mode="layout")
            for para in paragraphs(text):
                blocks.append(ParsedBlock("paragraph", f"Page {number}", para, page=number))
        return [ParsedDocument("text", blocks)]
