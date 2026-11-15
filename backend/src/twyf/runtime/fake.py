"""A scripted runtime for tests and for the demo: `twyf serve --runtime fake --fake-script <path>`."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from twyf.runtime.base import RuntimeError_, TurnRequest, TurnResult

REQUEST_KEYS = ("turn_type", "agent_name", "agent_kind")

# Placeholder -> (the id key it resolves to, the key whose text must contain the given string)
PLACEHOLDERS = {
    "$passage": ("passageId", "text"),
    "$citation": ("citationId", "quote"),
    "$claim": ("claimId", "text"),
}


@dataclass
class ScriptStep:
    match: dict[str, Any]
    output: dict[str, Any] | Exception
    times: int = 1
    used: int = field(default=0, compare=False)


type Script = Callable[[TurnRequest], dict[str, Any] | Exception] | list[ScriptStep]


def _snake(key: str) -> str:
    return "".join("_" + c.lower() if c.isupper() else c for c in key)


def _records(node: Any) -> list[dict[str, Any]]:
    """Every object in the input, depth first, in order."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        obj = cast(dict[str, Any], node)
        found.append(obj)
        for value in obj.values():
            found += _records(value)
    elif isinstance(node, list):
        for value in cast(list[Any], node):
            found += _records(value)
    return found


def _get(obj: dict[str, Any], key: str) -> Any:
    return obj.get(key, obj.get(_snake(key)))


def resolve(output: Any, request_input: dict[str, Any], turn: str) -> Any:
    """Replaces {"$passage": "text"}, {"$citation": "text"} and {"$claim": "text"} with ids from the input."""
    if isinstance(output, list):
        return [resolve(v, request_input, turn) for v in cast(list[Any], output)]
    if not isinstance(output, dict):
        return output
    obj = cast(dict[str, Any], output)
    if len(obj) == 1 and next(iter(obj)) in PLACEHOLDERS:
        name, needle = next(iter(obj.items()))
        id_key, text_key = PLACEHOLDERS[name]
        for record in _records(request_input):
            ident, text = _get(record, id_key), _get(record, text_key)
            if isinstance(ident, str) and isinstance(text, str) and str(needle) in text:
                return ident
        raise AssertionError(f"{turn}: placeholder {name}={needle!r} matches nothing in the input")
    return {k: resolve(v, request_input, turn) for k, v in obj.items()}


def _matches(step: ScriptStep, request: TurnRequest) -> bool:
    for key, expected in step.match.items():
        actual = getattr(request, key) if key in REQUEST_KEYS else _get(request.input, key)
        if actual != expected:
            return False
    return True


def _step(raw: dict[str, Any]) -> ScriptStep:
    data = cast(dict[str, Any], raw["output"])
    output: dict[str, Any] | Exception = data
    if "$raise" in data:
        output = RuntimeError_(str(data["$raise"]), "scripted failure")
    return ScriptStep(match=raw.get("match", {}), output=output, times=raw.get("times", 1))


class FakeRuntime:
    name = "fake"
    capabilities = frozenset({"vision"})

    def __init__(self, script: Script) -> None:
        self.script = script
        self.requests: list[TurnRequest] = []

    @classmethod
    def from_file(cls, path: Path) -> "FakeRuntime":
        """A JSON list of {match, output, times}. An output {"$raise": code} raises RuntimeError_(code)."""
        return cls([_step(raw) for raw in json.loads(path.read_text())])

    def unused(self) -> list[ScriptStep]:
        if callable(self.script):
            return []
        return [s for s in self.script if s.used < s.times]

    def _answer(self, request: TurnRequest) -> dict[str, Any] | Exception:
        if callable(self.script):
            return self.script(request)
        for step in self.script:
            if step.used < step.times and _matches(step, request):
                step.used += 1
                return step.output
        raise AssertionError(f"no script step for turn {request.turn_type} of {request.agent_name}")

    async def run_turn(self, request: TurnRequest) -> TurnResult:
        self.requests.append(request)
        answer = self._answer(request)
        if isinstance(answer, Exception):
            raise answer
        return TurnResult(output=resolve(answer, request.input, request.turn_type))

    async def cancel(self, turn_id: str) -> None:
        return None
