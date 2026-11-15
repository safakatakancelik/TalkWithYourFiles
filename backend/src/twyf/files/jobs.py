"""Background jobs for ingestion: one worker thread in the server, inline in tests and in seeding."""

import logging
import queue
import threading
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger(__name__)

type Job = Callable[[], None]


class Jobs(Protocol):
    def submit(self, fn: Job) -> None: ...
    def join(self) -> None: ...


def _run(fn: Job) -> None:
    try:
        fn()
    except Exception:
        log.exception("background job failed")


class InlineJobs:
    """Runs each job at once, before `submit` returns."""

    def submit(self, fn: Job) -> None:
        _run(fn)

    def join(self) -> None:
        return None


class ThreadJobs:
    """Runs jobs in order on one worker thread. A job that raises is logged and does not stop the next."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Job] = queue.Queue()
        self._thread = threading.Thread(target=self._work, name="twyf-jobs", daemon=True)
        self._thread.start()

    def _work(self) -> None:
        while True:
            fn = self._queue.get()
            try:
                _run(fn)
            finally:
                self._queue.task_done()

    def submit(self, fn: Job) -> None:
        self._queue.put(fn)

    def join(self) -> None:
        self._queue.join()
