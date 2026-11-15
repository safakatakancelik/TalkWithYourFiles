import json
from pathlib import Path
from typing import Any

import pytest

from twyf.runtime.base import RuntimeError_, TurnRequest
from twyf.runtime.fake import FakeRuntime, ScriptStep


def _request(turn_type: str = "work", agent: str = "Translator 1", **input: Any) -> TurnRequest:
    return TurnRequest(
        turn_id="t_1", turn_type=turn_type, agent_name=agent, agent_kind="translator", system_prompt="s",
        instructions="i", input=input, output_schema={}, timeout_s=5,
    )  # fmt: skip


async def test_fake_script_steps() -> None:
    fake = FakeRuntime(
        [
            ScriptStep({"turn_type": "work", "agent_name": "Translator 2"}, {"n": 2}),
            ScriptStep({"turn_type": "work", "focus": "rent"}, {"n": "rent"}),
            ScriptStep({"turn_type": "work"}, {"n": 1}, times=2),
            ScriptStep({"turn_type": "plan"}, RuntimeError_("unavailable")),
        ]
    )
    assert (await fake.run_turn(_request(agent="Translator 2"))).output == {"n": 2}
    assert (await fake.run_turn(_request(focus="rent"))).output == {"n": "rent"}
    assert (await fake.run_turn(_request())).output == {"n": 1}
    assert len(fake.unused()) == 2
    assert (await fake.run_turn(_request(agent="Translator 2"))).output == {"n": 1}
    with pytest.raises(AssertionError, match="work"):
        await fake.run_turn(_request())
    with pytest.raises(RuntimeError_) as raised:
        await fake.run_turn(_request("plan"))
    assert raised.value.code == "unavailable"
    assert fake.unused() == [] and len(fake.requests) == 6


async def test_fake_callable_script() -> None:
    fake = FakeRuntime(lambda r: {"echo": r.turn_type})
    assert (await fake.run_turn(_request("review"))).output == {"echo": "review"}
    assert fake.unused() == []


async def test_fake_placeholders() -> None:
    fake = FakeRuntime(
        lambda r: {
            "statements": [{"quotes": [{"passageId": {"$passage": "30 June"}, "citationId": {"$citation": "8%"}}]}],
            "claimIds": [{"$claim": "margin"}],
        }
    )
    request = _request(
        passages=[{"passageId": "p1", "text": "Rent rises."}, {"passageId": "p7", "text": "Ends 30 June 2029."}],
        transcript=[{"citations": [{"citationId": "c_9", "quote": "rises by 8%"}]}],
        claims=[{"claim_id": "k_3", "text": "The margin is 52.9%."}],
    )
    output = (await fake.run_turn(request)).output
    assert output == {"statements": [{"quotes": [{"passageId": "p7", "citationId": "c_9"}]}], "claimIds": ["k_3"]}
    with pytest.raises(AssertionError, match="nothing"):
        await FakeRuntime(lambda r: {"x": {"$passage": "absent"}}).run_turn(request)


async def test_fake_from_file(tmp_path: Path) -> None:
    path = tmp_path / "script.json"
    path.write_text(json.dumps([
        {"match": {"turn_type": "plan"}, "output": {"ok": True}},
        {"match": {"turn_type": "verify"}, "output": {"$raise": "timeout"}, "times": 1},
    ]))  # fmt: skip
    fake = FakeRuntime.from_file(path)
    assert (await fake.run_turn(_request("plan"))).output == {"ok": True}
    with pytest.raises(RuntimeError_):
        await fake.run_turn(_request("verify"))
