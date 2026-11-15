from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

from twyf.files.parsers.base import ParsedBlock, ParsedDocument


def _is_heading(paragraph: Paragraph) -> bool:
    style = paragraph.style.name if paragraph.style is not None else ""
    return bool(style) and (style.startswith("Heading") or style == "Title")


class DocxBasicParser:
    """python-docx: paragraphs and table rows in order. Label: the nearest heading above, or Paragraph N."""

    name = "docx_basic"
    version = "1"

    def supports(self, file_type: str) -> bool:
        return file_type == "docx"

    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
        document = Document(str(path))
        blocks: list[ParsedBlock] = []
        heading: str | None = None
        n = 0
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                if _is_heading(item):
                    heading = text
                    blocks.append(ParsedBlock("heading", text, text))
                    continue
                n += 1
                blocks.append(ParsedBlock("paragraph", heading or f"Paragraph {n}", text))
            else:
                for row in item.rows:
                    text = " | ".join(cell.text.strip() for cell in row.cells)
                    if text.strip(" |"):
                        n += 1
                        blocks.append(ParsedBlock("row", heading or f"Paragraph {n}", text))
        return [ParsedDocument("text", blocks)]
