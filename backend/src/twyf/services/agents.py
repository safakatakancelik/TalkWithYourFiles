from twyf.contract.models import Agent, TranslatorReply
from twyf.contract.operations import (
    AskTranslatorInput,
    CreateAgentInput,
    DeleteAgentInput,
    ListAgentsInput,
    RenameAgentInput,
)
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list(ctx: RequestContext, input: ListAgentsInput) -> list[Agent]:
    raise ServiceError("internal", "not implemented")


def create(ctx: RequestContext, input: CreateAgentInput) -> Agent:
    raise ServiceError("internal", "not implemented")


def rename(ctx: RequestContext, input: RenameAgentInput) -> Agent:
    raise ServiceError("internal", "not implemented")


def delete(ctx: RequestContext, input: DeleteAgentInput) -> None:
    raise ServiceError("internal", "not implemented")


async def ask_translator(ctx: RequestContext, input: AskTranslatorInput) -> TranslatorReply:
    raise ServiceError("internal", "not implemented")
