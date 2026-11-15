from twyf.contract.models import EventRecord
from twyf.contract.operations import ListEventsInput
from twyf.db.repos import events as events_repo
from twyf.recording.context import RequestContext
from twyf.services import state


def list_events(ctx: RequestContext, input: ListEventsInput) -> list[EventRecord]:
    with state.db() as conn:
        return events_repo.list(
            conn,
            workspace_id=input.workspace,
            question_id=input.question,
            event_type=input.type,
            after=input.after,
            limit=input.limit,
        )
