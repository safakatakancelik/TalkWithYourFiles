from twyf.contract.models import FileItem, FileText
from twyf.contract.operations import (
    AddFileVersionInput,
    DeleteFileInput,
    GetFileTextInput,
    ListFilesInput,
    UploadFileInput,
)
from twyf.recording.context import RequestContext
from twyf.services.errors import ServiceError


def list(ctx: RequestContext, input: ListFilesInput) -> list[FileItem]:
    raise ServiceError("internal", "not implemented")


def upload(ctx: RequestContext, input: UploadFileInput) -> FileItem:
    raise ServiceError("internal", "not implemented")


def add_version(ctx: RequestContext, input: AddFileVersionInput) -> FileItem:
    raise ServiceError("internal", "not implemented")


def delete(ctx: RequestContext, input: DeleteFileInput) -> None:
    raise ServiceError("internal", "not implemented")


def get_text(ctx: RequestContext, input: GetFileTextInput) -> FileText:
    raise ServiceError("internal", "not implemented")
