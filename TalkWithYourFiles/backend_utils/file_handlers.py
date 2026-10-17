import io
from abc import ABC, abstractmethod

from docx import Document
from pypdf import PdfReader


"""
In this module the factory pattern is used to make this functionalities more flexible & maintainable.
Currently there are four main file handlers for PDF, DOCX, CSV, TXT.

Handlers receive the raw bytes of a file, so they don't depend on the GUI framework.

To extend these file types:
1) Create a new subclass of FileHandler in this file.
2) Implement the read_file method: define the logic to process the bytes and return the extracted text
3) Register the file extension in FileHandlerFactory.HANDLERS.

"""


class FileHandler(ABC):
    """Abstract base class for file handlers."""

    @abstractmethod
    def read_file(self, data: bytes) -> str:
        """Extract the text from the file's bytes. Returns "" if nothing could be read."""


class PDFHandler(FileHandler):
    def read_file(self, data: bytes) -> str:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)


class DocxHandler(FileHandler):
    def read_file(self, data: bytes) -> str:
        doc = Document(io.BytesIO(data))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)


class TxtHandler(FileHandler):
    """Plain text; also used for CSV, which LLMs read fine as text."""

    def read_file(self, data: bytes) -> str:
        return data.decode("utf-8", errors="replace")


class FileHandlerFactory:
    """Factory for creating file handlers based on the file extension."""

    HANDLERS = {
        "pdf": PDFHandler,
        "docx": DocxHandler,
        "txt": TxtHandler,
        "csv": TxtHandler,
    }

    @classmethod
    def supported_extensions(cls):
        return list(cls.HANDLERS)

    @classmethod
    def get_file_handler(cls, file_name: str) -> FileHandler:
        extension = file_name.rsplit(".", 1)[-1].lower()
        if extension not in cls.HANDLERS:
            raise ValueError(f"Unsupported file type: .{extension}")
        return cls.HANDLERS[extension]()
