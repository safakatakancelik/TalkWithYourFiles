"""The door for a harness that does agent work through the queue runtime."""

from twyf.contract.models import SubmitResult
from twyf.contract.operations import ClaimTurnInput, FailTurnInput, SubmitTurnInput
from twyf.contract.turns import TurnOffer
from twyf.recording.context import RequestContext
from twyf.runtime.queue import QueueRuntime
from twyf.services import state
from twyf.services.errors import ServiceError, require_text


def _queue() -> QueueRuntime | None:
    runtime = state.engine().runner.runtime
    return runtime if isinstance(runtime, QueueRuntime) else None


async def claim(ctx: RequestContext, input: ClaimTurnInput) -> TurnOffer | None:
    """The oldest queued turn, waiting up to `wait_s` seconds. Nothing when the server runs another runtime."""
    worker = require_text(input.worker, "worker")
    queue = _queue()
    return await queue.claim(ctx, worker, input.wait_s) if queue is not None else None


async def submit(ctx: RequestContext, input: SubmitTurnInput) -> SubmitResult:
    queue = _queue()
    if queue is None:
        raise ServiceError("conflict", "The server does not run the queue runtime")
    return await queue.submit(input.turn_id, input.lease_token, input.output, input.usage)


async def fail(ctx: RequestContext, input: FailTurnInput) -> None:
    queue = _queue()
    if queue is None:
        raise ServiceError("conflict", "The server does not run the queue runtime")
    await queue.fail(input.turn_id, input.lease_token, require_text(input.reason, "reason"))
