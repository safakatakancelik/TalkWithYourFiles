"""`twyf seed-demo`: the demo workspace of 10-demo-scenario.md section 3, with fixed ids."""

import sqlite3
from pathlib import Path

from twyf.agents.definitions import current_version, resolve
from twyf.citations.locate import create_citation
from twyf.config import Settings
from twyf.contextmap.service import add_mentions
from twyf.contract.operations import UploadFileInput
from twyf.contract.turns import EntityOut
from twyf.db.connection import transaction
from twyf.db.repos import agents as agents_repo
from twyf.db.repos import files as files_repo
from twyf.db.repos import notes as notes_repo
from twyf.db.repos import sessions as sessions_repo
from twyf.db.repos import workspaces as workspaces_repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import files, state
from twyf.services.errors import ServiceError
from twyf.services.sessions import add_message

WORKSPACE = ("demo", "Harbor Coffee Roasters (demo)")
FILES = {
    "f-contract": "supplier-contract-andes.pdf",
    "f-sales": "q3-sales-2026.csv",
    "f-board": "board-notes-2026-10.docx",
    "f-pricing": "pricing-policy.md",
    "f-hr": "hr-handbook.pdf",
    "f-lease": "office-lease.pdf",
}
TRANSLATORS = [
    ("a-t1", "Translator 1", "generic"),
    ("a-t2", "Translator 2", "generic"),
    ("a-contracts", "Contracts translator", "contracts"),
    ("a-finance", "Finance translator", "finance"),
    ("a-people", "People translator", "people"),
]
BUILTINS = [("orchestrator", "Orchestrator"), ("verifier", "Verifier"), ("chat", "Chat")]
NOTES = [
    ("n-contract", "f-contract", "a-contracts",
     "Supply contract with Andes Green Coffee. Green coffee at $6.40 per kg through December 2026, with an 8% increase from 1 January 2027.",
     ["The Price shall be USD 6.40 per kilogram until 31 December 2026", "From 1 January 2027 the Price shall increase by eight percent (8%)"]),
    ("n-sales", "f-sales", "a-finance",
     "Q3 2026 sales by channel. 5,150 kg sold at an average of $29.00 per kg. Cost of goods $13.05 per kg, of which green coffee is $7.60.",
     ["total_kg=5150, avg_price_per_kg=29.00, cogs_per_kg=13.05, green_coffee_per_kg=7.60"]),
    ("n-board", "f-board", "a-t1",
     "October 2026 board meeting. Retail prices held until March 2027. Gross margin target set at 55%.",
     ["hold retail prices at current levels until the March 2027 meeting", "The gross margin target for the financial year remains 55%"]),
    ("n-pricing", "f-pricing", "a-t2",
     "Pricing policy. Prices must be reviewed when cost of goods moves more than 5%. Wholesale discounts are capped at 15%.",
     ["A price review is required whenever cost of goods moves by more than 5%", "Wholesale discounts are capped at 15%"]),
    ("n-hr", "f-hr", "a-people", "Employee handbook: leave, working hours, conduct and benefits.",
     ["Full-time staff receive 25 days of paid leave per year"]),
    ("n-lease", "f-lease", "a-contracts", "Lease for the roastery and office at 14 Quay Street, running to 2029.",
     ["roastery and office at 14 Quay Street", "shall expire on 30 June 2029"]),
]  # fmt: skip
ENTITIES = [
    ("e-andes", "Andes Green Coffee", "company", ["f-contract"]),
    ("e-margin", "Gross margin target 55%", "decision", ["f-sales", "f-board"]),
    ("e-prices", "Retail prices", "decision", ["f-sales", "f-board", "f-pricing"]),
    ("e-quay", "14 Quay Street", "place", ["f-lease"]),
    ("e-staff", "Staff", "other", ["f-hr", "f-board"]),
]
SESSION = ("s-lease", "When does the office lease end?")
LEASE_ANSWER = "The lease for 14 Quay Street runs until 30 June 2029 [1]."


def passage_with(conn: sqlite3.Connection, file_id: str, quote: str) -> str:
    """The id of the passage of the file's current version that contains the quote."""
    row = conn.execute(
        "SELECT c.id FROM chunks c JOIN extractions x ON x.id = c.extraction_id JOIN v_files f"
        " ON f.file_version_id = x.file_version_id WHERE f.id = ? AND instr(c.text, ?) > 0 ORDER BY c.ordinal LIMIT 1",
        (file_id, quote),
    ).fetchone()
    if row is None:
        raise ServiceError("internal", f"demo quote not found in {file_id}: {quote!r}")
    return f"p{row[0]}"


