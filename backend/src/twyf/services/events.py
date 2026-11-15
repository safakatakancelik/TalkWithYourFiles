from twyf.contract.models import EventRecord
from twyf.contract.operations import ListEventsInput
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list_events(ctx: RequestContext, input: ListEventsInput) -> list[EventRecord]:
    raise ServiceError("internal", "not implemented")
