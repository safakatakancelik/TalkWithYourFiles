from collections.abc import AsyncIterator

from twyf.contract.events import AgentEvent
from twyf.contract.operations import AskInput, CancelQuestionInput, GetQuestionEventsInput
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def ask(ctx: RequestContext, input: AskInput) -> AsyncIterator[AgentEvent]:
    raise ServiceError("internal", "not implemented")


def events(ctx: RequestContext, input: GetQuestionEventsInput) -> AsyncIterator[AgentEvent]:
    raise ServiceError("internal", "not implemented")


def cancel(ctx: RequestContext, input: CancelQuestionInput) -> None:
    raise ServiceError("internal", "not implemented")
