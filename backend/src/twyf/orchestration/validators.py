"""The validation rules after every turn (04-agents.md section 3). Each returns a list of error texts."""

from collections.abc import Callable
from typing import Any, cast

from twyf.contract.base import Wire
from twyf.contract.turns import (
    AssignOutput,
    DirectReplyOutput,
    FirstReadOutput,
    NoteOut,
    PlanOutput,
    Quote,
    ReviewOutput,
    StatementOut,
    VerifyInput,
    VerifyOutput,
    WorkOutput,
)

ID_KEYS = {"agent_id", "file_id", "passage_id", "citation_id", "claim_id"}
ID_LISTS = {"agent_ids", "file_ids", "claim_ids", "broadcast_to"}


def _strings(node: Any) -> set[str]:
    if isinstance(node, str):
        return {node}
    if isinstance(node, dict):
        return set[str]().union(*(_strings(v) for v in cast(dict[str, Any], node).values()))
    if isinstance(node, list):
        return set[str]().union(*(_strings(v) for v in cast(list[Any], node)))
    return set()


def _output_ids(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in cast(dict[str, Any], node).items():
            if key in ID_KEYS and isinstance(value, str):
                found.append(value)
            elif key in ID_LISTS and isinstance(value, list):
                found += [v for v in cast(list[Any], value) if isinstance(v, str)]
            else:
                found += _output_ids(value)
    elif isinstance(node, list):
        for value in cast(list[Any], node):
            found += _output_ids(value)
    return found


def unknown_ids(output: Wire, input: Wire) -> list[str]:
    """Rule for all turns: every id in the output was present in the input."""
    known = _strings(input.model_dump(mode="json"))
    return [
        f"{i} is not in the input" for i in dict.fromkeys(_output_ids(output.model_dump(mode="json"))) if i not in known
    ]


def plan(output: PlanOutput, translators: set[str], named_agents: list[str]) -> list[str]:
    errors = [f"{a} is not a translator" for a in output.broadcast_to if a not in translators]
    errors += [f"{c.agent_id} is not a translator" for c in output.direct_calls if c.agent_id not in translators]
    reached = set(output.broadcast_to) | {c.agent_id for c in output.direct_calls}
    errors += [f"the user named {a}: it must be asked or called" for a in named_agents if a not in reached]
    return errors


def assign(output: AssignOutput, translators: set[str], named_files: list[str]) -> list[str]:
    errors = [f"{a.agent_id} is not a translator" for a in output.assignments if a.agent_id not in translators]
    assigned = {f for a in output.assignments for f in a.file_ids}
    errors += [f"the user named file {f}: it must be assigned" for f in named_files if f not in assigned]
    return errors


type QuoteCheck = Callable[[Quote, str | None], str | None]
"""(quote, the file the quote must come from or None) -> an error text or None."""


def _quotes(statements: list[StatementOut], notes: list[NoteOut], check: QuoteCheck) -> list[str]:
    errors: list[str] = []
    for i, statement in enumerate(statements, start=1):
        if not statement.quotes:
            errors.append(f"statement {i} needs at least one quote")
        errors += [e for q in statement.quotes if (e := check(q, None))]
    for i, note in enumerate(notes, start=1):
        if note.kind in ("summary", "finding") and not note.quotes:
            errors.append(f"note {i} is a {note.kind} and needs at least one quote")
        errors += [e for q in note.quotes if (e := check(q, note.file_id))]
    return errors


def work(output: WorkOutput | DirectReplyOutput, searches_left: int, check: QuoteCheck) -> list[str]:
    errors = _quotes(output.statements, output.notes, check)
    if output.searches and searches_left <= 0:
        errors.append("searches must be empty when searchesLeft is 0")
    return errors


def first_read(output: FirstReadOutput, check: QuoteCheck) -> list[str]:
    return _quotes([], [output.summary], check)


def review(output: ReviewOutput, steps_left: int, members: set[str], translators: set[str]) -> list[str]:
    errors: list[str] = []
    if output.followups and (output.decision == "settle" or steps_left <= 0):
        errors.append("followups must be empty when the decision is settle or stepsLeft is 0")
    for f in output.followups:
        if f.agent_id not in translators:
            errors.append(f"{f.agent_id} is not a translator")
        elif f.agent_id not in members and not f.file_ids:
            errors.append(f"a follow-up to {f.agent_id}, who is not in the huddle, needs fileIds")
    return errors


def verify(output: VerifyOutput, input: VerifyInput) -> list[str]:
    errors: list[str] = []
    expected = {c.claim_id: {x.citation_id for x in c.citations} for c in input.claims}
    given = [v.claim_id for v in output.verdicts]
    if sorted(given) != sorted(expected):
        errors.append("there must be exactly one verdict per input claim")
    for v in output.verdicts:
        if v.claim_id in expected and {c.citation_id for c in v.citations} != expected[v.claim_id]:
            errors.append(f"the verdict on {v.claim_id} needs one entry per citation of that claim")
    return errors
