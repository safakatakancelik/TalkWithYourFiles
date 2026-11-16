import importlib.util
from pathlib import Path

from twyf.config import Settings
from twyf.files.parsers import pick_parser
from twyf.files.parsers.base import ParsedBlock
from twyf.files.parsers.csv import CsvParser
from twyf.files.parsers.docx_basic import DocxBasicParser
from twyf.files.parsers.pdf_basic import PdfBasicParser
from twyf.files.parsers.text import TextParser

FIXTURES = Path(__file__).parents[3] / "fixtures" / "parsing"


def _blocks(
    parser: TextParser | CsvParser | PdfBasicParser | DocxBasicParser, name: str, kind: str
) -> list[ParsedBlock]:
    [document] = parser.parse(FIXTURES / name, kind)
    assert document.kind == "text"
    return document.blocks


def test_parser_text() -> None:
    blocks = _blocks(TextParser(), "sample.txt", "txt")
    assert [(b.kind, b.label) for b in blocks] == [("paragraph", f"Paragraph {n}") for n in (1, 2, 3)]
    assert blocks[0].text == "First paragraph\nstill first."
    assert blocks[2].text == "Third."


def test_parser_md() -> None:
    blocks = _blocks(TextParser(), "sample.md", "md")
    assert [(b.kind, b.label, b.text) for b in blocks] == [
        ("paragraph", "Paragraph 1", "Intro before a heading."),
        ("heading", "Term", "Term"),
        ("paragraph", "Term", "The term is five years."),
        ("heading", "Break clause", "Break clause"),
        ("paragraph", "Break clause", "The tenant may break at year three."),
    ]


def test_parser_csv() -> None:
    blocks = _blocks(CsvParser(), "sample.csv", "csv")
    assert [(b.kind, b.label, b.text) for b in blocks] == [
        ("row", "Row 1", "item=Widget, price=29.00, qty=3"),
        ("row", "Row 2", "item=Gadget, large, price=13.05, qty=1"),
    ]


def test_parser_pdf_basic() -> None:
    blocks = _blocks(PdfBasicParser(), "sample.pdf", "pdf")
    assert [(b.kind, b.label, b.page) for b in blocks] == [
        ("paragraph", "Page 1", 1), ("paragraph", "Page 1", 1), ("paragraph", "Page 2", 2), ("paragraph", "Page 2", 2),
    ]  # fmt: skip
    assert [b.text.strip() for b in blocks] == [
        "The lease starts on 1 July 2024.",
        "Rent is reviewed every year.",
        "The tenant may end the lease early.",
        "Notice must be given in writing.",
    ]


def test_parser_docx_basic() -> None:
    blocks = _blocks(DocxBasicParser(), "sample.docx", "docx")
    assert [(b.kind, b.label, b.text) for b in blocks] == [
        ("paragraph", "Paragraph 1", "Opening words before any heading."),
        ("heading", "Payment terms", "Payment terms"),
        ("paragraph", "Payment terms", "Invoices are paid within 30 days."),
        ("row", "Payment terms", "Item | Price"),
        ("row", "Payment terms", "Widget | 29.00"),
        ("paragraph", "Payment terms", "Late payment adds 2% a month."),
    ]


def test_pick_parser(settings: Settings) -> None:
    basic = settings.model_copy(update={"parser": "basic"})
    assert isinstance(pick_parser(basic, "pdf"), PdfBasicParser)
    assert isinstance(pick_parser(basic, "md"), TextParser)
    assert pick_parser(basic, "image") is None
    assert pick_parser(basic, "other") is None
    auto = settings.model_copy(update={"parser": "auto"})
    rich = importlib.util.find_spec("docling") is not None
    assert type(pick_parser(auto, "docx")).__name__ == ("DoclingParser" if rich else "DocxBasicParser")
