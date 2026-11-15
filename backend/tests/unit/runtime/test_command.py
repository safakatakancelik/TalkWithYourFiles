import json
import sys
import time
from pathlib import Path

import pytest

from twyf.config import Settings
from twyf.runtime import get_runtime
from twyf.runtime.base import RuntimeError_, TurnRequest
from twyf.runtime.command import CommandRuntime, build_prompt, parse_output

CLI = [sys.executable, str(Path(__file__).parents[2] / "fixtures" / "fake_cli.py")]


def _request(timeout_s: int = 10) -> TurnRequest:
    return TurnRequest(
        turn_id="t_1", turn_type="volunteer", agent_name="T1", agent_kind="translator", system_prompt="SYSTEM",
        instructions="INSTRUCTIONS", input={"question": "Q?"}, output_schema={"type": "object"}, timeout_s=timeout_s,
    )  # fmt: skip


async def test_command_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = CommandRuntime(CLI)
    monkeypatch.setenv("FAKE_CLI_OUTPUT", '{"volunteer": true}')
    assert (await runtime.run_turn(_request())).output == {"volunteer": True}

    wrapped = {
        "result": '```json\n{"volunteer": false}\n```',
        "model": "m-1",
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }
    monkeypatch.setenv("FAKE_CLI_OUTPUT", json.dumps(wrapped))
    result = await runtime.run_turn(_request())
    assert result.output == {"volunteer": False}
    assert (result.usage.model, result.usage.input_tokens, result.usage.output_tokens) == ("m-1", 5, 2)

    monkeypatch.setenv("FAKE_CLI_OUTPUT", '```\n{"a": 1}\n```')
    assert (await runtime.run_turn(_request())).output == {"a": 1}

    monkeypatch.setenv("FAKE_CLI_EXIT", "3")
    with pytest.raises(RuntimeError_) as raised:
        await runtime.run_turn(_request())
    assert raised.value.code == "unavailable"
    monkeypatch.delenv("FAKE_CLI_EXIT")

    monkeypatch.setenv("FAKE_CLI_SLEEP", "5")
    started = time.monotonic()
    with pytest.raises(RuntimeError_) as raised:
        await runtime.run_turn(_request(timeout_s=1))
    assert raised.value.code == "timeout" and time.monotonic() - started < 4


async def test_command_prompt_and_bad_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt = build_prompt(_request())
    assert prompt.index("SYSTEM") < prompt.index("INSTRUCTIONS") < prompt.index('"question"')
    assert prompt.rstrip().endswith("Reply with one JSON object and nothing else.")
    for bad in ("not json", "[1, 2]", '{"result": "still not json"}'):
        with pytest.raises(RuntimeError_) as raised:
            parse_output(bad)
        assert raised.value.code == "bad_output"
    with pytest.raises(RuntimeError_):
        await CommandRuntime([str(tmp_path / "missing-cli")]).run_turn(_request())
    assert isinstance(get_runtime(Settings(runtime="command", command=CLI)), CommandRuntime)
    assert CommandRuntime(CLI).capabilities == frozenset()
