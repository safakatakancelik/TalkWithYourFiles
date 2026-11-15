from twyf.contract.models import ContextMap, MapLink, MapNode
from twyf.contract.operations import GetContextMapInput
from twyf.db.repos import entities
from twyf.db.repos import files as files_repo
from twyf.recording.context import RequestContext
from twyf.services import state
from twyf.services.workspaces import require


def get(ctx: RequestContext, input: GetContextMapInput) -> ContextMap:
    """Live files, entities with a mention in a live file, and their links."""
    with state.db() as conn:
        require(conn, input.ws)
        nodes = [MapNode(id=r["id"], label=r["name"], kind="file") for r in files_repo.list(conn, input.ws)]
        nodes += [MapNode(id=r["id"], label=r["label"], kind="entity") for r in entities.map_entities(conn, input.ws)]
        links = [
            MapLink.model_validate({"from": r["file_id"], "to": r["entity_id"]})
            for r in entities.map_links(conn, input.ws)
        ]
        return ContextMap(nodes=nodes, links=links)
