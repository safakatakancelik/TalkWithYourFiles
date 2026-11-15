import csv
from pathlib import Path

from twyf.files.parsers.base import ParsedBlock, ParsedDocument


class CsvParser:
    """One row block per data row, `col=value, col=value`, labelled Row N from 1."""

    name = "csv"
    version = "1"

    def supports(self, file_type: str) -> bool:
        return file_type == "csv"

    def parse(self, path: Path, file_type: str) -> list[ParsedDocument]:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            rows = list(csv.reader(f))
        if not rows:
            return [ParsedDocument("text", [])]
        header, data = rows[0], rows[1:]
        blocks: list[ParsedBlock] = []
        for n, row in enumerate(data, start=1):
            names = header + [f"column {i + 1}" for i in range(len(header), len(row))]
            text = ", ".join(f"{col}={value}" for col, value in zip(names, row, strict=False))
            blocks.append(ParsedBlock("row", f"Row {n}", text))
        return [ParsedDocument("text", blocks)]
