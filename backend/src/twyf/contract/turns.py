"""Input and output models of every agent turn (04-agents.md sections 3, 6, 8, 9 and 10)."""

from typing import Any, Literal

from pydantic import Field

from twyf.contract.base import Opt, Wire
from twyf.contract.models import FileType, Unverified

# Shared pieces


class PassageIn(Wire):
    passage_id: str
    file_id: str
    file_name: str
    location: str
    text: str


class CitationIn(Wire):
    citation_id: str
    n: int
    file_name: str
    location: str
    passage: str
    quote: str


class NoteIn(Wire):
    note_id: str
    file_name: str
    author: str
    kind: str
    weight: str
    text: str
    file_version: int
    earlier_version: bool  # true when written about a version that is no longer current


class Quote(Wire):
    # either passage_id + quote (a new citation) or citation_id (reuse one already made)
    passage_id: Opt[str] = None
    quote: Opt[str] = None
    citation_id: Opt[str] = None


class StatementOut(Wire):
    text: str
    quotes: list[Quote]  # at least one quote


class NoteOut(Wire):
    file_id: str
    kind: Literal["summary", "finding", "interpretation"]
    text: str
    quotes: list[Quote]


class EntityOut(Wire):
    label: str
    type: str
    passage_id: str


class Line(Wire):
    agent: str
    text: str
    citations: list[CitationIn]


class HistoryItem(Wire):
    role: Literal["user", "assistant"]
    text: str


class FileInfo(Wire):
    file_id: str
    name: str
    type: FileType
    notes: list[NoteIn]


class AgentInfo(Wire):
    agent_id: str
    name: str
    specialty: str
    note_count: int
    files_worked: list[str]


class DirectCall(Wire):
    agent_id: str
    file_ids: list[str]
    reason: str


class Volunteer(Wire):
    agent_id: str
    reason: str
    file_ids: list[str]


class AssignmentOut(Wire):
    agent_id: str
    file_ids: list[str]
    focus: str


class Feedback(Wire):
    claim_text: str
    reason: str


class SearchOut(Wire):
    file_id: str
    query: str


class FailedClaim(Wire):
    claim_text: str
    verdict: str
    reason: str


class Followup(Wire):
    agent_id: str
    focus: str
    file_ids: list[str]


class EarlierClaim(Wire):
    ref: str
    text: str
    verdict: str
    reason: str


class ClaimRef(Wire):
    claim_id: str
    text: str


class Usage(Wire):
    model: Opt[str] = None
    input_tokens: Opt[int] = None
    output_tokens: Opt[int] = None


# Turns


class TurnInput(Wire):
    previous_error: Opt[str] = None


class PlanInput(TurnInput):
    question: str
    history: list[HistoryItem]
    files: list[FileInfo]
    agents: list[AgentInfo]
    named_file_ids: list[str]
    named_agent_ids: list[str]


class PlanOutput(Wire):
    broadcast_text: str
    broadcast_to: list[str]
    direct_calls: list[DirectCall]


class VolunteerInput(TurnInput):
    question: str
    broadcast_text: str
    files: list[FileInfo]


class VolunteerOutput(Wire):
    volunteer: bool
    reason: str
    file_ids: list[str]


class AssignInput(TurnInput):
    question: str
    volunteers: list[Volunteer]
    direct_calls: list[DirectCall]
    files: list[FileInfo]
    agents: list[AgentInfo]
    named_file_ids: list[str]


class AssignOutput(Wire):
    assignments: list[AssignmentOut]


class WorkInput(TurnInput):
    question: str
    focus: str
    passages: list[PassageIn]
    notes: list[NoteIn]
    transcript: list[Line]
    feedback: list[Feedback]
    searches_left: int


class WorkOutput(Wire):
    statements: list[StatementOut]
    notes: list[NoteOut]
    entities: list[EntityOut]
    searches: list[SearchOut]


class ReviewInput(TurnInput):
    question: str
    transcript: list[Line]
    members: list[str]
    agents: list[AgentInfo]
    files: list[FileInfo]
    failed: list[FailedClaim]
    steps_left: int


