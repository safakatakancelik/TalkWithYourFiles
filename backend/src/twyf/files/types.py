from pathlib import PurePath

from twyf.contract.models import FileType

_BY_EXTENSION: dict[str, FileType] = {
    "pdf": "pdf",
    "docx": "docx",
    "csv": "csv",
    "md": "md",
    "txt": "txt",
    **dict.fromkeys(["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"], "image"),
}


def file_type(name: str) -> FileType:
    """Decided from the extension only. The name is never used as a path."""
    return _BY_EXTENSION.get(PurePath(name).suffix.lower().removeprefix("."), "other")
