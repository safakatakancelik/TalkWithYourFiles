from pathlib import Path

from twyf.files.parsers.base import ParsedBlock, ParsedDocument, paragraphs


def _pieces(para: str, markdown: bool) -> list[tuple[str, str]]:
    """A paragraph as (kind, text) pieces: in Markdown, each line starting with # is its own heading."""
    pieces: list[tuple[str, str]] = []
    lines: list[str] = []
    for line in para.split("\n"):
        if markdown and line.lstrip().startswith("#"):
            if lines:
                pieces.append(("paragraph", "\n".join(lines)))
                lines = []
            pieces.append(("heading", line.strip().lstrip("#").strip()))
        else:
            lines.append(line)
    if lines:
        pieces.append(("paragraph", "\n".join(lines)))
    return pieces


class TextParser:
    """txt: one block per paragraph. md: the same, and a line starting with # is a heading."""

    name = "text"
    version = "1"

    def supports(self, file_type: str) -> bool:
        return file_type in ("txt", "md")

    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
        text = path.read_text(encoding="utf-8", errors="replace")
        blocks: list[ParsedBlock] = []
        heading: str | None = None
        n = 0
        for para in paragraphs(text):
            for kind, piece in _pieces(para, file_type == "md"):
                if kind == "heading":
                    heading = piece
                    blocks.append(ParsedBlock("heading", piece, piece))
                else:
                    n += 1
                    blocks.append(ParsedBlock("paragraph", heading or f"Paragraph {n}", piece))
        return [ParsedDocument("text", blocks)]
