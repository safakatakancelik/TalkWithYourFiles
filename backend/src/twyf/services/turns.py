from twyf.contract.models import SubmitResult
from twyf.contract.operations import ClaimTurnInput, FailTurnInput, SubmitTurnInput
from twyf.contract.turns import TurnOffer
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


async def claim(ctx: RequestContext, input: ClaimTurnInput) -> TurnOffer | None:
    raise ServiceError("internal", "not implemented")


def submit(ctx: RequestContext, input: SubmitTurnInput) -> SubmitResult:
    raise ServiceError("internal", "not implemented")


def fail(ctx: RequestContext, input: FailTurnInput) -> None:
    raise ServiceError("internal", "not implemented")