def _cite(conn: sqlite3.Connection, ctx: RequestContext, file_id: str, quote: str, agent_id: str) -> str:
    return create_citation(conn, ctx.as_actor(agent_id, ctx.source), workspace_id=WORKSPACE[0],
                           passage_id=passage_with(conn, file_id, quote), quote=quote, agent_id=agent_id, turn_id=None).id  # fmt: skip


def _workspace(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    ws_id, name = WORKSPACE
    workspaces_repo.insert(conn, ws_id, ctx.user_id, name)
    event = record(conn, ctx, "workspace.created", workspace_id=ws_id, entity_type="workspace", entity_id=ws_id,
                   payload={"name": name})  # fmt: skip
    agents = [(new_id("a"), kind, label, "") for kind, label in BUILTINS]
    agents += [(agent_id, "translator", label, specialty) for agent_id, label, specialty in TRANSLATORS]
    for agent_id, kind, label, specialty in agents:
        definition_id = resolve(conn, kind, specialty or kind)
        agents_repo.insert(conn, ws_id, agent_id, kind, label, specialty, definition_id)
        record(conn, ctx.caused_by(event), "agent.created", workspace_id=ws_id, entity_type="agent", entity_id=agent_id,
               payload={"kind": kind, "name": label, "specialty": specialty},
               definition_version_id=current_version(conn, definition_id).id)  # fmt: skip


def _notes_entities_session(conn: sqlite3.Connection, ctx: RequestContext) -> None:
    ws_id = WORKSPACE[0]
    for note_id, file_id, author, text, quotes in NOTES:
        cited = [_cite(conn, ctx, file_id, q, author) for q in quotes]
        current = files_repo.get(conn, ws_id, file_id)
        assert current is not None
        notes_repo.insert(conn, note_id=note_id, workspace_id=ws_id, file_id=file_id,
                          file_version_id=current["file_version_id"], author_id=author, kind="summary", text=text,
                          citation_ids=cited, question_id=None, turn_id=None)  # fmt: skip
        record(conn, ctx, "note.created", workspace_id=ws_id, entity_type="note", entity_id=note_id,
               payload={"file_id": file_id, "kind": "summary", "author_id": author})  # fmt: skip
    for entity_id, label, kind, file_ids in ENTITIES:
        for i, file_id in enumerate(file_ids):
            add_mentions(conn, ctx, workspace_id=ws_id, entities=[EntityOut(label=label, type=kind, passage_id=file_id)],
                         passage_file=lambda p: p, question_id=None, entity_id=entity_id if i == 0 else None)  # fmt: skip
    session_id, title = SESSION
    sessions_repo.insert(conn, ws_id, session_id, title)
    record(conn, ctx, "session.created", workspace_id=ws_id, session_id=session_id, entity_type="session",
           entity_id=session_id, payload={"title": title})  # fmt: skip
    add_message(conn, ctx, workspace_id=ws_id, session_id=session_id, role="user", text=title)
    lease = _cite(conn, ctx, "f-lease", "shall expire on 30 June 2029", "a-contracts")
    chat = agents_repo.builtin(conn, ws_id, "chat").id
    add_message(conn, ctx.as_actor(chat, ctx.source), workspace_id=ws_id, session_id=session_id, role="assistant",
                text=LEASE_ANSWER, citation_ids=[lease])  # fmt: skip


def seed(ctx: RequestContext, settings: Settings, fixtures: Path) -> None:
    """Creates the demo workspace. Refuses to run when workspace `demo` exists. Files are ingested inline."""
    with state.db() as conn, transaction(conn):
        if conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (WORKSPACE[0],)).fetchone() is not None:
            raise ServiceError("conflict", "The demo workspace already exists")
        _workspace(conn, ctx)
    for file_id, name in FILES.items():
        with (fixtures / name).open("rb") as stream:
            item = files.upload(ctx, UploadFileInput(ws=WORKSPACE[0]), name=name, stream=stream, file_id=file_id)
        if item.status != "ready":
            raise ServiceError("internal", f"demo file {name} is {item.status}, not ready: ingestion must run inline")
    with state.db() as conn, transaction(conn):
        _notes_entities_session(conn, ctx)
        record(conn, ctx, "demo.seeded", workspace_id=WORKSPACE[0], entity_type="workspace", entity_id=WORKSPACE[0])
