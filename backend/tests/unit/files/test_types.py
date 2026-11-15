import pytest

from twyf.files.types import file_type


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.pdf", "pdf"), ("a.DOCX", "docx"), ("a.csv", "csv"), ("notes.md", "md"), ("a.txt", "txt"),
        *[(f"pic.{ext}", "image") for ext in ["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"]],
        ("a.xlsx", "other"), ("noext", "other"), ("../../etc/passwd.txt", "txt"), ("archive.tar.gz", "other"),
    ],
)  # fmt: skip
def test_file_type_from_extension(name: str, expected: str) -> None:
    assert file_type(name) == expected
