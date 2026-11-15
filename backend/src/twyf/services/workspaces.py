from twyf.contract.models import Workspace
from twyf.contract.operations import (
    CreateWorkspaceInput,
    DeleteWorkspaceInput,
    ListWorkspacesInput,
    RenameWorkspaceInput,
)
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list(ctx: RequestContext, input: ListWorkspacesInput) -> list[Workspace]:
    raise ServiceError("internal", "not implemented")


def create(ctx: RequestContext, input: CreateWorkspaceInput) -> Workspace:
    raise ServiceError("internal", "not implemented")


def rename(ctx: RequestContext, input: RenameWorkspaceInput) -> Workspace:
    raise ServiceError("internal", "not implemented")


def delete(ctx: RequestContext, input: DeleteWorkspaceInput) -> None:
    raise ServiceError("internal", "not implemented")
