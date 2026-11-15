"""Runs a headless CLI (for example `claude -p`) once per turn, in an empty folder (04-agents.md section 6.3)."""

import asyncio
import json
import re
import tempfile
from typing import Any, cast

from twyf.contract.turns import Usage
from twyf.runtime.base import RuntimeError_, TurnRequest, TurnResult

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def build_prompt(request: TurnRequest) -> str:
    return "\n\n".join([
        request.system_prompt,
        request.instructions,
        "Input:\n" + json.dumps(request.input, indent=2),
        "Output schema:\n" + json.dumps(request.output_schema, indent=2),
        "Reply with one JSON object and nothing else.",
    ])  # fmt: skip


def _object(text: str) -> dict[str, Any]:
    match = _FENCE.match(text)
    value = json.loads(match.group(1) if match else text)
    if not isinstance(value, dict):
        raise TypeError("the output is not a JSON object")
    return cast(dict[str, Any], value)


def parse_output(stdout: str) -> tuple[dict[str, Any], Usage]:
    """A `{"result": "..."}` wrapper is unwrapped (fences stripped) and its usage read; otherwise stdout is the object."""
    try:
        outer = _object(stdout.strip())
        result = outer.get("result")
        if not isinstance(result, str):
            return outer, Usage()
        usage = cast(dict[str, Any], outer.get("usage") or {})
        return _object(result.strip()), Usage(
            model=outer.get("model"), input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens")
        )
    except (ValueError, TypeError) as error:  # json.JSONDecodeError is a ValueError
        raise RuntimeError_("bad_output", str(error)) from error


class CommandRuntime:
    name = "command"
    capabilities = frozenset[str]()

    def __init__(self, command: list[str]) -> None:
        self.command = command

    async def run_turn(self, request: TurnRequest) -> TurnResult:
        with tempfile.TemporaryDirectory(prefix="twyf-turn-") as folder:
            try:
                process = await asyncio.create_subprocess_exec(
                    *self.command, cwd=folder, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )  # fmt: skip
            except OSError as error:
                raise RuntimeError_("unavailable", f"cannot start {self.command[0]}: {error}") from error
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(build_prompt(request).encode()), request.timeout_s
                )
            except TimeoutError as error:
                process.kill()
                await process.wait()
                raise RuntimeError_("timeout", f"the command took longer than {request.timeout_s} seconds") from error
            except asyncio.CancelledError:
                process.kill()
                await process.wait()
                raise
        if process.returncode != 0:
            raise RuntimeError_("unavailable", f"the command exited with {process.returncode}: {stderr.decode()[:500]}")
        output, usage = parse_output(stdout.decode())
        return TurnResult(output=output, usage=usage)

    async def cancel(self, turn_id: str) -> None:
        return None  # a running command is killed when its task is cancelled
