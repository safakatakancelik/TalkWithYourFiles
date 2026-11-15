"""Files, the entities they mention, and the links between them (05-retrieval-and-citations.md section 8)."""

import sqlite3
from collections.abc import Callable

from twyf.contract.models import MapLink, MapNode
from twyf.contract.turns import EntityOut
from twyf.db.repos import entities as repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

MAX_PER_TURN = 5


def add_mentions(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    *,
    workspace_id: str,
    entities: list[EntityOut],
    passage_file: Callable[[str], str],
    question_id: str | None,
    entity_id: str | None = None,
) -> tuple[list[MapNode], list[MapLink]]:
    """Finds or inserts each entity and links it to the file its passage belongs to. Returns only what is new.

    `entity_id` is the id to give a single new entity (seeding uses fixed ids). Outside a question, anything new
    is recorded as `context.extended` at once; inside one, the engine sends it all in one `context` event."""
    if entity_id is not None and len(entities) != 1:
        raise ValueError("entity_id names one entity")
    nodes: list[MapNode] = []
    links: list[MapLink] = []
    for entity in entities[:MAX_PER_TURN]:
        label = entity.label.strip()[: repo.MAX_LABEL]
        norm = repo.norm_label(label)
        if not norm:
            continue
        found = repo.find(conn, workspace_id, norm)
        if found is None:
            found = entity_id or new_id("e")
            kind = entity.type if entity.type in repo.ENTITY_TYPES else "other"
            repo.insert(conn, entity_id=found, workspace_id=workspace_id, label=label, norm=norm, entity_type=kind)
            nodes.append(MapNode(id=found, label=label, kind="entity"))
        file_id = passage_file(entity.passage_id)
        if repo.add_mention(
            conn, workspace_id=workspace_id, entity_id=found, file_id=file_id, created_by=ctx.actor_id,
            question_id=question_id,
        ):  # fmt: skip
            links.append(MapLink.model_validate({"from": file_id, "to": found}))
    if question_id is None and (nodes or links):
        record(
            conn, ctx, "context.extended", workspace_id=workspace_id,
            payload={"nodes": [n.id for n in nodes], "links": [[link.from_, link.to] for link in links]},
        )  # fmt: skip
    return nodes, links
