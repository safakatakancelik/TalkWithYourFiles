import builtins

from twyf.contract.models import ChatMsg, Session
from twyf.contract.operations import (
    CreateSessionInput,
    DeleteSessionInput,
    GetMessagesInput,
    ListSessionsInput,
    RenameSessionInput,
)
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list(ctx: RequestContext, input: ListSessionsInput) -> list[Session]:
    raise ServiceError("internal", "not implemented")


def create(ctx: RequestContext, input: CreateSessionInput) -> Session:
    raise ServiceError("internal", "not implemented")


def rename(ctx: RequestContext, input: RenameSessionInput) -> Session:
    raise ServiceError("internal", "not implemented")


def delete(ctx: RequestContext, input: DeleteSessionInput) -> None:
    raise ServiceError("internal", "not implemented")


def messages(ctx: RequestContext, input: GetMessagesInput) -> builtins.list[ChatMsg]:
    raise ServiceError("internal", "not implemented")
