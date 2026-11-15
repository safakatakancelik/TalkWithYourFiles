"""The mechanical parts of verification and answer writing (04-agents.md sections 8, 9.3 and 10)."""

import hashlib
import re
import sqlite3

from twyf.contract.turns import ClaimOut, ClaimRef, Segment
from twyf.db.repos import claims as repo
from twyf.db.repos.claims import ClaimRow
from twyf.ids import new_id
from twyf.orchestration.arithmetic import ArithmeticRejected, evaluate, within_tolerance
from twyf.recording.context import RequestContext
from twyf.recording.recorder import record

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_FINAL_PUNCTUATION = ".!?,;:"


def validate_claims(claims: list[ClaimOut], known_citation_ids: set[str]) -> list[str]:
    """Rules 1 and 2: quoted claims cite known citations; derived claims stand on existing refs, with no cycle."""
    errors: list[str] = []
    refs = [c.ref for c in claims]
    by_ref = {c.ref: c for c in claims}
    if len(set(refs)) != len(refs):
        errors.append("every claim ref must be unique in the output")
    for claim in claims:
        if claim.kind == "quoted":
            if not claim.citation_ids:
                errors.append(f"quoted claim {claim.ref} needs at least one citation")
            errors += [
                f"claim {claim.ref} cites {cid}, which is not a citation of this question into a current file version"
                for cid in claim.citation_ids
                if cid not in known_citation_ids
            ]
        else:
            if not claim.derived_from:
                errors.append(f"derived claim {claim.ref} needs at least one derived_from ref")
            errors += [f"claim {claim.ref} derives from unknown ref {r}" for r in claim.derived_from if r not in by_ref]
    errors += [f"claim {ref} is part of a cycle" for ref in _cycles(by_ref)]
    return errors


def _cycles(by_ref: dict[str, ClaimOut]) -> list[str]:
    cyclic: list[str] = []
    for start in by_ref:
        stack, seen = [start], set[str]()
        while stack:
            ref = stack.pop()
            for nxt in by_ref[ref].derived_from if ref in by_ref else []:
                if nxt == start:
                    cyclic.append(start)
                    stack = []
                    break
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return cyclic


def _sha(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def store_claims(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    *,
    question_id: str,
    round_id: str,
    turn_id: str,
    claims: list[ClaimOut],
) -> list[ClaimRow]:
    """Stores validated claims inside the caller's transaction, in an order where inputs come first.

    Computes each derived claim's citations (the union of its inputs'), its computed result, its content hash,
    and the verdict carried from an identical claim verified earlier in this question."""
    workspace_id = conn.execute("SELECT workspace_id FROM questions WHERE id = ?", (question_id,)).fetchone()[0]
    by_ref = {c.ref: c for c in claims}
    rows: dict[str, ClaimRow] = {}

    def build(ref: str) -> ClaimRow:
        if ref in rows:
            return rows[ref]
        claim = by_ref[ref]
        inputs = [build(r) for r in claim.derived_from]
        if claim.kind == "quoted":
            cited = tuple(dict.fromkeys(claim.citation_ids))
        else:
            cited = tuple(dict.fromkeys(c for i in inputs for c in i.citation_ids))
        computed, error = None, None
        if claim.expression is not None:
            try:
                computed = evaluate(claim.expression)
                if claim.stated_result is None or not within_tolerance(computed, claim.stated_result):
                    error = f"the expression gives {computed:.4f}, not the stated {claim.stated_result}"
            except ArithmeticRejected as rejected:
                error = str(rejected)
        sha = _sha(
            claim.text, claim.kind, *sorted(cited), *sorted(i.content_sha256 for i in inputs), claim.expression or ""
        )
        row = ClaimRow(
            id=new_id("k"), ref=ref, ordinal=len(rows), kind=claim.kind, text=claim.text, expression=claim.expression,
            stated_result=claim.stated_result, computed_result=computed, arithmetic_error=error, content_sha256=sha,
            citation_ids=cited, input_ids=tuple(i.id for i in inputs), carried=repo.latest_verdict(conn, question_id, sha),
        )  # fmt: skip
        rows[ref] = row
        repo.insert(
            conn, workspace_id=workspace_id, question_id=question_id, round_id=round_id, turn_id=turn_id, row=row
        )
        return row

    for claim in claims:
        build(claim.ref)
    stored = sorted(rows.values(), key=lambda r: r.ordinal)
    record(
        conn, ctx, "claims.drafted", workspace_id=workspace_id, question_id=question_id, round_id=round_id,
        turn_id=turn_id, payload={"claims": [{"id": r.id, "ref": r.ref, "kind": r.kind, "text": r.text} for r in stored]},
    )  # fmt: skip
    return stored


def passes(verdicts: list[str]) -> bool:
    """A verification passes only when every claim is `supported`."""
    return all(v == "supported" for v in verdicts)


def _numbers(text: str) -> set[float]:
    return {float(m.replace(",", "")) for m in _NUMBER.findall(text)}


def validate_segments(segments: list[Segment], verified: dict[str, str], mode: str) -> list[str]:
    """The four rules of 04-agents.md section 10. `verified` maps claim id to claim text."""
    errors: list[str] = []
    for i, segment in enumerate(segments, start=1):
        unknown = [c for c in segment.claim_ids if c not in verified]
        errors += [f"segment {i} names {c}, which is not a verified claim" for c in unknown]
        if not segment.claim_ids:
            if any(ch.isdigit() for ch in segment.text):
                errors.append(f"segment {i} has no claims, so it may not contain digits")
            continue
        allowed = set[float]().union(*(_numbers(verified[c]) for c in segment.claim_ids if c in verified))
        errors += [
            f"segment {i} writes {n:g}, which is in none of its claims"
            for n in sorted(_numbers(segment.text) - allowed)
        ]
    if mode not in ("no_files", "nothing_found") and not any(s.claim_ids for s in segments):
        errors.append("at least one segment must state a claim")
    return errors


def assemble_answer(segments: list[Segment], claim_citations: dict[str, list[str]]) -> tuple[str, list[str]]:
    """The answer text with citation markers, and the citation ids in marker order (numbered from 1)."""
    order: list[str] = []
    text = ""
    for i, segment in enumerate(segments):
        cited = [c for claim_id in segment.claim_ids for c in claim_citations.get(claim_id, [])]
        for c in cited:
            if c not in order:
                order.append(c)
        piece = segment.text.strip()
        if cited:
            markers = " " + "".join(f"[{n}]" for n in sorted({order.index(c) + 1 for c in cited}))
            if piece and piece[-1] in _FINAL_PUNCTUATION:
                piece = piece[:-1] + markers + piece[-1]
            else:
                piece += markers
        if i:
            text += "\n\n" if segment.new_paragraph else " "
        text += piece
    return text, order


def fallback_answer(claims: list[ClaimRef], claim_citations: dict[str, list[str]]) -> tuple[str, list[str]]:
    """The verified claims as sentences with markers, for when the chat agent fails every attempt."""
    return assemble_answer([Segment(text=c.text, claim_ids=[c.claim_id]) for c in claims], claim_citations)
