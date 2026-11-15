"""Server-sent events for `ask` and `get_question_events` (03-contract.md section 4.2)."""

import asyncio
import json
from collections.abc import AsyncIterator

from twyf.contract.events import AgentEvent
from twyf.contract.models import dump
from twyf.recording.broker import EventBroker
from twyf.services.questions import ConnFactory, follow

PING_S = 15.0


def format(event_id: int, event: AgentEvent) -> bytes:
    return f"id: {event_id}\nevent: {event.type}\ndata: {json.dumps(dump(event))}\n\n".encode()


async def with_pings(items: AsyncIterator[tuple[int, AgentEvent]], ping_s: float = PING_S) -> AsyncIterator[bytes]:
    """Each event as SSE, and a `: ping` comment whenever nothing arrived for `ping_s` seconds."""
    pending: asyncio.Task[tuple[int, AgentEvent]] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(items))
            done, _ = await asyncio.wait({pending}, timeout=ping_s)
            if not done:
                yield b": ping\n\n"
                continue
            try:
                event_id, event = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield format(event_id, event)
    finally:
        if pending is not None:
            pending.cancel()


def stream(broker: EventBroker, conn_factory: ConnFactory, question_id: str, after: int) -> AsyncIterator[bytes]:
    return with_pings(follow(broker, conn_factory, question_id, after))
