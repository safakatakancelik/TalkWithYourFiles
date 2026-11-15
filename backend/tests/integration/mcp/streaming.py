"""An ASGI transport for httpx that streams the response body as the app sends it.

httpx's own ASGITransport collects the whole body first, which would block `ask` with `wait: false` until the
question ends. Test infrastructure only."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI


class _Body(httpx.AsyncByteStream):
    def __init__(self, chunks: "asyncio.Queue[bytes | None]", task: "asyncio.Task[None]") -> None:
        self.chunks, self.task = chunks, task

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while (chunk := await self.chunks.get()) is not None:
            yield chunk

    async def aclose(self) -> None:
        if not self.task.done():
            self.task.cancel()


class StreamingASGITransport(httpx.AsyncBaseTransport):
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        scope: dict[str, Any] = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": request.method,
            "scheme": request.url.scheme, "path": request.url.path, "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query, "root_path": "", "server": ("test", 80), "client": ("127.0.0.1", 1),
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
        }  # fmt: skip
        sent = False
        start: asyncio.Future[tuple[int, list[tuple[bytes, bytes]]]] = asyncio.get_running_loop().create_future()
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                start.set_result((message["status"], message.get("headers", [])))
            elif message["type"] == "http.response.body":
                if message.get("body"):
                    await chunks.put(message["body"])
                if not message.get("more_body", False):
                    await chunks.put(None)

        async def run() -> None:
            try:
                await self.app(scope, receive, send)
            finally:
                await chunks.put(None)

        task = asyncio.get_running_loop().create_task(run())
        status, headers = await start
        return httpx.Response(status, headers=headers, stream=_Body(chunks, task), request=request)
