"""The boundary to a model. Nothing outside runtime/ knows which adapter is in use."""

from typing import Any, Protocol

from pydantic import Field

from twyf.contract.base import Wire
from twyf.contract.turns import Usage


class Attachment(Wire):
    media_type: str
    path: str


class TurnRequest(Wire):
    turn_id: str
    turn_type: str
    agent_name: str
    agent_kind: str
    system_prompt: str
    instructions: str
    input: dict[str, Any]
    output_schema: dict[str, Any]
    attachments: list[Attachment] = Field(default_factory=list[Attachment])
    timeout_s: int


class TurnResult(Wire):
    output: dict[str, Any]
    usage: Usage = Usage()


class RuntimeError_(Exception):
    """A turn the runtime could not answer. `code` is 'timeout', 'unavailable', 'bad_output' or 'cancelled'."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


class AgentRuntime(Protocol):
    name: str
    capabilities: frozenset[str]  # may contain 'vision'

    async def run_turn(self, request: TurnRequest) -> TurnResult: ...
    async def cancel(self, turn_id: str) -> None: ...
