"""Turns one operation call into one HTTP request to the API, by the binding rule of 03-contract.md section 3."""

import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import TypeAdapter

from twyf.contract.base import Wire
from twyf.contract.operations import Operation

SOURCE = {"X-TWYF-Source": "mcp"}


def headers(client: str | None) -> dict[str, str]:
    return {**SOURCE, "X-TWYF-Client": client} if client else dict(SOURCE)


def request_parts(op: Operation, input: Wire) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """The path, the query parameters and the JSON body for this operation and input."""
    data = input.model_dump(mode="json", by_alias=True, exclude_none=True)
    names = input.model_dump(mode="json", exclude_none=True)
    path_fields = re.findall(r"{(\w+)}", op.path)
    path = re.sub(r"{(\w+)}", lambda m: str(names[m.group(1)]), op.path)
    fields = type(input).model_fields
    aliases = {name: (fields[name].alias or name) for name in path_fields}
    rest = {k: v for k, v in data.items() if k not in aliases.values()}
    if op.method == "GET":
        return path, rest, None
    return path, {}, rest


def raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        error = response.json()["error"]
        raise ToolError(f"{error['code']}: {error['message']}")
    except (ValueError, KeyError, TypeError):
        raise ToolError(f"internal: the API answered {response.status_code}") from None


def parse(op: Operation, response: httpx.Response) -> Any:
    """The API's JSON, exactly as the HTTP door returns it. None when the operation has no output."""
    if response.status_code == 204 or op.output is None:
        return None
    return response.json()


async def call(http: httpx.AsyncClient, op: Operation, input: Wire, client: str | None = None) -> Any:
    path, params, body = request_parts(op, input)
    response = await http.request(op.method, path, params=params or None, json=body, headers=headers(client))
    raise_for_error(response)
    return parse(op, response)


async def upload(
    http: httpx.AsyncClient, op: Operation, input: Wire, name: str, data: bytes, client: str | None = None
) -> Any:
    path, _, _ = request_parts(op, input)
    response = await http.post(path, files={"file": (name, data)}, headers=headers(client))
    raise_for_error(response)
    return parse(op, response)


async def events(
    http: httpx.AsyncClient, op: Operation, input: Wire, client: str | None = None
) -> AsyncIterator[dict[str, Any]]:
    """The events of a stream operation, one JSON object at a time, as they arrive."""
    path, params, body = request_parts(op, input)
    async with http.stream(op.method, path, params=params or None, json=body, headers=headers(client)) as response:
        if response.status_code >= 400:
            await response.aread()
            raise_for_error(response)
        data: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data.append(line[len("data: ") :])
            elif line == "" and data:
                yield TypeAdapter(dict[str, Any]).validate_json("\n".join(data))
                data = []
