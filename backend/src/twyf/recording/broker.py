"""In-process fan-out of agent events to the streams of a question. Fed by the recorder after each commit."""

import asyncio
import threading
from collections.abc import AsyncIterator

from twyf.contract.events import AgentEvent

type Item = tuple[int, AgentEvent] | None  # None closes the subscription


class Subscription:
    """Registered as soon as it is created, so nothing published afterwards is missed."""

    def __init__(self, broker: "EventBroker", question_id: str) -> None:
        self._broker = broker
        self._question_id = question_id
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[Item] = asyncio.Queue()
        self._done = False

    def put(self, item: Item) -> None:
        # publish may run on a worker thread: hand the item to the subscriber's own loop.
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def __aiter__(self) -> AsyncIterator[tuple[int, AgentEvent]]:
        return self

    async def __anext__(self) -> tuple[int, AgentEvent]:
        if self._done:
            raise StopAsyncIteration
        item = await self._queue.get()
        if item is None:
            self.close()
            raise StopAsyncIteration
        return item

    def close(self) -> None:
        self._done = True
        self._broker.unsubscribe(self._question_id, self)


class EventBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Subscription]] = {}

    def subscribe(self, question_id: str) -> Subscription:
        subscription = Subscription(self, question_id)
        with self._lock:
            self._subscribers.setdefault(question_id, []).append(subscription)
        return subscription

    def unsubscribe(self, question_id: str, subscription: Subscription) -> None:
        with self._lock:
            subs = self._subscribers.get(question_id, [])
            if subscription in subs:
                subs.remove(subscription)
            if not subs:
                self._subscribers.pop(question_id, None)

    def _current(self, question_id: str) -> list[Subscription]:
        with self._lock:
            return list(self._subscribers.get(question_id, []))

    def publish(self, question_id: str, event_id: int, event: AgentEvent) -> None:
        for subscription in self._current(question_id):
            subscription.put((event_id, event))

    def close(self, question_id: str) -> None:
        for subscription in self._current(question_id):
            subscription.put(None)


BROKER = EventBroker()
"""The process's broker. The recorder publishes to it, and the stream handlers subscribe to it."""
