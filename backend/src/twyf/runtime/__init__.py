from twyf.config import Settings
from twyf.runtime.base import AgentRuntime
from twyf.runtime.fake import FakeRuntime


def get_runtime(settings: Settings) -> AgentRuntime:
    if settings.runtime == "fake":
        return FakeRuntime([])
    if settings.runtime == "queue":
        from twyf.runtime.queue import QueueRuntime  # imports services, which import this package
        from twyf.services import state

        return QueueRuntime(state.connect, lease_s=settings.turn_timeout_s)
    # The command runtime is task B32.
    raise ValueError(f"runtime {settings.runtime!r} is not available yet")
