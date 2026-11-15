from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, TypeAdapter

from twyf.contract.base import Opt, Wire
from twyf.contract.models import Citation, Claim, MapLink, MapNode, Note, Unverified, Verdict


def _type_is_required(schema: dict[str, Any]) -> None:
    # `type` has a default so events are easy to build, but on the wire it is always present.
    schema["properties"]["type"].pop("default", None)
    required: list[str] = schema.setdefault("required", [])
    if "type" not in required:
        required.insert(0, "type")


class Event(Wire):
    model_config = ConfigDict(json_schema_extra=_type_is_required)


class StartedEvent(Event):
    type: Literal["started"] = "started"
    question_id: str


class StatusEvent(Event):
    type: Literal["status"] = "status"
    text: str


class BroadcastEvent(Event):
    type: Literal["broadcast"] = "broadcast"
    text: str
    to: list[str]


class JoinEvent(Event):
    type: Literal["join"] = "join"
    agent_id: str
    how: Literal["volunteered", "called"]


class AssignEvent(Event):
    type: Literal["assign"] = "assign"
    agent_id: str
    file_id: str


class ReadingEvent(Event):
    type: Literal["reading"] = "reading"
    agent_id: str


class NoteEvent(Event):
    type: Literal["note"] = "note"
    note: Note


class SayEvent(Event):
    type: Literal["say"] = "say"
    agent_id: str
    text: str
    citations: Opt[list[Citation]] = None


class VerifyEvent(Event):
    type: Literal["verify"] = "verify"
    round: int
    claims: list[Claim]
    citations: list[Citation]


class VerdictEvent(Event):
    type: Literal["verdict"] = "verdict"
    round: int
    passed: bool
    verdicts: list[Verdict]


class RehuddleEvent(Event):
    type: Literal["rehuddle"] = "rehuddle"
    round: int
    reason: str
    claim_ids: list[str]


class LeaveEvent(Event):
    type: Literal["leave"] = "leave"
    agent_ids: list[str]


class ContextEvent(Event):
    type: Literal["context"] = "context"
    nodes: list[MapNode]
    links: list[MapLink]


class AnswerEvent(Event):
    type: Literal["answer"] = "answer"
    text: str
    citations: list[Citation]
    placeholder: Opt[bool] = None
    unverified: Opt[list[Unverified]] = None


class ErrorEvent(Event):
    type: Literal["error"] = "error"
    code: str
    message: str


class CancelledEvent(Event):
    type: Literal["cancelled"] = "cancelled"


AgentEvent = Annotated[
    StartedEvent
    | StatusEvent
    | BroadcastEvent
    | JoinEvent
    | AssignEvent
    | ReadingEvent
    | NoteEvent
    | SayEvent
    | VerifyEvent
    | VerdictEvent
    | RehuddleEvent
    | LeaveEvent
    | ContextEvent
    | AnswerEvent
    | ErrorEvent
    | CancelledEvent,
    Field(discriminator="type"),
]

EVENT_MODELS: list[type[Event]] = [
    StartedEvent,
    StatusEvent,
    BroadcastEvent,
    JoinEvent,
    AssignEvent,
    ReadingEvent,
    NoteEvent,
    SayEvent,
    VerifyEvent,
    VerdictEvent,
    RehuddleEvent,
    LeaveEvent,
    ContextEvent,
    AnswerEvent,
    ErrorEvent,
    CancelledEvent,
]

agent_event_adapter: TypeAdapter[AgentEvent] = TypeAdapter(AgentEvent)


def parse_event(data: dict[str, Any]) -> AgentEvent:
    return agent_event_adapter.validate_python(data)
