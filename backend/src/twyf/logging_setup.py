"""Logs: one JSON object per line, to stderr and logs/twyf.log, with request_id and, when present, question and turn."""

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

from twyf.config import Settings

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
question_id: ContextVar[str | None] = ContextVar("question_id", default=None)
turn_id: ContextVar[str | None] = ContextVar("turn_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
        }
        for name, var in (("question_id", question_id), ("turn_id", turn_id)):
            if (value := var.get()) is not None:
                line[name] = value
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line)


def setup_logging(settings: Settings) -> None:
    """Replaces the root logger's handlers with the two JSON handlers."""
    folder = settings.data_dir / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "twyf", False):
            root.removeHandler(handler)
    for handler in (logging.StreamHandler(sys.stderr), logging.FileHandler(folder / "twyf.log")):
        handler.setFormatter(formatter)
        handler.twyf = True  # pyright: ignore[reportAttributeAccessIssue] -- marks the handlers this module added
        root.addHandler(handler)
    root.setLevel(logging.INFO)
