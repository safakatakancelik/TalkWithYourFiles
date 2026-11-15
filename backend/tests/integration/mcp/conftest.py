from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from mcp import Client
from mcp.server.mcpserver import MCPServer

from tests.integration.mcp.streaming import StreamingASGITransport
from twyf.mcp.server import build_server


class OneShotClient:
    """Each method opens a fresh `mcp.Client` in the calling task and closes it after the call.

    The protocol revision is stateless, so nothing is lost; and pytest-asyncio sets up and tears down async
    fixtures in different tasks, which an entered Client (an anyio task group) does not allow."""

    def __init__(self, server: MCPServer) -> None:
        self.server = server

    def __getattr__(self, name: str) -> Callable[..., Coroutine[Any, Any, Any]]:
        async def forward(*args: Any, **kwargs: Any) -> Any:
            async with Client(self.server) as client:
                return await getattr(client, name)(*args, **kwargs)

        return forward


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = StreamingASGITransport(app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c,
    ):
        yield c


@pytest.fixture
def mcp_client(http: httpx.AsyncClient) -> Any:
    return OneShotClient(build_server(http))
