import threading
import time

import pytest

from twyf.files.jobs import InlineJobs, ThreadJobs


def test_jobs(caplog: pytest.LogCaptureFixture) -> None:
    ran: list[str] = []
    InlineJobs().submit(lambda: ran.append("inline"))
    assert ran == ["inline"]

    jobs = ThreadJobs()
    threads: list[str] = []

    def job(name: str) -> None:
        time.sleep(0.01)
        threads.append(threading.current_thread().name)
        ran.append(name)

    def boom() -> None:
        raise RuntimeError("job failed")

    jobs.submit(lambda: job("a"))
    jobs.submit(boom)
    jobs.submit(lambda: job("b"))
    jobs.join()
    assert ran == ["inline", "a", "b"]
    assert all(name != threading.current_thread().name for name in threads)
    assert "background job failed" in caplog.text


def test_inline_job_error_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> None:
        raise RuntimeError("x")

    InlineJobs().submit(boom)
    assert "background job failed" in caplog.text
