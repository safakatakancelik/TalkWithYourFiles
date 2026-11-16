"""Docling and fastembed (the rich extra). Marker `models`: run by hand with
`uv sync --extra rich && uv run pytest -m models`. The first run downloads models from Hugging Face."""

import io
import math
import sqlite3

import pytest

from tests.conftest import DEMO_FIXTURES, upload
from twyf.citations.locate import create_citation
from twyf.config import Settings
from twyf.contract.models import Workspace
from twyf.recording.context import RequestContext
from twyf.services import demo as demo_service

pytestmark = pytest.mark.models

STORY_QUOTES = {
    "f-contract": ["From 1 January 2027 the Price shall increase by eight percent (8%)"],
    "f-board": ["hold retail prices at current levels until the March 2027 meeting"],
    "f-lease": ["shall expire on 30 June 2029"],
}


def test_demo_documents_parse_with_pages_and_quotes(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    settings.parser = "docling"  # the services read the settings at call time
    agent = conn.execute(
        "SELECT id FROM v_agents WHERE workspace_id = ? AND agent_kind = 'orchestrator'", (ws.id,)
    ).fetchone()[0]
    for file_id in ("f-contract", "f-board", "f-hr", "f-lease"):
        name = demo_service.FILES[file_id]
        item = upload(ctx, ws.id, name, (DEMO_FIXTURES / name).read_bytes(), file_id=f"{file_id}-d")
        assert item.status == "ready", name
        parser = conn.execute(
            "SELECT x.parser FROM extractions x JOIN v_files f ON f.file_version_id = x.file_version_id WHERE f.id = ?",
            (item.id,),
        ).fetchone()[0]
        assert parser == "docling"
        if name.endswith(".pdf"):
            pages = conn.execute(
                "SELECT b.page FROM blocks b JOIN extractions x ON x.id = b.extraction_id"
                " JOIN v_files f ON f.file_version_id = x.file_version_id WHERE f.id = ?",
                (item.id,),
            ).fetchall()
            assert pages and all(p[0] == 1 for p in pages)
        quotes = [q for n in demo_service.NOTES if n[1] == file_id for q in n[4]] + STORY_QUOTES.get(file_id, [])
        for quote in quotes:
            passage = demo_service.passage_with(conn, item.id, quote)
            row = create_citation(
                conn, ctx, workspace_id=ws.id, passage_id=passage, quote=quote, agent_id=agent, turn_id=None
            )
            assert row.quote == quote and quote in row.passage


def test_image_text_becomes_an_ocr_extraction(
    ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, settings: Settings
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    settings.parser = "docling"
    image = Image.new("RGB", (900, 240), "white")
    ImageDraw.Draw(image).text((40, 80), "INVOICE TOTAL 4200 EUR", fill="black", font=ImageFont.load_default(size=56))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    item = upload(ctx, ws.id, "invoice.png", buffer.getvalue())
    kind, text = conn.execute(
        "SELECT x.kind, x.text FROM extractions x JOIN v_files f ON f.file_version_id = x.file_version_id"
        " WHERE f.id = ? AND x.status = 'ok'",
        (item.id,),
    ).fetchone()
    assert kind == "ocr" and "INVOICE" in text.upper() and "4200" in text


def test_fastembed_unit_vectors_of_384_dimensions() -> None:
    from twyf.retrieval.embedder import FastEmbedEmbedder

    embedder = FastEmbedEmbedder()
    assert embedder.dim == 384
    vectors = embedder.embed(["The lease ends in June.", "Rent rises by eight percent."])
    assert all(len(v) == 384 and math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-5) for v in vectors)
