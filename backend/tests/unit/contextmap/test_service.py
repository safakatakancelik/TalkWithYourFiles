import sqlite3

import pytest

from tests.conftest import EventsHelper, upload
from twyf.contextmap.service import add_mentions
from twyf.contract.models import MapLink, MapNode, Workspace
from twyf.contract.operations import CreateWorkspaceInput, DeleteFileInput, GetContextMapInput
from twyf.contract.turns import EntityOut
from twyf.db.connection import transaction
from twyf.recording.context import RequestContext
from twyf.services import contextmap, files, workspaces


def _add(
    conn: sqlite3.Connection, ctx: RequestContext, ws_id: str, file_id: str, *labels: tuple[str, str]
) -> tuple[list[MapNode], list[MapLink]]:
    with transaction(conn):
        return add_mentions(
            conn, ctx, workspace_id=ws_id, entities=[EntityOut(label=l, type=t, passage_id="p1") for l, t in labels],
            passage_file=lambda _: file_id, question_id=None,
        )  # fmt: skip


def test_entity_upsert(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection, events: EventsHelper) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Acme Ltd signed.")
    b = upload(ctx, ws.id, "b.txt", b"ACME LTD paid.")
    nodes, links = _add(conn, ctx, ws.id, a.id, ("Acme  Ltd", "company"), ("30 June", "weird-type"))
    assert [n.label for n in nodes] == ["Acme  Ltd", "30 June"] and len(links) == 2
    again = _add(conn, ctx, ws.id, a.id, ("acme ltd", "company"))
    assert again == ([], [])
    nodes, links = _add(conn, ctx, ws.id, b.id, ("ACME LTD", "company"))
    assert nodes == [] and [(l.from_, l.to) for l in links] == [(b.id, links[0].to)]
    assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 2
    assert conn.execute("SELECT entity_type FROM entities WHERE label = '30 June'").fetchone()[0] == "other"
    assert len(events("context.extended")) == 2


def test_limits_and_fixed_id(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Text.")
    nodes, _ = _add(conn, ctx, ws.id, a.id, *[(f"Entity {i}", "other") for i in range(7)], ("x" * 80, "other"))
    assert len(nodes) == 5
    with transaction(conn):
        [node], _ = add_mentions(
            conn, ctx, workspace_id=ws.id, entities=[EntityOut(label="y" * 80, type="place", passage_id="p1")],
            passage_file=lambda _: a.id, question_id=None, entity_id="e-fixed",
        )  # fmt: skip
    assert node.id == "e-fixed" and len(node.label) == 60
    with pytest.raises(ValueError):
        add_mentions(
            conn, ctx, workspace_id=ws.id, entities=[], passage_file=lambda _: a.id, question_id=None, entity_id="e"
        )


def test_map_read(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    a = upload(ctx, ws.id, "a.txt", b"Acme signed.")
    b = upload(ctx, ws.id, "b.txt", b"Bolt paid.")
    _add(conn, ctx, ws.id, a.id, ("Acme", "company"))
    _add(conn, ctx, ws.id, b.id, ("Bolt", "company"))
    other = workspaces.create(ctx, CreateWorkspaceInput(name="Other"))
    c = upload(ctx, other.id, "c.txt", b"Elsewhere.")
    _add(conn, ctx, other.id, c.id, ("Zed", "company"))
    files.delete(ctx, DeleteFileInput(ws=ws.id, file_id=b.id))
    graph = contextmap.get(ctx, GetContextMapInput(ws=ws.id))
    assert [(n.label, n.kind) for n in graph.nodes] == [("a.txt", "file"), ("Acme", "entity")]
    assert [(l.from_, n.id) for l, n in zip(graph.links, graph.nodes[1:], strict=True)] == [(a.id, graph.links[0].to)]
