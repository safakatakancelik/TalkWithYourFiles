from twyf.contract.models import Note
from twyf.contract.operations import AddNoteInput, DeleteNoteInput, EditNoteInput, ListNotesInput, SetNoteWeightInput
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list(ctx: RequestContext, input: ListNotesInput) -> list[Note]:
    raise ServiceError("internal", "not implemented")


def add(ctx: RequestContext, input: AddNoteInput) -> Note:
    raise ServiceError("internal", "not implemented")


def edit(ctx: RequestContext, input: EditNoteInput) -> Note:
    raise ServiceError("internal", "not implemented")


def delete(ctx: RequestContext, input: DeleteNoteInput) -> None:
    raise ServiceError("internal", "not implemented")


def set_weight(ctx: RequestContext, input: SetNoteWeightInput) -> None:
    raise ServiceError("internal", "not implemented")
