from typing import Any, Literal

from pydantic import Field

from twyf.contract.base import Opt, Wire

Weight = Literal["off", "low", "normal", "high"]
FileType = Literal["pdf", "docx", "csv", "md", "txt", "image", "other"]
FileStatus = Literal["processing", "ready", "unreadable", "missing", "changed"]
NoteKind = Literal["summary", "interpretation", "finding"]
VerdictKind = Literal["supported", "partly_supported", "unsupported", "mechanical_fail"]

ORCHESTRATOR = "orchestrator"
VERIFIER = "verifier"
USER = "user"


class Workspace(Wire):
    id: str
    name: str


class FileItem(Wire):
    id: str
    name: str
    type: FileType
    size_kb: int
    uploaded_at: str
    status: Opt[FileStatus] = None
    version: Opt[int] = None


class Agent(Wire):
    id: str
    name: str
    specialty: str


class Citation(Wire):
    n: int
    file_id: str
    agent_id: str
    location: str
    passage: str
    quote: str
    id: Opt[str] = None
    extraction_id: Opt[str] = None
    start: Opt[int] = None
    end: Opt[int] = None
    page: Opt[int] = None
    file_name: Opt[str] = None
    file_version: Opt[int] = None


class Note(Wire):
    id: str
    file_id: str
    author_id: str
    kind: NoteKind
    text: str
    citations: list[Citation]
    created_at: str
    weight: Weight
    author_name: Opt[str] = None
    file_version: Opt[int] = None


class Session(Wire):
    id: str
    title: str
    updated_at: str
    message_count: int


class Unverified(Wire):
    text: str
    reason: str


class ChatMsg(Wire):
    id: str
    role: Literal["user", "assistant"]
    text: str
    citations: Opt[list[Citation]] = None
    pending: Opt[bool] = None
    status: Opt[str] = None
    placeholder: Opt[bool] = None
    unverified: Opt[list[Unverified]] = None
    error: Opt[str] = None


class MapNode(Wire):
    id: str
    label: str
    kind: Literal["file", "entity"]


class MapLink(Wire):
    from_: str = Field(alias="from")
    to: str


class ContextMap(Wire):
    nodes: list[MapNode]
    links: list[MapLink]


class Claim(Wire):
    id: str
    text: str
    kind: Literal["quoted", "derived"]
    citations: list[int]
    derived_from: Opt[list[str]] = None
    calculation: Opt[str] = None


class Verdict(Wire):
    claim_id: str
    verdict: VerdictKind
    reason: str


class TranslatorReply(Wire):
    text: str
    citations: list[Citation]


class EventRecord(Wire):
    id: int
    occurred_at: str
    event_type: str
    actor_id: str
    source: str
    workspace_id: Opt[str] = None
    session_id: Opt[str] = None
    question_id: Opt[str] = None
    round_id: Opt[str] = None
    turn_id: Opt[str] = None
    cause_event_id: Opt[int] = None
    entity_type: Opt[str] = None
    entity_id: Opt[str] = None
    payload: dict[str, Any]


class ErrorInfo(Wire):
    code: str
    message: str
    details: Opt[dict[str, Any]] = None


class ErrorBody(Wire):
    error: ErrorInfo


class FileText(Wire):
    text: str
    start: int
    end: int
    total: int


class SubmitResult(Wire):
    accepted: bool
    errors: Opt[list[str]] = None


def dump(model: Wire) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)
