from twyf.contract.models import ContextMap
from twyf.contract.operations import GetContextMapInput
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def get(ctx: RequestContext, input: GetContextMapInput) -> ContextMap:
    raise ServiceError("internal", "not implemented")
