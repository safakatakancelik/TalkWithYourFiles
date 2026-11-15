import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParsedBlock:
    kind: str  # 'heading' | 'paragraph' | 'row' | 'table' | 'image'
    label: str  # shown to people as the location
    text: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class ParsedDocument:
    kind: str  # extraction kind: 'text' | 'ocr'
    blocks: list[ParsedBlock]


class Parser(Protocol):
    name: str
    version: str

    def supports(self, file_type: str) -> bool: ...
    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]: ...


_BLANK_LINE = re.compile(r"\n\s*\n")


def paragraphs(text: str) -> list[str]:
    """Text split on blank lines, without empty pieces."""
    return [p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n")) if p.strip()]
