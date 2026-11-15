from collections.abc import AsyncIterator

from twyf.agents.definitions import sync, sync_config
from twyf.contract.events import AgentEvent, StartedEvent
from twyf.contract.operations import AskInput, CancelQuestionInput, GetQuestionEventsInput
from twyf.db.connection import transaction
from twyf.db.repos import questions as repo
from twyf.ids import new_id
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record
from twyf.services import state
from twyf.services.errors import ServiceError, require_text
from twyf.services.sessions import add_message, live
from twyf.services.workspaces import require


def start(ctx: RequestContext, input: AskInput) -> str:
    """Validates, rejects a busy session, stores the user message and the question, records question.asked."""
    text = require_text(input.question, "question")
    settings = state.settings()
    with state.db() as conn, transaction(conn):
        require(conn, input.ws)
        live(conn, input.ws, input.session_id)
        if repo.running_in_session(conn, input.session_id) is not None:
            raise ServiceError(
                "conflict", "This session already has a running question", {"session_id": input.session_id}
            )
        system = ctx.as_actor("system", "internal")
        sync(conn, system, settings)
        config_id = sync_config(conn, system, settings)
        question_id = new_id("q")
        repo.insert(
            conn, question_id=question_id, workspace_id=input.ws, session_id=input.session_id,
            max_rounds=settings.max_verify_rounds, config_version_id=config_id, runtime=settings.runtime,
        )  # fmt: skip
        add_message(conn, ctx, workspace_id=input.ws, session_id=input.session_id, role="user", text=text,
                    question_id=question_id)  # fmt: skip
        record(
            conn, ctx, "question.asked", workspace_id=input.ws, session_id=input.session_id, question_id=question_id,
            entity_type="question", entity_id=question_id, payload={"question": text},
            wire=StartedEvent(question_id=question_id), config_version_id=config_id,
        )  # fmt: skip
        return question_id


def ask(ctx: RequestContext, input: AskInput) -> AsyncIterator[AgentEvent]:
    raise ServiceError("internal", "not implemented")


def events(ctx: RequestContext, input: GetQuestionEventsInput) -> AsyncIterator[AgentEvent]:
    raise ServiceError("internal", "not implemented")


def cancel(ctx: RequestContext, input: CancelQuestionInput) -> None:
    raise ServiceError("internal", "not implemented")
