"""Writes the demo's PDF and DOCX files under tests/fixtures/demo/ (10-demo-scenario.md section 2).

Run from backend/: uv run python scripts/make_demo_files.py. The two text files are written by hand."""

from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo"

CONTRACT = [
    "# Supply Agreement",
    "Clause 1, Parties. This Supply Agreement is made between Harbor Coffee Roasters (the Buyer) and Andes Green Coffee (the Supplier).",
    "Clause 2, Goods. The Supplier shall deliver washed arabica green coffee in 60 kilogram bags.",
    "Clause 4.2, Price adjustment. The Price shall be USD 6.40 per kilogram until 31 December 2026. From 1 January 2027 the Price shall increase by eight percent (8%) to USD 6.91 per kilogram.",
    "Clause 7, Term. This Agreement runs until 31 December 2028.",
]
HANDBOOK = [
    "# Employee handbook",
    "Section 2, Working hours. The standard working week is 40 hours.",
    "Section 3, Leave. Full-time staff receive 25 days of paid leave per year.",
    "Section 5, Conduct. Staff are expected to treat colleagues and customers with respect.",
]
LEASE = [
    "# Lease",
    "Section 1, Premises. The Landlord lets the roastery and office at 14 Quay Street to the Tenant.",
    "Section 2, Term. The Term shall commence on 1 July 2024 and shall expire on 30 June 2029 unless terminated earlier under Section 11.",
]
BOARD = [
    "# Board meeting, October 2026",
    "# Item 1, Attendance",
    "All five directors attended.",
    "# Item 3, Pricing and margin",
    "The board agreed to hold retail prices at current levels until the March 2027 meeting. The gross margin target for the financial year remains 55%.",
    "# Item 5, Staff",
    "Two seasonal staff will be hired for the holiday period.",
]


def make_pdf(path: Path, lines: list[str]) -> None:
    """One paragraph per line, wrapped, with a blank gap between paragraphs so pypdf's layout mode keeps it."""
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=True)
    pdf.setFont("Helvetica", 11)
    y = 790
    for line in lines:
        text = line.removeprefix("# ")
        for part in simpleSplit(text, "Helvetica", 11, 450):
            pdf.drawString(72, y, part)
            y -= 14
        y -= 28
    pdf.showPage()
    pdf.save()


def make_docx(path: Path, lines: list[str]) -> None:
    doc = Document()
    for line in lines:
        if line.startswith("# "):
            doc.add_heading(line.removeprefix("# "), level=1)
        else:
            doc.add_paragraph(line)
    doc.save(str(path))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_pdf(OUT / "supplier-contract-andes.pdf", CONTRACT)
    make_pdf(OUT / "hr-handbook.pdf", HANDBOOK)
    make_pdf(OUT / "office-lease.pdf", LEASE)
    make_docx(OUT / "board-notes-2026-10.docx", BOARD)


if __name__ == "__main__":
    main()