class ReviewOutput(Wire):
    decision: Literal["continue", "settle"]
    say: str
    followups: list[Followup]


class ClaimOut(Wire):
    ref: str  # a label unique in this output: "k1"
    text: str  # one sentence, one fact
    kind: Literal["quoted", "derived"]
    citation_ids: list[str] = Field(default_factory=list)  # quoted claims: at least one
    derived_from: list[str] = Field(
        default_factory=list
    )  # derived claims: refs of other claims in this output, at least one
    expression: Opt[str] = None  # derived claims with arithmetic: "1 - (13.05 + 7.60 * 0.08) / 29.00"
    stated_result: Opt[float] = None  # 0.529


class DraftClaimsInput(TurnInput):
    question: str
    transcript: list[Line]
    earlier: list[EarlierClaim]


class DraftClaimsOutput(Wire):
    claims: list[ClaimOut]


class ClaimIn(Wire):
    claim_id: str
    text: str
    kind: Literal["quoted", "derived"]
    citations: list[CitationIn]  # every citation the claim rests on, with passage and quote
    inputs: list[ClaimRef]  # derived: the claims it is derived from
    expression: Opt[str] = None
    computed_result: Opt[float] = None


class CitationVerdictOut(Wire):
    citation_id: str
    supports: Literal["full", "partial", "none"]


class VerdictOut(Wire):
    claim_id: str
    verdict: Literal["supported", "partly_supported", "unsupported"]
    reason: str  # one or two sentences. Required for every verdict
    citations: list[CitationVerdictOut]


class VerifyInput(TurnInput):
    claims: list[ClaimIn]


class VerifyOutput(Wire):
    verdicts: list[VerdictOut]


class Segment(Wire):
    text: str
    claim_ids: list[str] = Field(default_factory=list)
    new_paragraph: bool = False


class WriteAnswerInput(TurnInput):
    question: str
    history: list[HistoryItem]
    mode: Literal["full", "partial", "nothing_found", "no_files"]
    claims: list[ClaimRef]
    unverified: list[Unverified]


class WriteAnswerOutput(Wire):
    segments: list[Segment]


class DirectReplyInput(TurnInput):
    question: str
    passages: list[PassageIn]
    notes: list[NoteIn]
    searches_left: int


class DirectReplyOutput(Wire):
    statements: list[StatementOut]
    notes: list[NoteOut]
    searches: list[SearchOut]


class FirstReadInput(TurnInput):
    file_name: str
    passages: list[PassageIn]
    chunks_shown: int
    chunks_total: int


class FirstReadOutput(Wire):
    summary: NoteOut
    entities: list[EntityOut]


class DescribeImageInput(TurnInput):
    file_name: str  # the image itself goes as an attachment


class DescribeImageOutput(Wire):
    description: str


class TurnOffer(Wire):
    turn_id: str
    lease_token: str
    turn_type: str
    agent_name: str
    agent_kind: str
    system_prompt: str
    instructions: str
    input: dict[str, Any]
    output_schema: dict[str, Any]
    expires_at: str


TURN_MODELS: dict[str, tuple[type[Wire], type[Wire], list[str]]] = {
    "plan": (PlanInput, PlanOutput, ["plan-huddle"]),
    "volunteer": (VolunteerInput, VolunteerOutput, ["volunteer"]),
    "assign": (AssignInput, AssignOutput, ["assign-files"]),
    "work": (WorkInput, WorkOutput, ["work-on-files", "cite-passages"]),
    "review": (ReviewInput, ReviewOutput, ["review-huddle"]),
    "draft_claims": (DraftClaimsInput, DraftClaimsOutput, ["draft-claims"]),
    "verify": (VerifyInput, VerifyOutput, ["verify-claims"]),
    "write_answer": (WriteAnswerInput, WriteAnswerOutput, ["write-answer"]),
    "direct_reply": (DirectReplyInput, DirectReplyOutput, ["direct-reply", "cite-passages"]),
    "first_read": (FirstReadInput, FirstReadOutput, ["first-read", "cite-passages"]),
    "describe_image": (DescribeImageInput, DescribeImageOutput, ["describe-image"]),
}
