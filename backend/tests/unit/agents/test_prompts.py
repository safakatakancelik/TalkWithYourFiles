import sqlite3

from tests.conftest import REPO_ROOT
from twyf.agents.definitions import current_version, load_folder
from twyf.agents.prompts import render
from twyf.contract.models import Workspace
from twyf.contract.operations import CreateAgentInput
from twyf.db.repos import agents as agents_repo
from twyf.recording.context import RequestContext
from twyf.services import agents


def test_render_prompt(ws: Workspace, ctx: RequestContext, conn: sqlite3.Connection) -> None:
    rules = load_folder(REPO_ROOT / ".agents").rules
    created = agents.create(ctx, CreateAgentInput(ws=ws.id, name="Lawyer", specialty="contracts"))
    lawyer = agents_repo.get(conn, ws.id, created.id)
    assert lawyer is not None
    definition = current_version(conn, lawyer.definition_id)
    skills = {s.slug: s for s in definition.skills}
    system, instructions = render(lawyer, definition, "work", skills, rules=rules)
    assert system.startswith(rules.strip())
    assert definition.resolved_prompt.strip() in system
    assert system.endswith("Your name is Lawyer. Your speciality is contracts.")
    assert instructions.startswith(skills["cite-passages"].body.strip())
    assert skills["work-on-files"].body.strip() in instructions

    orchestrator = agents_repo.builtin(conn, ws.id, "orchestrator")
    o_definition = current_version(conn, orchestrator.definition_id)
    system, instructions = render(
        orchestrator, o_definition, "plan", {s.slug: s for s in o_definition.skills}, rules=rules
    )
    assert system.endswith("Your name is Orchestrator.")
    assert instructions == next(s for s in o_definition.skills if s.slug == "plan-huddle").body.strip()

    generic = agents_repo.list(conn, ws.id, "translator")[0]
    g_definition = current_version(conn, generic.definition_id)
    system, _ = render(generic, g_definition, "volunteer", {s.slug: s for s in g_definition.skills}, rules=rules)
    assert system.endswith("Your name is Translator.")
