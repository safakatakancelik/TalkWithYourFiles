import importlib.util

from twyf.config import Settings
from twyf.files.parsers.base import Parser
from twyf.files.parsers.csv import CsvParser
from twyf.files.parsers.docx_basic import DocxBasicParser
from twyf.files.parsers.pdf_basic import PdfBasicParser
from twyf.files.parsers.text import TextParser

BASIC: list[Parser] = [TextParser(), CsvParser(), PdfBasicParser(), DocxBasicParser()]


def _docling() -> Parser | None:
    """The Docling parser, when it and its module (task B37) are installed."""
    if importlib.util.find_spec("docling") is None or importlib.util.find_spec("twyf.files.parsers.docling") is None:
        return None
    module = importlib.import_module("twyf.files.parsers.docling")
    parser: Parser = module.DoclingParser()
    return parser


def pick_parser(settings: Settings, file_type: str) -> Parser | None:
    """`auto` uses Docling when importable and the basic parser otherwise. None when nothing reads this type."""
    candidates: list[Parser] = []
    if settings.parser in ("auto", "docling"):
        docling = _docling()
        if docling is not None:
            candidates.append(docling)
    if settings.parser in ("auto", "basic"):
        candidates.extend(BASIC)
    return next((p for p in candidates if p.supports(file_type)), None)
