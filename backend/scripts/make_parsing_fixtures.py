"""Writes the small parser fixtures under tests/fixtures/parsing/. Run from backend/: uv run python scripts/make_parsing_fixtures.py"""

from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "parsing"

PAGES = [
    ["The lease starts on 1 July 2024.", "", "Rent is reviewed every year."],
    ["The tenant may end the lease early.", "", "Notice must be given in writing."],
]


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=True)
    for lines in PAGES:
        y = 800
        for line in lines:
            if line:
                pdf.drawString(72, y, line)
            y -= 40 if not line else 16
        pdf.showPage()
    pdf.save()


def make_docx(path: Path) -> None:
    doc = Document()
    doc.add_paragraph("Opening words before any heading.")
    doc.add_heading("Payment terms", level=1)
    doc.add_paragraph("Invoices are paid within 30 days.")
    table = doc.add_table(rows=2, cols=2)
    for r, (a, b) in enumerate([("Item", "Price"), ("Widget", "29.00")]):
        table.cell(r, 0).text = a
        table.cell(r, 1).text = b
    doc.add_paragraph("Late payment adds 2% a month.")
    doc.save(str(path))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_pdf(OUT / "sample.pdf")
    make_docx(OUT / "sample.docx")
    (OUT / "corrupt.pdf").write_bytes(b"%PDF-1.4\nthis is not really a pdf\n")


if __name__ == "__main__":
    main()
