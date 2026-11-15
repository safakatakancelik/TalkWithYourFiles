from typing import Any

import pytest
from pydantic import ValidationError

from twyf.contract.base import Wire
from twyf.contract.turns import TURN_MODELS

CITATION_IN = {"citationId": "c_1", "n": 1, "fileName": "a.pdf", "location": "Page 1", "passage": "p", "quote": "q"}
NOTE_OUT = {"fileId": "f_1", "kind": "summary", "text": "Says x.", "quotes": [{"passageId": "p_1", "quote": "x"}]}

OUTPUT_SAMPLES: dict[str, dict[str, Any]] = {
    "plan": {
        "broadcastText": "Who can read the lease?",
        "broadcastTo": ["a_1"],
        "directCalls": [{"agentId": "a_2", "fileIds": ["f_1"], "reason": "Named"}],
    },
    "volunteer": {"volunteer": True, "reason": "I read leases.", "fileIds": ["f_1"]},
    "assign": {"assignments": [{"agentId": "a_1", "fileIds": ["f_1"], "focus": "End date"}]},
    "work": {
        "statements": [{"text": "It ends in 2029.", "quotes": [{"passageId": "p_1", "quote": "30 June 2029"}]}],
        "notes": [NOTE_OUT],
        "entities": [{"label": "Acme", "type": "company", "passageId": "p_1"}],
        "searches": [{"fileId": "f_1", "query": "break clause"}],
    },
    "review": {
        "decision": "continue",
        "say": "Check the break clause.",
        "followups": [{"agentId": "a_1", "focus": "break", "fileIds": []}],
    },
    "draft_claims": {
        "claims": [
            {"ref": "k1", "text": "Price is 29.00.", "kind": "quoted", "citationIds": ["c_1"]},
            {
                "ref": "k2",
                "text": "Margin is 52.9%.",
                "kind": "derived",
                "derivedFrom": ["k1"],
                "expression": "1 - 13.66 / 29.00",
                "statedResult": 0.529,
            },
        ]
    },
    "verify": {
        "verdicts": [
            {
                "claimId": "k_1",
                "verdict": "supported",
                "reason": "Stated.",
                "citations": [{"citationId": "c_1", "supports": "full"}],
            }
        ]
    },
    "write_answer": {
        "segments": [{"text": "Price is 29.00.", "claimIds": ["k_1"], "newParagraph": False}, {"text": "That is all."}]
    },
    "direct_reply": {
        "statements": [{"text": "It ends in 2029.", "quotes": [{"citationId": "c_1"}]}],
        "notes": [],
        "searches": [],
    },
    "first_read": {"summary": NOTE_OUT, "entities": []},
    "describe_image": {"description": "A chart of sales by month."},
}


def test_every_turn_type_has_models_and_skills() -> None:
    assert set(TURN_MODELS) == set(OUTPUT_SAMPLES)
    for input_model, output_model, skills in TURN_MODELS.values():
        assert issubclass(input_model, Wire) and issubclass(output_model, Wire)
        assert skills
        assert "previous_error" in input_model.model_fields


@pytest.mark.parametrize("turn_type", sorted(OUTPUT_SAMPLES))
def test_turn_output_validates_sample(turn_type: str) -> None:
    output_model = TURN_MODELS[turn_type][1]
    output_model.model_validate(OUTPUT_SAMPLES[turn_type])


@pytest.mark.parametrize("turn_type", sorted(OUTPUT_SAMPLES))
def test_turn_output_rejects_extra_field(turn_type: str) -> None:
    output_model = TURN_MODELS[turn_type][1]
    with pytest.raises(ValidationError):
        output_model.model_validate({**OUTPUT_SAMPLES[turn_type], "extra": 1})


def test_verify_input_carries_citations() -> None:
    verify_input = TURN_MODELS["verify"][0].model_validate(
        {"claims": [{"claimId": "k_1", "text": "t", "kind": "quoted", "citations": [CITATION_IN], "inputs": []}]}
    )
    assert verify_input.model_dump()["claims"][0]["citations"][0]["citation_id"] == "c_1"
