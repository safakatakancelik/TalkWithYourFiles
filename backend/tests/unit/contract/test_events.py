import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from twyf.contract.events import EVENT_MODELS, StatusEvent, agent_event_adapter, parse_event
from twyf.contract.models import dump

SAMPLES: dict[str, dict[str, Any]] = json.loads((Path(__file__).parents[2] / "fixtures" / "samples.json").read_text())[
    "events"
]


def test_agent_event_union() -> None:
    assert len(SAMPLES) == 16
    assert {m.model_fields["type"].default for m in EVENT_MODELS} == set(SAMPLES)
    for name, sample in SAMPLES.items():
        event = parse_event(sample)
        assert event.type == name
        assert dump(event) == sample
    with pytest.raises(ValidationError):
        parse_event({"type": "shout", "text": "hi"})


def test_event_type_required_on_the_wire() -> None:
    schema = agent_event_adapter.json_schema(mode="serialization", by_alias=True)
    status = schema["$defs"]["StatusEvent"]
    assert status["required"][0] == "type"
    assert "default" not in status["properties"]["type"]
    assert dump(StatusEvent(text="x")) == {"type": "status", "text": "x"}
